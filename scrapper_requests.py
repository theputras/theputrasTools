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
from flask import session, has_request_context, g
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
# === HELPER: DETEKSI USER ID OTOMATIS ===
def _get_current_user_id(explicit_id=None):
    if explicit_id:
        return explicit_id
    
    if has_request_context():
        # 1. Cek JWT (g.user)
        if hasattr(g, 'user') and g.user.get('sub'):
            return g.user.get('sub')
            
        # 2. Cek Session Flask Lama
        uid = session.get('user_id')
        if uid:
            return uid
            
        logging.warning("[Scraper] Request context ada, tapi tidak ada user_id.")
    
    # 3. Fallback Cerdas untuk Scheduler / Bot
    # JANGAN HARDCODE 1! Minta model cariin siapa yang available.
    bot_id = gate_user_model.get_bot_user() 
    
    logging.info(f"[Scraper] Mode Otomatis: Menggunakan User ID {bot_id} sebagai eksekutor.")
    return bot_id

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

def dahsboard_nilai(params, user_id=None):
    """
    Mengambil detail KRS/Nilai.
    UPDATE: Support 'dashboard_nilai_ujian' yang menggunakan struktur DIV (bukan TABLE).
    """
    target_user = _get_current_user_id(user_id)
    sess = get_authenticated_session(target_user)
    
    result = {"success": False, "tables": []}
    
    if not sess: return result

    proxy_url = urljoin(TARGET_URL, "/table-proxy/")
    
    try:
        logging.info(f"--- Scraping Table Proxy: {params} ---")
        resp = sess.get(proxy_url, params=params, headers={"Referer": TARGET_URL}, timeout=15)
        
        soup = BeautifulSoup(resp.text, "lxml")
        parsed_tables = []

        # ==========================================
        # STRATEGI 1: Cek Struktur DIV Dashboard (listUjianItem)
        # ==========================================
        # File HTML 'dashboard_nilai_ujian' menggunakan class="listUjianItem"
        div_items = soup.find_all("div", class_="listUjianItem")
        
        if div_items:
            logging.info(f"[Scraper] Terdeteksi struktur DIV Dashboard ({len(div_items)} item).")
            rows_data = []
            
            for item in div_items:
                # Struktur:
                # Span 1: Nama Matakuliah
                # Span 2: Wrapper Progress Bar -> div.progressblue (Nilai)
                spans = item.find_all("span", recursive=False)
                
                if len(spans) >= 1:
                    mk_name = spans[0].get_text(strip=True)
                    
                    # Cari nilai di dalam class 'progressblue'
                    nilai_div = item.find("div", class_="progressblue")
                    nilai_val = nilai_div.get_text(strip=True) if nilai_div else "-"
                    
                    rows_data.append({
                        "Matakuliah": mk_name,
                        "NILAI": nilai_val,  # Biasanya berupa Angka (misal: 85, 100)
                        "UTS": "-",          # Dashboard tidak menampilkan detail UTS
                        "UAS": "-"           # Dashboard tidak menampilkan detail UAS
                    })
            
            parsed_tables.append({
                "headers": ["Matakuliah", "NILAI"],
                "rows": rows_data
            })
            
        # ==========================================
        # STRATEGI 2: Cek Struktur TABLE Standar (sicycatable)
        # ==========================================
        else:
            tables = soup.find_all("table", class_=lambda x: x and x in ["sicycatable", "tabtable"])
            if not tables: tables = soup.find_all("table") # Fallback
            
            for tbl in tables:
                rows_data = []
                
                # Ambil Header
                headers = []
                thead = tbl.find("thead")
                header_cols = thead.find_all(["th", "td"]) if thead else tbl.find("tr").find_all(["th", "td"]) if tbl.find("tr") else []
                headers = [h.get_text(strip=True) for h in header_cols]
                
                # Ambil Data
                tbody = tbl.find("tbody")
                content_rows = tbody.find_all("tr") if tbody else tbl.find_all("tr")
                if not thead and content_rows: content_rows = content_rows[1:] # Skip header row

                for tr in content_rows:
                    cols = tr.find_all("td")
                    if not cols: continue
                    
                    row_dict = {}
                    for idx, col in enumerate(cols):
                        val = col.get_text(strip=True)
                        key = headers[idx] if idx < len(headers) else f"col_{idx}"
                        row_dict[key] = val
                    
                    if row_dict:
                        rows_data.append(row_dict)

                if rows_data:
                    parsed_tables.append({"headers": headers, "rows": rows_data})

        return {
            "success": True, 
            "tables": parsed_tables
        }

    except Exception as e:
        logging.error(f"[Scraper] Error scraping: {e}")
        return result


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

def search_mahasiswa(query, user_id=None):
    return _generic_search("/komunitas/mahasiswa/", query, "Mahasiswa", user_id)

def search_staff(query, user_id=None):
    return _generic_search("/komunitas/staff/", query, "Staff", user_id)

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
    
def fetch_sks(user_id=None) -> dict:
    """
    Mengambil data SKS (SKS Tempuh, SKS Ambil, Sisa SKS).
    Output mentah sesuai response API Sicyca.
    """
    target_user = _get_current_user_id(user_id)
    
    for attempt in range(2):
        s = get_authenticated_session(target_user)
        if not s: 
            if attempt == 0: continue
            return {} # Return dict kosong jika gagal

        try:
            nim, token = _get_api_params(target_user, s)
            if not nim or not token:
                if attempt == 0: continue
                return {}

            # Payload sesuai request jQuery Anda
            payload = {
                "nim": nim,
                "token": token,
                "sks": True 
            }

            logging.info(f"[SKS] Fetching data SKS (Attempt {attempt+1})...")
            # Endpoint: https://sicyca.dinamika.ac.id/sicyca_api.php
            r = s.post(f"{TARGET_URL}{API_SICYCA}", data=payload, timeout=10)
            
            if r.status_code == 200:
                try:
                    data = r.json()
                    logging.info(f"   --> SKS Data fetched.")
                    # Mengembalikan FULL JSON mentah: { "data": { "sks_tempuh": ..., ... } }
                    return data 
                except json.JSONDecodeError:
                    logging.warning("[SKS] Response bukan JSON valid.")
                    pass
            
            if attempt == 0: continue

        except Exception as e:
            logging.error(f"[SKS] Error: {e}")
            if attempt == 0: continue
                
    return {}

def get_csrf_token_gate():
    try:
        url = GATE_ROOT
        
        # 1. GUNAKAN HEADERS LENGKAP (Biar dikira Browser Asli)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,id;q=0.8',
            'Referer': GATE_ROOT,
            'Connection': 'keep-alive'
        }
        
        # Gunakan Session untuk menangkap cookies (siapa tahu dibutuhkan)
        session = requests.Session()
        response = session.get(url, headers=headers, timeout=10)
        
        print(f"[Scrapper Debug] Status Code: {response.status_code}")
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # CARA 1: Cari di Input Hidden (Sesuai source code kamu)
            # <input type="hidden" name="_token" value="...">
            token_input = soup.find('input', {'name': '_token'})
            
            if token_input:
                token_val = token_input.get('value')
                print(f"[Scrapper Success] Token ditemukan di Input: {token_val[:10]}...")
                return token_val
            
            # CARA 2: Cari di Meta Tag (Cadangan, sering dipakai Laravel)
            # <meta name="csrf-token" content="...">
            meta_token = soup.find('meta', {'name': 'csrf-token'})
            if meta_token:
                token_val = meta_token.get('content')
                print(f"[Scrapper Success] Token ditemukan di Meta: {token_val[:10]}...")
                return token_val

            # DEBUG: Jika gagal, print sedikit HTML-nya untuk dicek
            print("[Scrapper Fail] Token tidak ditemukan. Cek struktur HTML di bawah:")
            print(soup.prettify()[:500]) # Print 500 karakter pertama
            
    except Exception as e:
        print(f"[Scrapper Error] Gagal ambil token gate: {e}")
        
    return ""

# FUNGSI BARU KHUSUS PROFIL
def fetch_profil_mhs(nim, user_id=None):
    """
    Mengambil foto profil khusus mahasiswa dari endpoint API Sicyca baru.
    Endpoint: https://sicyca.dinamika.ac.id/API/get_mhs_photo.php?nim=...
    """
    target_user = _get_current_user_id(user_id)
    sess = get_authenticated_session(target_user)
    
    if not sess:
        logging.error(f"[Profil Photo] Gagal mendapatkan session untuk NIM {nim}")
        return None

    try:
        # Endpoint khusus yang diminta
        url = f"{TARGET_URL}/API/get_mhs_photo.php?nim={nim}"
        
        logging.info(f"[Profil Photo] Fetching dari endpoint baru: {url}")
        
        # Request dengan session yang sudah login
        resp = sess.get(url, timeout=10, headers={"Referer": TARGET_URL})
        resp.raise_for_status()
        
        # Validasi konten apakah benar gambar
        if resp.headers.get('Content-Type', '').startswith('image/'):
            return resp.content
        else:
            logging.warning(f"[Profil Photo] Response bukan gambar: {resp.headers.get('Content-Type')}")
            return None
            
    except Exception as e:
        logging.error(f"[Profil Photo] Error fetching: {e}")
        return None
    


# --- Update scrapper_requests.py ---

def fetch_sskm_data(user_id=None):
    """
    Mengambil data SSKM secara MENTAH (Raw) dari tabel Sicyca.
    Perbaikan: 
    1. Menggunakan selector tbody untuk memisahkan header.
    2. Konversi Poin dipaksa menjadi INTEGER (int).
    """
    logging.info(f"[SSKM] Fetching Raw Data...")
    target_user = _get_current_user_id(user_id)
    sess = get_authenticated_session(target_user)
    
    result = {
        "success": False, 
        "total_poin": 0,
        "total_kegiatan": 0,
        "detail": [] 
    }

    if not sess: return result

    proxy_url = urljoin(TARGET_URL, "/table-proxy/?t=sskm")
    params = {"t": "sskm"} 

    try:
        resp = sess.get(proxy_url, params=params, timeout=20, headers={"Referer": TARGET_URL})
        soup = BeautifulSoup(resp.text, "lxml")
        
        table = soup.find("table", class_="sicycatable")
        if not table:
            logging.warning("[SSKM] Tabel sicycatable tidak ditemukan.")
            return result

        items_list = []
        total_poin = 0 

        # Ambil baris dari tbody
        tbody = table.find("tbody")
        if tbody:
            rows = tbody.find_all("tr")
        else:
            all_rows = table.find_all("tr")
            rows = [r for r in all_rows if r.find("td")]

        for tr in rows:
            cols = tr.find_all("td")
            if len(cols) < 4: continue
            
            try:
                nama_kegiatan = cols[1].get_text(strip=True)
                poin_str = cols[3].get_text(strip=True)
                
                val_poin = 0
                
                if poin_str:
                    # Bersihkan string: hanya angka, titik, koma
                    clean_str = re.sub(r'[^\d.,]', '', poin_str)
                    
                    if clean_str:
                        # Ganti koma jadi titik untuk format float standar
                        clean_str = clean_str.replace(',', '.')
                        try:
                            # Convert ke float dulu baru ke int untuk handle string "2.0"
                            # int("2.0") -> Error
                            # int(float("2.0")) -> 2 (Berhasil)
                            val_poin = int(float(clean_str))
                        except ValueError:
                            val_poin = 0

                items_list.append({
                    "kegiatan": nama_kegiatan,
                    "poin": val_poin # Sudah pasti integer
                })
                
                total_poin += val_poin
                
            except Exception:
                continue

        logging.info(f"[SSKM] Selesai. Total Raw: {total_poin} Poin dari {len(items_list)} kegiatan.")
        
        return {
            "success": True,
            "total_poin": total_poin, # Integer
            "total_kegiatan": len(items_list),
            "detail": items_list
        }

    except Exception as e:
        logging.error(f"[SSKM] Error scraping: {e}")
        return result

_kalender_cache_data = None
_kalender_cache_time = 0

def scrape_kalender_akademik(user_id=None):
    """
    Mencari semester aktif dari histori, lalu mengambil & mendownload
    gambar kalender akademik jika belum ada di lokal. (SSR Cache 1 Hari)
    """
    global _kalender_cache_data, _kalender_cache_time
    now = time.time()
    
    json_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kalender_akademik.json')
    
    # Cache 1 hari (86400 detik) untuk mengurangi request berat ke Sicyca
    if _kalender_cache_data and (now - _kalender_cache_time < 86400):
        logging.info("[Kalender] Menggunakan data gambar dari cache (memory).")
        # Ensure we always populate events from cache or JSON
        return _kalender_cache_data

    target_user = _get_current_user_id(user_id)
    sess = get_authenticated_session(target_user)
    if not sess:
        # Fallback to reading from JSON if session is invalid
        if os.path.exists(json_file_path):
             try:
                 with open(json_file_path, 'r', encoding='utf-8') as f:
                     saved_data = json.load(f)
                     if "data" in saved_data:
                          return {"success": True, "message": "Dari Cache JSON", "images": [], "semester": "", "events": saved_data["data"]}
             except Exception:
                 pass
        return {"success": False, "message": "Gagal mendapatkan sesi valid.", "images": [], "semester": "", "events": []}

    try:
        # 1. Pengecekkan semester aktif dari histori (Ambil baris terakhir)
        histori_url = urljoin(TARGET_URL, "/akademik/histori")
        r_histori = sess.get(histori_url, timeout=20, headers={"Referer": TARGET_URL})
        soup_histori = BeautifulSoup(r_histori.text, "lxml")
        
        semester_aktif = ""
        tabel_histori = soup_histori.find("table", class_="sicycatable")
        if tabel_histori:
            rows = tabel_histori.find_all("tr")
            if len(rows) > 1: # Baris 0 biasanya header tabel
                last_row = rows[-1]
                cols = last_row.find_all("td")
                if len(cols) > 1:
                    semester_aktif = cols[1].get_text(strip=True)
        
        # 2. Ambil gambar kalender
        kalender_url = urljoin(TARGET_URL, "/akademik/kalender")
        r_kalender = sess.get(kalender_url, timeout=20, headers={"Referer": TARGET_URL})
        soup_kalender = BeautifulSoup(r_kalender.text, "lxml")

        images = []
        box = soup_kalender.find("div", class_="boxcontainer")
        if box:
            img_tags = box.find_all("img")
            
            base_dir = os.path.dirname(os.path.abspath(__file__))
            save_dir = os.path.join(base_dir, "static", "kalender")
            os.makedirs(save_dir, exist_ok=True) # Buat folder kalau blm ada

            for img in img_tags:
                src = img.get("src")
                if src and "kalenderakademik" in src:
                    img_url = urljoin(TARGET_URL, src)
                    filename = os.path.basename(img_url)
                    local_path = os.path.join(save_dir, filename)
                    
                    is_new = not os.path.exists(local_path)
                    # Download jika gambar blm ada di local server
                    if is_new:
                        logging.info(f"[Kalender] Mengunduh kalender baru: {filename}")
                        img_data = sess.get(img_url, timeout=20).content
                        with open(local_path, "wb") as f:
                            f.write(img_data)
                    
                    images.append({
                        "url": f"/static/kalender/{filename}",
                        "filename": filename,
                        "local_path": local_path,
                        "is_new": is_new
                    })
        
        # Ekstrak event dinamis dari gambar kalender pertama menggunakan OCR
        events_data = []
        json_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kalender_akademik.json')
        
        # Load from file if image was not newly downloaded and json exists
        need_ocr = True
        if images and images[-1].get("local_path"):
             last_image = images[-1]
             last_image_path = last_image["local_path"]
             is_new_image = last_image.get("is_new", False)
             
             # If the image was NOT just downloaded, try reading from JSON first
             if not is_new_image and os.path.exists(json_file_path):
                try:
                    with open(json_file_path, 'r', encoding='utf-8') as f:
                        saved_data = json.load(f)
                        if "data" in saved_data and len(saved_data["data"]) > 0:
                            events_data = saved_data["data"]
                            need_ocr = False
                            logging.info(f"[Kalender] Data loaded from {json_file_path}")
                except Exception as e:
                    logging.warning(f"Gagal membaca json kalender: {e}")
             
             if need_ocr:
                 # Proses gambar dengan EasyOCR dan OpenCV
                 events_data = parse_kalender_image_with_ocr(last_image_path, filename=last_image["filename"])
                 
                 # Save to JSON
                 try:
                     with open(json_file_path, 'w', encoding='utf-8') as f:
                         json.dump({
                             "metadata": {
                                 "last_scraped": datetime.now().strftime("%A, %d %B %Y %H:%M:%S"),
                                 "total_jadwal": len(events_data)
                             },
                             "data": events_data
                         }, f, indent=4)
                     logging.info(f"[Kalender] Data saved to {json_file_path}")
                 except Exception as e:
                     logging.error(f"Gagal menyimpan json kalender: {e}")
        else:
            events_data = []

        result = {
            "success": True,
            "semester": semester_aktif,
            "images": images,
            "events": events_data
        }
        
        # Simpan ke cache
        _kalender_cache_data = result
        _kalender_cache_time = now
        return result

    except Exception as e:
        logging.error(f"[Kalender] Error scrape kalender: {e}")
        events_data = []
        if os.path.exists(json_file_path):
             try:
                 with open(json_file_path, 'r', encoding='utf-8') as f:
                     saved_data = json.load(f)
                     if "data" in saved_data and len(saved_data["data"]) > 0:
                          events_data = saved_data["data"]
             except Exception:
                 pass
        return {"success": False, "message": str(e), "images": [], "semester": "", "events": events_data}

def parse_kalender_image_with_ocr(image_path, filename=""):
    """
    Ekstrak data kalender secara visual realtime menggunakan OpenCV dan EasyOCR.
    """
    base_year = 2026
    start_month = 2
    
    if filename:
        match = re.search(r'akd-(\d{2})(\d)', filename)
        if match:
            year_prefix = int(match.group(1))
            sem_type = int(match.group(2))
            
            if sem_type == 1: # Gasal
                base_year = 2000 + year_prefix
                start_month = 8
            elif sem_type == 2: # Genap
                base_year = 2000 + year_prefix + 1
                start_month = 2

    try:
        import cv2
        import numpy as np
        import easyocr
    except ImportError:
        logging.error("[OCR] Library OpenCV atau EasyOCR belum terinstall. Menggunakan fallback statis.")
        return []

    try:
        logging.info(f"[OCR] Memulai proses ekstraksi realtime pada: {image_path}")
        img = cv2.imread(image_path)
        if img is None:
            logging.error(f"[OCR] Gagal memuat gambar: {image_path}")
            return []
            
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # Inisialisasi OCR hanya untuk membaca angka tanggal
        reader = easyocr.Reader(['en'], gpu=True, verbose=False)
        results = reader.readtext(img, allowlist='0123456789')
        
        def get_mask(hsv_img, lower, upper):
            return cv2.inRange(hsv_img, lower, upper)
            
        tailwind_classes = {
            'Herregistrasi & Perwalian': ('bg-emerald-500/20 text-emerald-300 border-emerald-500/30', 'fa-clipboard-list'),
            'Perubahan KRS': ('bg-emerald-500/20 text-emerald-300 border-emerald-500/30', 'fa-clipboard-list'),
            'Pembatalan KRS': ('bg-emerald-500/20 text-emerald-300 border-emerald-500/30', 'fa-clipboard-list'),
            'Data KRS Tetap': ('bg-emerald-500/20 text-emerald-300 border-emerald-500/30', 'fa-clipboard-list'),
            'Batas Pengajuan Cuti': ('bg-emerald-500/20 text-emerald-300 border-emerald-500/30', 'fa-clipboard-list'),
            'Pelaksanaan Praktikum': ('bg-blue-500/20 text-blue-300 border-blue-500/30', 'fa-flask'),
            'Pengumuman Nilai': ('bg-emerald-500/20 text-emerald-300 border-emerald-500/30', 'fa-clipboard-list'),
            'Pengumuman Presensi': ('bg-emerald-500/20 text-emerald-300 border-emerald-500/30', 'fa-clipboard-list'),
            'Ujian Praktikum': ('bg-amber-500/20 text-amber-300 border-amber-500/30', 'fa-edit'),
            'UTS / UAS': ('bg-amber-500/20 text-amber-300 border-amber-500/30', 'fa-edit'),
            'Pengumuman Yudisium': ('bg-emerald-500/20 text-emerald-300 border-emerald-500/30', 'fa-clipboard-list'),
            'Hari Tenang': ('bg-blue-500/20 text-blue-300 border-blue-500/30', 'fa-book'),
            'Libur Semester': ('bg-red-500/20 text-red-300 border-red-500/30', 'fa-star'),
            'Libur Nasional': ('bg-red-500/20 text-red-300 border-red-500/30', 'fa-star'),
            'Daftar Sidang TA Akhir': ('bg-purple-500/20 text-purple-300 border-purple-500/30', 'fa-graduation-cap'),
            'Dies Natalis': ('bg-purple-500/20 text-purple-300 border-purple-500/30', 'fa-graduation-cap'),
            'Wisuda': ('bg-purple-500/20 text-purple-300 border-purple-500/30', 'fa-graduation-cap'),
            'Hari Upacara': ('bg-purple-500/20 text-purple-300 border-purple-500/30', 'fa-graduation-cap'),
            'Kelengkapan Yudisium Akhir': ('bg-emerald-500/20 text-emerald-300 border-emerald-500/30', 'fa-clipboard-list'),
            'KRS / Revisi': ('bg-emerald-500/20 text-emerald-300 border-emerald-500/30', 'fa-clipboard-list')
        }

        extracted_events = []
        width = img.shape[1]
        table_start_x = int(width * 0.1)
        table_end_x = int(width * 0.95)
        table_width = table_end_x - table_start_x
        
        for (bbox, text, prob) in results:
            if not text.isdigit(): continue
            date_num = int(text)
            if not (1 <= date_num <= 31): continue
            
            x_center = int((bbox[0][0] + bbox[2][0]) / 2)
            y_center = int((bbox[0][1] + bbox[2][1]) / 2)
            
            if x_center < table_start_x or x_center > table_end_x:
                continue
            
            y1, y2 = max(0, y_center-15), min(img.shape[0], y_center+15)
            x1, x2 = max(0, x_center-15), min(img.shape[1], x_center+15)
            roi_hsv = hsv[y1:y2, x1:x2]
            
            if roi_hsv.size == 0: continue
            
            red_mask = get_mask(roi_hsv, np.array([0, 150, 150]), np.array([10, 255, 255])) | \
                       get_mask(roi_hsv, np.array([170, 150, 150]), np.array([179, 255, 255]))
            pink_mask = get_mask(roi_hsv, np.array([140, 50, 150]), np.array([170, 150, 255]))
            yellow_mask = get_mask(roi_hsv, np.array([20, 150, 200]), np.array([35, 255, 255]))
            light_blue_mask = get_mask(roi_hsv, np.array([90, 100, 150]), np.array([110, 255, 255]))
            dark_blue_mask = get_mask(roi_hsv, np.array([100, 150, 100]), np.array([130, 255, 255]))
            dark_green_mask = get_mask(roi_hsv, np.array([40, 150, 100]), np.array([80, 255, 200]))
            light_green_mask = get_mask(roi_hsv, np.array([40, 100, 150]), np.array([80, 200, 255]))
            purple_mask = get_mask(roi_hsv, np.array([130, 150, 100]), np.array([160, 255, 255]))
            light_purple_mask = get_mask(roi_hsv, np.array([130, 20, 200]), np.array([160, 100, 255]))
            brown_gray_mask = get_mask(roi_hsv, np.array([0, 0, 50]), np.array([180, 50, 150]))
            brown_mask = get_mask(roi_hsv, np.array([10, 50, 150]), np.array([25, 150, 255]))
            
            total_px = roi_hsv.shape[0] * roi_hsv.shape[1]
            if total_px == 0: continue
            
            red_ratio = np.count_nonzero(red_mask) / total_px
            pink_ratio = np.count_nonzero(pink_mask) / total_px
            yellow_ratio = np.count_nonzero(yellow_mask) / total_px
            light_blue_ratio = np.count_nonzero(light_blue_mask) / total_px
            dark_blue_ratio = np.count_nonzero(dark_blue_mask) / total_px
            dark_green_ratio = np.count_nonzero(dark_green_mask) / total_px
            light_green_ratio = np.count_nonzero(light_green_mask) / total_px
            purple_ratio = np.count_nonzero(purple_mask) / total_px
            light_purple_ratio = np.count_nonzero(light_purple_mask) / total_px
            brown_gray_ratio = np.count_nonzero(brown_gray_mask) / total_px
            brown_ratio = np.count_nonzero(brown_mask) / total_px
            
            detected_evt = None
            
            if red_ratio > 0.4: detected_evt = 'Libur Nasional'
            elif yellow_ratio > 0.4: detected_evt = 'Libur Semester'
            elif light_blue_ratio > 0.4: detected_evt = 'UTS / UAS'
            elif dark_green_ratio > 0.4: detected_evt = 'Pengumuman Yudisium'
            elif light_purple_ratio > 0.4: detected_evt = 'Hari Tenang'
            elif brown_gray_ratio > 0.4: detected_evt = 'Kelengkapan Yudisium Akhir'
            
            if detected_evt is None:
                h, w = roi_hsv.shape[0], roi_hsv.shape[1]
                h2, w2 = h//2, w//2
                if h2 > 0 and w2 > 0:
                    red_top_right = np.count_nonzero(red_mask[0:h2, w2:w]) / (h2 * (w-w2) + 1)
                    yellow_top_left = np.count_nonzero(yellow_mask[0:h2, 0:w2]) / (h2 * w2 + 1)
                    light_blue_bottom_right = np.count_nonzero(light_blue_mask[h2:h, w2:w]) / ((h-h2) * (w-w2) + 1)
                    
                    if red_top_right > 0.2: detected_evt = 'Data KRS Tetap'
                    elif yellow_top_left > 0.2: detected_evt = 'Dies Natalis'
                    elif light_blue_bottom_right > 0.2: detected_evt = 'Pengumuman Nilai'
                
            if detected_evt is None:
                h, w = roi_hsv.shape[0], roi_hsv.shape[1]
                center_red = np.count_nonzero(red_mask[h//4:3*h//4, w//4:3*w//4]) / ((h//2)*(w//2)+1)
                
                if red_ratio > 0.03:
                    corners_red = (np.count_nonzero(red_mask[0:5, 0:5]) + 
                                   np.count_nonzero(red_mask[0:5, -5:]) + 
                                   np.count_nonzero(red_mask[-5:, 0:5]) + 
                                   np.count_nonzero(red_mask[-5:, -5:]))
                    if center_red > 0.15: detected_evt = 'Batas Pengajuan Cuti'
                    elif center_red > 0.02 and corners_red < 5: detected_evt = 'Pembatalan KRS'
                    elif corners_red > 5: detected_evt = 'Perubahan KRS'
                    else: detected_evt = 'Ujian Praktikum'
                elif pink_ratio > 0.03: detected_evt = 'Herregistrasi & Perwalian'
                elif dark_blue_ratio > 0.03: detected_evt = 'Pengumuman Presensi'
                elif purple_ratio > 0.03: detected_evt = 'Daftar Sidang TA Akhir'
                elif light_green_ratio > 0.03: detected_evt = 'Hari Upacara'
                elif light_blue_ratio > 0.03: detected_evt = 'Wisuda'
                elif brown_ratio > 0.03: detected_evt = 'Pelaksanaan Praktikum'
            
            if detected_evt:
                col_width = table_width / 6.0
                rel_x = x_center - table_start_x
                col_index = min(5, max(0, int(rel_x / col_width)))
                
                current_month = start_month + col_index
                event_year = base_year
                if current_month > 12:
                    current_month -= 12
                    event_year += 1
                    
                date_str = f"{event_year}-{current_month:02d}-{date_num:02d}"
                color_class, icon = tailwind_classes.get(detected_evt, ('bg-gray-500/20 text-gray-300', 'fa-calendar'))
                
                is_duplicate = False
                for ev in extracted_events:
                    if ev['date'] == date_str and ev['title'] == detected_evt:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    extracted_events.append({
                        "date": date_str,
                        "title": detected_evt,
                        "color": color_class,
                        "icon": icon
                    })
                
        if len(extracted_events) == 0:
            logging.warning("[OCR] Tidak ada data signifikan yang terdeteksi, menggunakan fallback statis.")
            return []
            
        logging.info(f"[OCR] Selesai membaca gambar. {len(extracted_events)} event berhasil dideteksi realtime.")
        return extracted_events
        
    except Exception as e:
        logging.error(f"[OCR] Terjadi kesalahan fatal dalam mendeteksi: {e}")
        return []
    