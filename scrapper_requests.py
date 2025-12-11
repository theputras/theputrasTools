# scrapper_requests.py
import os, json, time
import requests
from bs4 import BeautifulSoup
import pandas as pd
from dotenv import load_dotenv
from urllib.parse import urljoin, quote, unquote
import re
from datetime import datetime, date, timedelta
import logging
from typing import List, Dict, Any, Optional
from zoneinfo import ZoneInfo
from flask import session, has_request_context
from controller.GateController import get_authenticated_session, reset_session_user
from models.gate import GateUser

load_dotenv()
proxy_url = os.getenv("HTTP_PROXY_URL")
# USER = os.getenv("SICYCA_USER")
# PASS = os.getenv("SICYCA_PASS")
# if not USER or not PASS:
#     raise SystemExit("Set SICYCA_USER dan SICYCA_PASS di .env")
# === ENV & TZ ===
TZ = os.getenv("TIMEZONE", "Asia/Jakarta")
JKT = ZoneInfo(TZ)
TARGET_URL = "https://sicyca.dinamika.ac.id"
GATE_ROOT = "https://gate.dinamika.ac.id"
COOKIES_FILE = "cookies.json"
API_SICYCA = "/sicyca_api.php"

# === STATE MANAGEMENT ===
VALIDITY_CHECK_INTERVAL = 300  # Cek validitas ke server max 5 menit sekali
gate_user_model = GateUser()

# # === HTTP session (retry) ===
# _session = requests.Session()
# _retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[429, 500, 502, 503, 504])
# _session.mount("https://", HTTPAdapter(max_retries=_retries))
# _session.mount("http://", HTTPAdapter(max_retries=_retries))

# === Cache harian ===
_cache_data: Dict[str, Any] = {}
_cache_expire_at: float = 0.0



def _midnight_epoch() -> float:
    now = datetime.now(JKT)
    midnight_tomorrow = datetime(now.year, now.month, now.day, tzinfo=JKT) + timedelta(days=1)
    return midnight_tomorrow.timestamp()


# === HELPER: DETEKSI USER ID OTOMATIS ===
def _get_current_user_id(explicit_id=None):
    """
    Menentukan User ID mana yang dipakai untuk scraping.
    Prioritas:
    1. Parameter explicit (jika dikirim manual)
    2. Flask Session (jika dipanggil user via web/API)
    3. Default '1' (jika dipanggil Scheduler/Background job)
    """
    if explicit_id:
        return explicit_id
    
    if has_request_context():
        # Sedang diakses via Browser/API
        uid = session.get('user_id')
        if uid:
            return uid
        logging.warning("[Scraper] Request context ada, tapi tidak ada user_id di session.")
    
    # Fallback untuk Scheduler / Bot (Default User ID 1)
    # Pastikan User ID 1 sudah di-seed di database!
    logging.info("[Scraper] Menggunakan User ID default (1) untuk proses ini.")
    return 1

# === HELPER: AMBIL CREDENTIALS (NIM & TOKEN) ===
def _get_api_params(user_id, session_obj):
    """
    Mengambil NIM dari DB dan GLOBAL TOKEN dari HTML Gate Dashboard.
    """
    # 1. Ambil NIM dari Database
    _, nim, _ = gate_user_model.get_credentials_by_user_id(user_id)
    if not nim:
        logging.error(f"Gagal mengambil NIM untuk User ID {user_id}")
        return None, None

    # 2. Scrape GLOBAL TOKEN dari Gate Dashboard (Sesuai request)
    token = None
    try:
        # Request ke halaman dashboard gate untuk cari var global_token
        # Gunakan GATE_ROOT (https://gate.dinamika.ac.id)
        logging.info(f"Scraping global_token dari {GATE_ROOT}...")
        r = session_obj.get(GATE_ROOT, timeout=15)
        
        # Regex cari: var global_token = "..."
        match = re.search(r'var global_token\s*=\s*"([^"]+)"', r.text)
        if match:
            token = match.group(1)
            logging.info(f"Token ditemukan via regex global_token, dengan NIM: {nim}")
        else:
            # Fallback: cari meta csrf-token
            meta_match = re.search(r'name="csrf-token"\s+content="([^"]+)"', r.text)
            if meta_match: 
                token = meta_match.group(1)
                logging.info("Token ditemukan via meta csrf-token.")
                
    except Exception as e:
        logging.error(f"Gagal ambil token dari Gate: {e}")
        return None, None

    if not token:
        logging.warning("Token global tidak ditemukan di HTML Gate.")
        return None, None

    return nim, token

def scrape_data(user_id=None):
    logging.info("\n--- Memulai Scraping Jadwal ---")
    target_user = _get_current_user_id(user_id)
    sess = get_authenticated_session(target_user)
    if not sess: return pd.DataFrame()
    try:
        akademik_url = urljoin(TARGET_URL, "/akademik")
        resp_ak2 = sess.get(akademik_url, timeout=30, headers={"Referer": TARGET_URL})
        resp_ak2.raise_for_status()
        soup = BeautifulSoup(resp_ak2.text, "lxml")
        text_node = soup.find(string=re.compile(r'JADWAL KEGIATAN MINGGU INI', re.IGNORECASE))
        target_div = text_node.find_parent("div", class_="tabletitle") if text_node else None
        if not target_div: raise Exception("Tidak ketemu div 'JADWAL KEGIATAN MINGGU INI'.")
        table = target_div.find_next("table", class_=re.compile(r"\bsicycatable\b"))
        if not table: raise Exception("Tabel sicycatable tidak ketemu.")
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        rows = [[td.get_text(strip=True) for td in tr.find_all("td")] for tr in table.find_all("tr") if tr.find("td")]
        df_raw = pd.DataFrame(rows, columns=headers)
        df_raw.columns = df_raw.columns.str.strip()
        logging.info(f"   --> Scraping jadwal berhasil, {len(df_raw)} data ditemukan.")
        return df_raw
    except Exception as e:
        logging.error(f"Error saat scraping jadwal: {e}")
        return pd.DataFrame()

def scrape_krs(user_id=None) -> pd.DataFrame:
    """
    Scrape data KRS (Hari, Jam, MK, Kode, Kelas, SKS, Ruang)
    """
    target_user = _get_current_user_id(user_id)
    
    for attempt in range(2):
        is_force = (attempt > 0)
        s = get_authenticated_session(target_user)
        if not s: 
            if attempt == 0: continue
            return pd.DataFrame()

        try:
            logging.info(f"[KRS] Request List (Attempt {attempt+1})...")
            url_krs = f"{TARGET_URL}/akademik/krs"
            r = s.get(url_krs, timeout=30)
            
            if "login" in r.url.lower(): raise Exception("Redirected to Login")

            soup = BeautifulSoup(r.text, "html.parser")
            tabel = soup.find('table', id='tableView')
            if not tabel: tabel = soup.find('table', class_='sicycatablemanual')
            
            if not tabel:
                if attempt == 0: 
                    # Simpan debug html jika gagal
                    try:
                        with open("debug_krs_failed.html", "w", encoding="utf-8") as f: f.write(r.text)
                    except: pass
                    raise Exception("Tabel KRS tidak ditemukan")
                return pd.DataFrame()

            data_rows = []
            tr_list = tabel.find_all('tr')[1:] 
            
            for tr in tr_list:
                tds = tr.find_all('td')
                if len(tds) >= 9: 
                    hari = tds[0].get_text(strip=True)
                    waktu = tds[1].get_text(strip=True)
                    mk_raw = tds[2].get_text(strip=True)
                    # tds[3] is Brilian, skip
                    ruang = tds[4].get_text(strip=True)
                    sks = tds[5].get_text(strip=True)
                    nilai = tds[6].get_text(strip=True)
                    min_nilai = tds[7].get_text(strip=True)
                    kehadiran = tds[8].get_text(strip=True)
                    keterangan = tds[9].get_text(strip=True) if len(tds) > 9 else "-"
                    
                    # Default Parsed Values
                    nama_mk = mk_raw
                    kelas = "-"
                    kode_mk = "-"
                    param_grup = "" 
                    
                    # 1. Regex Nama & Kelas Visual: "Matkul (Kelas)"
                    match_display = re.search(r'^(.*)\s\((.*)\)$', mk_raw)
                    if match_display:
                        nama_mk = match_display.group(1).strip()
                        kelas = match_display.group(2).strip()
                    
                    # 2. Extract Parameter dari ONCLICK <a> di kolom Matakuliah (tds[2])
                    link_mk = tds[2].find('a')
                    if link_mk and link_mk.has_attr('onclick'):
                        onclick = link_mk['onclick']
                        # format: showModalMatakuliah('KELAS','KODE','NAMA')
                        args = re.findall(r"['\"](.*?)['\"]", onclick)
                        
                        if "showModalMatakuliahSP" in onclick and len(args) >= 4:
                            kelas = args[0]
                            kode_mk = args[1]
                            # args[2] = nama
                            param_grup = args[3]
                        elif len(args) >= 2:
                            kelas = args[0]
                            kode_mk = args[1]
                    
                    # Bersihkan text tombol jika isinya cuma "Detail" agar UI frontend rapi
                    # Frontend logic: if Nilai !== '-', show button Detail. 
                    # Jadi biarkan 'Detail' atau text aslinya jika ada.
                    # Tapi biasanya user ingin lihat Grade di 'Nilai Minimal' dan tombol di 'Nilai'
                    
                    data_rows.append({
                        "Hari": hari, 
                        "Waktu": waktu, 
                        "Matakuliah": nama_mk, # Nama bersih (tanpa kelas)
                        "Ruang": ruang,
                        "SKS": sks,
                        "Nilai": nilai,       # Isinya biasanya text "Detail"
                        "Nilai Minimal": min_nilai, # Isinya Grade (A, B, C)
                        "Kehadiran": kehadiran, # Isinya Persentase (50%, dll)
                        "Keterangan": keterangan,
                        # Params untuk Modal Frontend
                        "param_mk": kode_mk,   
                        "param_kls": kelas,    
                        "param_grup": param_grup
                    })
            
            if data_rows:
                logging.info(f"[KRS] Berhasil ambil {len(data_rows)} data.")
                return pd.DataFrame(data_rows)
            else:
                return pd.DataFrame()

        except Exception as e:
            logging.warning(f"[KRS] Error attempt {attempt+1}: {e}")
            if attempt == 0: continue
                
    return pd.DataFrame()


def fetch_masa_studi(user_id=None) -> str:
    target_user = _get_current_user_id(user_id)
    
    for attempt in range(2):
        s = get_authenticated_session(target_user)
        if not s: 
            if attempt == 0: continue
            return "-"

        try:
            nim, token = _get_api_params(target_user, s)
            if not nim or not token: 
                if attempt == 0: continue
                return "-"

            payload = {
                "nim": nim,
                "token": token,
                "masa_studi": True
            }

            r = s.post(f"{TARGET_URL}{API_SICYCA}", data=payload, timeout=10)
            
            if r.status_code == 200:
                try:
                    data = r.json()
                    if isinstance(data, dict) and 'data' in data:
                        result = data['data']
                        logging.info(f"    --> Masa studi JSON: {result}")
                        return result
                    return str(data)
                except:
                    pass # Retry
            
            if attempt == 0: continue

        except Exception as e:
            logging.error(f"[Masa Studi] Error: {e}")
            if attempt == 0: continue
                
    return "-"
        
def scrape_krs_detail(params: Dict[str, str], user_id=None) -> Dict[str, Any]:
    """
    Mengambil detail KRS. Menangani struktur Tabel murni (Nilai/Kehadiran) 
    dan struktur Campuran (Matakuliah: Info Dosen + Tabel Peserta).
    """
    logging.info(f"\n--- Scraping KRS Detail: {params} ---")
    target_user = _get_current_user_id(user_id)
    sess = get_authenticated_session(target_user)
    if not sess:
        return {"success": False, "message": "Gagal mendapatkan sesi valid."}

    proxy_url = urljoin(TARGET_URL, "/table-proxy/")
    
    try:
        resp = sess.get(proxy_url, params=params, timeout=20, headers={"Referer": TARGET_URL})
        
        # # Cek Redirect (Session Expired)
        # if "gate.dinamika.ac.id" in resp.url or "/login" in resp.url:
        #     reset_session_memory()
        #     return {"success": False, "message": "Sesi kedaluwarsa. Silakan refresh."}

        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        ada_prak = soup.find(string=re.compile(r"Group\s*Prak", re.IGNORECASE))
        
        # Tentukan judul dinamis buat Tabel Mahasiswa
        judul_tabel_mhs = "Data Praktikum Mahasiswa" if ada_prak else "Data Peserta Mahasiswa"
        # =================================================================
        # --- 1. AMBIL METADATA (Untuk kasus t=matakuliah) ---
        # Mencari teks di body yang bukan bagian dari tabel, lalu cari pola "Label: Value"
        metadata = {}
        full_text = soup.get_text(separator="\n")
        
        # Regex sederhana untuk menangkap "Label: Value" (misal: "Dosen: Budi")
        # Kita batasi agar tidak mengambil isi tabel
        lines = full_text.split('\n')
        for line in lines:
            if ":" in line:
                parts = line.split(":", 1)
                key = parts[0].strip()
                val = parts[1].strip()
                # Filter supaya gak ambil sampah (key terlalu panjang biasanya bukan label)
                if len(key) < 50 and val: 
                    metadata[key] = val
        
        # =================================================================
        # --- 2. AMBIL TABEL ---
        tables_list = []
        html_tables = soup.find_all("table")
        
        for table in html_tables:
            # --- Coba Cari Judul Tabel ---
            # Cari elemen text sebelumnya (misal "PESERTA KULIAH")
            title = ""
            
            # Logic: Mundur ke elemen sebelumnya sampai ketemu text yang bukan kosong
            prev_el = table.previous_sibling
            while prev_el:
                if isinstance(prev_el, str) and prev_el.strip():
                    title = prev_el.strip()
                    found_title = prev_el.strip()
                    title = found_title
                    break
                if hasattr(prev_el, 'get_text') and prev_el.get_text(strip=True):
                    found_title = prev_el.get_text(strip=True)
                    title = prev_el.get_text(strip=True)
                    title = found_title
                    break
                prev_el = prev_el.previous_sibling
            
            # Bersihkan judul (kadang kebawa tanda baca aneh)
            title = re.sub(r'[^\w\s]', '', title).strip() or "Detail"
# --- Parse Header ---
            headers = []
            thead = table.find("thead")
            if thead:
                headers = [th.get_text(strip=True) for th in thead.find_all("th")]
            
            if not headers:
                first_tr = table.find("tr")
                if first_tr:
                    headers = [ele.get_text(strip=True) for ele in first_tr.find_all(["th", "td"])]

            # Fallback nama kolom
            headers = [h if h else f"Kolom {i+1}" for i, h in enumerate(headers)]

            # =============================================================
            # [LOGIC TITLE] PENENTUAN JUDUL TABEL
            # =============================================================
            # Gabung header jadi string lowercase buat pengecekan
            headers_str = " ".join(headers).lower()

            if "nim" in headers_str or "nama" in headers_str:
                # Ini pasti tabel daftar mahasiswa -> Pakai judul dinamis
                title = judul_tabel_mhs
            elif "dosen" in headers_str or "matakuliah" in headers_str or "sks" in headers_str:
                # Ini tabel metadata (yang isinya rows group prak tadi)
                title = "Detail Mata Kuliah"
            else:
                # Fallback title (mencoba cari judul dari text sebelumnya seperti kode lama)
                title = "Data Lainnya"
                prev_el = table.previous_sibling
                while prev_el:
                    if isinstance(prev_el, str) and prev_el.strip():
                        title = prev_el.strip()
                        break
                    if hasattr(prev_el, 'get_text') and prev_el.get_text(strip=True):
                        title = prev_el.get_text(strip=True)
                        break
                    prev_el = prev_el.previous_sibling
                title = re.sub(r'[^\w\s]', '', title).strip() or "Tabel Data"
            # --- Parse Rows ---
            rows_data = []
            all_trs = table.find_all("tr")
            
            # Skip header row?
            start_idx = 0
            # Jika headers diambil dari tr pertama dan tidak ada thead, skip tr pertama
            if not thead and all_trs and headers:
                # Cek apakah tr pertama isinya sama persis dengan headers
                first_tr_text = [e.get_text(strip=True) for e in all_trs[0].find_all(["th", "td"])]
                if first_tr_text == headers:
                    start_idx = 1

            tbody = table.find("tbody")
            tr_source = tbody.find_all("tr") if tbody else all_trs[start_idx:]

            for tr in tr_source:
                cols = tr.find_all("td")
                if not cols: continue
                # Skip baris kosong
                if len(cols) == 1 and not cols[0].get_text(strip=True): continue

                row_obj = {}
                for idx, td in enumerate(cols):
                    val = td.get_text(strip=True)
                    link = td.find("a")
                    
                    if idx < len(headers):
                        col_name = headers[idx]
                        row_obj[col_name] = val
                        if link and link.get("href"):
                            row_obj[f"{col_name}_link"] = link.get("href")
                
                if row_obj:
                    rows_data.append(row_obj)
            
            # Masukkan ke list tables jika ada isinya
            if headers or rows_data:
                tables_list.append({
                    "title": title,
                    "headers": headers,
                    "rows": rows_data
                })
        
        # --- 3. RETURN HASIL ---
        return {
            "success": True,
            "metadata": metadata,
            "tables": tables_list # ARRAY of tables
        }

    except Exception as e:
        logging.error(f"Error scrape krs detail: {e}")
        return {"success": False, "message": str(e)}

def _generic_search(endpoint, query, label, user_id=None) -> pd.DataFrame:
    """Helper function untuk search mhs/staff agar tidak duplikasi kode"""
    logging.info(f"\n--- Cari {label}: '{query}' ---")
    target_user = _get_current_user_id(user_id)
    sess = get_authenticated_session(target_user)
    if not sess: return pd.DataFrame()
    try:
        search_url = urljoin(TARGET_URL, f"{endpoint}?q={quote(query)}")
        resp = sess.get(search_url, timeout=20)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, "lxml")
        # Cari tabel pertama yang sicycatable (biasanya hasil pencarian)
        table = soup.find("table", class_=re.compile(r"\bsicycatable\b"))
        
        if not table:
            logging.info(f"   --> Tidak ada hasil {label}.")
            return pd.DataFrame()
            
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        rows = [[td.get_text(strip=True) for td in tr.find_all("td")] for tr in table.find_all("tr") if tr.find("td")]
        
        df = pd.DataFrame(rows, columns=headers)
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        logging.error(f"Error cari {label}: {e}")
        return pd.DataFrame()

def search_mahasiswa(query):
    return _generic_search("/komunitas/mahasiswa/", query, "Mahasiswa")

def search_staff(query):
    return _generic_search("/komunitas/staff/", query, "Staff")

def fetch_photo_from_sicyca(role, id_, user_id=None):
    """
    Fetch foto dari Sicyca menggunakan session authenticated.
    role: 'mahasiswa' atau 'staff'
    id_: NIM (untuk mahasiswa) atau NIK (untuk staff)
    Returns: bytes of image content, or None if failed.
    """
    target_user = _get_current_user_id(user_id)
    sess = get_authenticated_session(target_user)
    if not sess:
        logging.error(f"   --> Gagal fetch foto {role}/{id_}: Session tidak valid.")
        return None
    
    try:
        if role == "mahasiswa":
            photo_url = f"{TARGET_URL}/static/foto/mahasiswa/{id_}.jpg"
        elif role == "staff":
            photo_url = f"{TARGET_URL}/static/foto/karyawan/{id_}.jpg"
        else:
            raise ValueError("Role tidak valid.")
        
        logging.info(f"   --> Fetching foto dari {photo_url}")
        response = sess.get(photo_url, timeout=10, headers={"Referer": TARGET_URL})
        response.raise_for_status()
        
        if response.headers.get('content-type', '').startswith('image/'):
            logging.info(f"   --> Foto {role}/{id_} berhasil di-fetch ({len(response.content)} bytes).")
            return response.content
        else:
            logging.warning(f"   --> Response bukan image untuk {role}/{id_}.")
            return None
    except requests.RequestException as e:
        logging.error(f"   --> Gagal fetch foto {role}/{id_}: {e}")
        return None
    except Exception as e:
        logging.error(f"   --> Error tak terduga saat fetch foto {role}/{id_}: {e}")
        return None
        
    
        

def fetch_data_ultah(force_refresh=False, user_id=None):
    """
    Mengambil data ulang tahun, memparsing format DD-MM-YYYY, 
    menghitung umur, dan menyesuaikan key output untuk frontend.
    """
    target_user = _get_current_user_id(user_id)
    
    # Mapping Bulan Indonesia (Untuk format tampilan: 10 Desember 2024)
    bulan_indo = {
        1: "Januari", 2: "Februari", 3: "Maret", 4: "April", 5: "Mei", 6: "Juni",
        7: "Juli", 8: "Agustus", 9: "September", 10: "Oktober", 11: "November", 12: "Desember"
    }

    for attempt in range(2):
        s = get_authenticated_session(target_user)
        if not s: 
            if attempt == 0: continue
            return {"error": True, "message": "Gagal mendapatkan sesi valid.", "rows": []}

        try:
            nim, token = _get_api_params(target_user, s)
            if not nim or not token:
                if attempt == 0: continue 
                return {"error": True, "message": "Gagal mengambil Token/NIM.", "rows": []}
            
            payload = {"nim": nim, "token": token, "ultah": True}
            
            logging.info(f"[ULTAH] Mengambil data ultah (Attempt {attempt+1})...")
            r = s.post(f"{TARGET_URL}{API_SICYCA}", data=payload, timeout=20)
            
            if r.status_code == 200:
                try:
                    raw_data = r.json()
                    
                    # 1. Ambil list data mentah berdasarkan struktur JSON yang kamu kirim
                    # Struktur: { "data": [ { "NAMA": "...", ... }, ... ] }
                    raw_rows = []
                    if isinstance(raw_data, dict):
                        raw_rows = raw_data.get('data', [])
                    elif isinstance(raw_data, list):
                        raw_rows = raw_data
                    
                    formatted_rows = []
                    now = datetime.now(JKT) # Waktu server sekarang (Asia/Jakarta)

                    for item in raw_rows:
                        # 2. Ambil Key Huruf Kapital (Bukan Angka)
                        nama = item.get('NAMA', 'Tanpa Nama')
                        prodi = item.get('PRODI', '-')
                        tgl_raw = item.get('TANGGAL', '') # Contoh: "10-12-2004"
                        
                        tgl_display = tgl_raw
                        umur = "??"

                        # 3. Parsing Tanggal & Hitung Umur
                        if tgl_raw and len(tgl_raw) >= 10:
                            try:
                                # Parsing format "10-12-2004" (DD-MM-YYYY)
                                dt = datetime.strptime(tgl_raw[:10], '%d-%m-%Y')
                                
                                # Format ulang jadi "10 Desember 2004" (Agar frontend bisa split)
                                tgl_display = f"{dt.day} {bulan_indo[dt.month]} {dt.year}"
                                
                                # Hitung Umur
                                # Logic: Tahun sekarang - Tahun lahir, dikurangi 1 jika ulang tahun belum lewat tahun ini
                                umur_val = now.year - dt.year - ((now.month, now.day) < (dt.month, dt.day))
                                umur = str(umur_val)
                            except ValueError as ve:
                                logging.warning(f"[ULTAH] Gagal parse tanggal {tgl_raw}: {ve}")
                                # Fallback jika format tanggal beda/error, tetap tampilkan raw
                                tgl_display = tgl_raw
                        
                        # 4. Susun Object Sesuai Frontend (renderUltah)
                        # Frontend butuh: nama, prodi, tanggal_lahir, umur
                        formatted_rows.append({
                            "nama": nama,
                            "prodi": prodi,
                            "tanggal_lahir": tgl_display, 
                            "umur": umur
                        })

                    logging.info(f"[ULTAH] Berhasil memproses {len(formatted_rows)} data.")
                    
                    return {
                        "error": False, 
                        "message": "Data ulang tahun berhasil diambil.", 
                        "jumlah": len(formatted_rows),
                        "tanggal_hari_ini": f"{now.day} {bulan_indo[now.month]} {now.year}", # Tambahan info tanggal hari ini
                        "rows": formatted_rows
                    }
                    
                except json.JSONDecodeError: 
                    logging.warning("[ULTAH] Respon bukan JSON.")
                    if attempt == 0: continue
            else:
                logging.warning(f"[ULTAH] Status Code {r.status_code}")
                if attempt == 0: continue
                
        except Exception as e:
            logging.error(f"[ULTAH] Error: {e}")
            if attempt == 0: continue
            
    return {"error": True, "message": "Gagal mengambil data ulang tahun.", "rows": []}