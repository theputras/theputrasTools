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
    Mengambil NIM (User Sicyca) dan Token (XSRF) untuk payload API.
    """
    # 1. Ambil NIM dari Database
    # Return: (id, gate_username, gate_password)
    _, nim, _ = gate_user_model.get_credentials_by_user_id(user_id)
    
    if not nim:
        logging.error(f"Gagal mengambil NIM untuk User ID {user_id}")
        return None, None

    # 2. Ambil Token dari Cookie (XSRF-TOKEN)
    # Token di cookie biasanya URL Encoded, jadi perlu di-unquote
    raw_token = session_obj.cookies.get("XSRF-TOKEN", "")
    token = unquote(raw_token) if raw_token else ""
    
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
    target_user = _get_current_user_id(user_id)
    
    # Loop Maksimal 2x (Percobaan 1 -> Gagal -> Reset Session -> Percobaan 2)
    for attempt in range(2):
        s = get_authenticated_session(target_user)
        if not s: 
            if attempt == 0: continue # Coba lagi (siapa tau glitch)
            return pd.DataFrame()

        try:
            logging.info(f"[KRS] Memulai Scraping KRS (Percobaan {attempt+1})...")
            
            # Request Halaman KRS
            url_krs = f"{TARGET_URL}/akademik/krs.php"
            r = s.get(url_krs, timeout=30)
            
            # Cek apakah terlempar ke Login?
            if "login" in r.url.lower() or "gate.dinamika.ac.id" in r.url.lower():
                raise Exception("Session expired (Redirected to Login)")

            soup = BeautifulSoup(r.text, "html.parser")
            
            # --- LOGIKA PARSING (Dari kode lama) ---
            # Cari tabel yang berisi jadwal/KRS
            # Biasanya tabel KRS ada class 'table-hover' atau 'table-striped'
            tabel = soup.find('table', class_='table-hover') 
            if not tabel:
                # Coba selector lain jika layout berubah
                tabel = soup.find('table', class_='table-striped')
            
            if not tabel:
                # Jika tabel tidak ketemu, mungkin session bermasalah?
                raise Exception("Tabel KRS tidak ditemukan (Mungkin session invalid)")

            # Parsing Data Tabel
            data_rows = []
            tbody = tabel.find('tbody')
            if tbody:
                tr_list = tbody.find_all('tr')
                for tr in tr_list:
                    tds = tr.find_all('td')
                    # Pastikan baris memiliki data (bukan header/kosong)
                    if len(tds) >= 7: 
                        # Contoh index (sesuaikan dengan kolom asli Sicyca):
                        # 0: No, 1: Kode, 2: Matakuliah, 3: SKS, 4: Kelas, 5: Hari, 6: Jam, 7: Ruang
                        row_data = {
                            "Kode": tds[1].get_text(strip=True),
                            "Matakuliah": tds[2].get_text(strip=True),
                            "SKS": tds[3].get_text(strip=True),
                            "Kelas": tds[4].get_text(strip=True),
                            "Hari": tds[5].get_text(strip=True),
                            "Jam": tds[6].get_text(strip=True),
                            "Ruang": tds[7].get_text(strip=True) if len(tds) > 7 else "-"
                        }
                        data_rows.append(row_data)
            
            # Jika berhasil dapat data, return langsung
            if data_rows:
                logging.info(f"[KRS] Berhasil ambil {len(data_rows)} data.")
                return pd.DataFrame(data_rows)
            else:
                # Tabel ada tapi kosong? (Mungkin emang gak ambil KRS)
                logging.warning("[KRS] Tabel ditemukan tapi data kosong.")
                return pd.DataFrame()

        except Exception as e:
            logging.warning(f"[KRS] Gagal Percobaan {attempt+1}: {e}")
            
            # === KUNCI PERBAIKAN: RESET SESSION ===
            # Jika gagal di percobaan pertama, kita HAPUS session dari memori
            # agar 'get_authenticated_session' dipaksa login ulang di loop berikutnya.
            if attempt == 0:
                logging.info(f"[KRS] Mereset session User {target_user} dan mencoba ulang...")
                reset_session_user(target_user)
                time.sleep(1) # Jeda dikit
            else:
                logging.error("[KRS] Gagal total setelah retry.")
                
    return pd.DataFrame()


def fetch_masa_studi(user_id=None) -> str:
    # Logic sama, tapi kalau bisa tambahkan retry juga
    target_user = _get_current_user_id(user_id)
    
    for attempt in range(2):
        s = get_authenticated_session(target_user)
        if not s: return "-"

        try:
            logging.info(f"--- Mengambil Data Masa Studi (Percobaan {attempt+1}) ---")
            nim, token = _get_api_params(target_user, s)
            if not nim: return "-"

            payload = {"nim": nim, "token": token, "masa_studi": True}
            
            r = s.post(f"{TARGET_URL}{API_SICYCA}", data=payload, timeout=10)
            
            if r.status_code == 200:
                try:
                    data = r.json()
                    res = data.get("masa_studi", "-") if isinstance(data, dict) else str(data)
                    logging.info(f"    --> Masa studi didapat: {res}")
                    return str(res)
                except:
                    return r.text.strip()
            
            # Jika gagal status code (misal 401/403/500)
            if attempt == 0:
                reset_session_user(target_user)
                
        except Exception as e:
            if attempt == 0:
                reset_session_user(target_user)
            else:
                logging.error(f"[Masa Studi] Error: {e}")
                
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
        
    
        
def fetch_data_ultah(force_refresh: bool = False, user_id=None) -> Dict[str, Any]:
    """
    Satu fungsi untuk:
    - call API SICYCA (pakai env SICYCA_USER & SICYCA_TOKEN)
    - normalisasi record (0/1/2/3 -> NIM/NAMA/PRODI/TANGGAL)
    - parse tanggal & hitung umur
    - filter ultah = hari ini
    - caching sampai 23:59:59 zona Asia/Jakarta
    """
    global _cache_data, _cache_expire_at

    now = datetime.now(JKT)
    today = now.date()

    if not force_refresh and time.time() <= _cache_expire_at and _cache_data:
        logging.info("Mengambil data ultah dari cache.")
        return _cache_data
    target_user = _get_current_user_id(user_id)
    sess = get_authenticated_session(target_user)
    if not sess:
        raise Exception(status_code=401, detail="Gagal autentikasi ke Sicyca")

    # --- coba ambil CSRF token ---
    token = None

    # 2. Fallback: Parse dari Halaman (INI YANG DIGANTI)
    logging.info("Mencoba scrape global_token dari Halaman Dashboard Sicyca...")
    try:
        # Ambil NIM dan Token
        nim, token = _get_api_params(target_user, sess)
        if not nim:
            return {"error": True, "message": "NIM tidak ditemukan", "rows": []}
        # Akses halaman utama Sicyca (TARGET_URL)
        r = sess.get(GATE_ROOT, timeout=15)
        r.raise_for_status()
        
        # Cari token-nya pakai Regex (var global_token = "...")
        match = re.search(r'var global_token\s*=\s*"([^"]+)"', r.text)
        
        if match:
            token = match.group(1)
            logging.info(f"   --> Global token (JS var) berhasil di-parse dari HTML.")
        else:
            # Fallback ke meta tag (jaga-jaga)
            meta_match = re.search(r'name="csrf-token"\s+content="([^"]+)"', r.text)
            if meta_match:
                token = meta_match.group(1)
                logging.info(f"   --> Global token (meta tag) berhasil di-parse.")
            else:
                logging.error("GAGAL! Tidak menemukan 'var global_token' atau 'meta csrf-token' di halaman.")
                # Simpan HTML untuk cek
                with open("debug_token_page.html", "w", encoding="utf-8") as f:
                    f.write(r.text)
                logging.error("HTML halaman disimpan ke debug_token_page.html")
                raise Exception("Tidak bisa menemukan token di halaman HTML.") 

    except Exception as e:
        logging.error(f"Error saat scraping token: {e}")
        raise Exception(status_code=500, detail=f"Gagal scrape token: {e}")


    if not token:
        raise Exception(status_code=403, detail="CSRF/Global token tidak ditemukan setelah scrape")

    # --- panggil API ---
    api_url = urljoin(TARGET_URL, API_SICYCA)
    payload = {"nim": nim, "token": token, "ultah": True}
    logging.info("Memanggil API Sicyca untuk data ulang tahun...")
    logging.info(f"   --> API URL: {api_url}")
    logging.info(f"   --> Payload: nim={nim}, token={token}, ultah=True")
    r = sess.post(api_url, data=payload, timeout=10)
    r.raise_for_status()

    try:
        data_json = r.json()
    except json.JSONDecodeError:
        raise Exception(status_code=502, detail="Invalid JSON dari Sicyca")

    raw_list = data_json.get("data", [])
    if not isinstance(raw_list, list):
        raw_list = []

    # helper lokal (biar satu fungsi)
    def parse_tanggal(s: str) -> Optional[date]:
        s = (s or "").strip()
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %m %Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return None

    def hitung_umur(tgl_lahir: date, today_: date) -> int:
        umur = today_.year - tgl_lahir.year
        if (today_.month, today_.day) < (tgl_lahir.month, tgl_lahir.day):
            umur -= 1
        return umur

    def map_record(raw: Dict[str, Any]) -> Dict[str, Any]:
        nim = raw.get("NIM") or raw.get("0") or ""
        nama = raw.get("NAMA") or raw.get("1") or ""
        prodi = raw.get("PRODI") or raw.get("2") or ""
        tanggal_str = raw.get("TANGGAL") or raw.get("3") or ""
        return {"nim": nim, "nama": nama, "prodi": prodi, "tanggal": tanggal_str}

    # 2) map & filter
    rows: List[Dict[str, Any]] = []
    for raw in raw_list:
        rec = map_record(raw)
        tgl = parse_tanggal(rec["tanggal"])
        if not tgl:
            continue
        if (tgl.month, tgl.day) == (today.month, today.day):
            rows.append({
                "nama": rec["nama"],
                "prodi": rec["prodi"],
                "tanggal_lahir": tgl.strftime("%d %B %Y"),
                "umur": hitung_umur(tgl, today)
            })
    result = {"message": f"{len(rows)} ulang tahun hari ini.","tanggal_hari_ini": now.strftime("%d %B %Y"), "rows": rows}
    return result