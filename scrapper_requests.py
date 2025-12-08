# scrapper_requests.py

import os, json, time
import requests
from bs4 import BeautifulSoup
import pandas as pd
from dotenv import load_dotenv
from urllib.parse import urljoin, urlparse, quote
import re
from datetime import datetime, date, timedelta
import threading
import logging # Tambahkan import logging
from typing import List, Dict, Any, Optional
from zoneinfo import ZoneInfo
from requests.adapters import HTTPAdapter, Retry

load_dotenv()
USER = os.getenv("SICYCA_USER")
PASS = os.getenv("SICYCA_PASS")
if not USER or not PASS:
    raise SystemExit("Set SICYCA_USER dan SICYCA_PASS di .env")
# === ENV & TZ ===
TZ = os.getenv("TIMEZONE", "Asia/Jakarta")
JKT = ZoneInfo(TZ)
TARGET_URL = "https://sicyca.dinamika.ac.id"
GATE_ROOT = "https://gate.dinamika.ac.id"
COOKIES_FILE = "cookies.json"
API_SICYCA = "/sicyca_api.php"

# === STATE MANAGEMENT ===
_session_lock = threading.Lock()
_authenticated_session = None
_last_validity_check = 0  # Timestamp kapan terakhir kali cek ke /dashboard
VALIDITY_CHECK_INTERVAL = 300  # Cek validitas ke server max 5 menit sekali

# # === HTTP session (retry) ===
# _session = requests.Session()
# _retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[429, 500, 502, 503, 504])
# _session.mount("https://", HTTPAdapter(max_retries=_retries))
# _session.mount("http://", HTTPAdapter(max_retries=_retries))

# === Cache harian ===
_cache_data: Dict[str, Any] = {}
_cache_expire_at: float = 0.0

def create_session():
    """Membuat session baru dengan konfigurasi Retry dan Header standar."""
    s = requests.Session()
    retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
    })
    return s

def reset_session_memory():
    """Membersihkan sesi global di memori agar dipaksa login ulang/baca file."""
    global _authenticated_session, _last_validity_check
    with _session_lock:
        _authenticated_session = None
        _last_validity_check = 0
    logging.info("   --> [RESET] Memory sesi scraper telah dikosongkan.")

def _midnight_epoch() -> float:
    now = datetime.now(JKT)
    midnight_tomorrow = datetime(now.year, now.month, now.day, tzinfo=JKT) + timedelta(days=1)
    return midnight_tomorrow.timestamp()

def save_cookies(session):
    data_to_save = { 
    "cookies": session.cookies.get_dict(), 
    "last_access_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S") 
    }
    try:
        with open(COOKIES_FILE, 'w') as f:
            json.dump(data_to_save, f)
        logging.info("   --> Cookies baru berhasil disimpan ke cookies.json")
    except Exception as e:
            logging.error(f"   --> Gagal simpan cookies: {e}")

def load_cookies(session):
    if not os.path.exists(COOKIES_FILE): return False
    try:
        with open(COOKIES_FILE, 'r') as f:
            data = json.load(f)
            last_time = datetime.strptime(data['last_access_time'], "%Y-%m-%d %H:%M:%S")
            if (datetime.now() - last_time) > timedelta(minutes=30):
                logging.warning("   --> Cookies sudah kedaluwarsa.")
                return False
            session.cookies.update(data.get("cookies", {}))
            logging.info("   --> Cookies berhasil dimuat dari file.")
            return True
    except (json.JSONDecodeError, KeyError):
        logging.error("   --> Gagal memuat cookies.json, file rusak atau format salah.")
        return False

def check_session_validity(session, force_check=False):
    logging.info("   --> Memeriksa validitas sesi dengan mengakses Sicyca Dashboard...")
    global _last_validity_check
        
    now = time.time()
        # Jika belum 5 menit sejak cek terakhir, anggap masih valid (kecuali dipaksa)
    if not force_check and (now - _last_validity_check < VALIDITY_CHECK_INTERVAL):
            return True
    
    logging.info("   --> Memeriksa validitas sesi ke server...")
    dashboard_url = urljoin(TARGET_URL, "/dashboard")
    try:
            response = session.get(dashboard_url, allow_redirects=True, timeout=10)
            # Cek apakah URL akhir masih di dashboard (tidak terlempar ke login gate)
            if response.status_code == 200 and "/dashboard" in response.url:
                _last_validity_check = now
                return True
    except requests.RequestException: 
        pass

# GANTI FUNGSI LAMA DENGAN INI
# def check_session_validity(session):
#     logging.info("   --> Memeriksa validitas sesi dengan mengakses Sicyca Dashboard...")
#     dashboard_url = urljoin(TARGET_URL, "/dashboard")
#     try:
#         response = session.get(dashboard_url, allow_redirects=True, timeout=15)
#         response.raise_for_status()

#         # --- Cek yang DIBUAT LEBIH KETAT ---
#         parsed_url = urlparse(response.url)

#         # Cek domainnya (netloc) HARUS sicyca, BUKAN gate
#         is_sicyca_domain = "sicyca.dinamika.ac.id" in parsed_url.netloc
#         # Cek path-nya HARUS diawali /dashboard
#         is_dashboard_path = parsed_url.path.startswith("/dashboard")

#         # Kalo dua-duanya bener, baru valid
#         if is_sicyca_domain and is_dashboard_path:
#             logging.info("   --> Sesi Sicyca masih valid (di domain sicyca & path /dashboard).")
#             return True
#         else:
#             # Kalo di-redirect ke gate, itu pasti tidak valid
#             if "gate.dinamika.ac.id" in parsed_url.netloc:
#                 logging.warning(f"   --> Sesi tidak valid, di-redirect ke {response.url}")
#             else:
#                 logging.warning(f"   --> Sesi Sicyca tidak valid (URL akhir: {response.url}).")
#             return False

#     except requests.RequestException as e:
#         logging.error(f"   --> Error saat cek validitas: {e}")
#         pass # Lanjut ke return False

#     logging.warning("   --> Sesi Sicyca sudah tidak valid (RequestException).")
#     return False

def login_gateDinamika(session):
    try:
        logging.info("1. [Login] Mengakses Gate untuk mendapatkan form...")
        r = session.get(GATE_ROOT, allow_redirects=True, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        form = soup.find("form")
        if not form: raise Exception("Gagal menemukan form login.")
        action_url = urljoin(r.url, form.get("action") or r.url)
        payload = {inp.get("name"): inp.get("value", "") for inp in form.find_all("input") if inp.get("name")}
        user_keys, pass_keys = ["username", "user", "userid"], ["password", "pass"]
        for key in user_keys:
            if key in payload: payload[key] = USER
        for key in pass_keys:
            if key in payload: payload[key] = PASS
        headers = {"Referer": r.url, "Origin": f"{urlparse(r.url).scheme}://{urlparse(r.url).netloc}"}
        logging.info("2. [Login] Mengirim kredensial...")
        resp = session.post(action_url, data=payload, allow_redirects=True, timeout=30, headers=headers)
        resp.raise_for_status()
        logging.info("3. [Login] Menangani alur redirect SSO...")
        html, cur_url = resp.text, resp.url
        
        # Handle SSO Redirects
        for i in range(5):
            soup = BeautifulSoup(html, "lxml")
            form = soup.find("form")
            if not form: break
            action_url = urljoin(cur_url, form.get("action") or cur_url)
            payload2 = {inp.get("name"): inp.get("value", "") for inp in form.find_all("input") if inp.get("name")}
            r2 = session.post(action_url, data=payload2, allow_redirects=True, timeout=30, headers={"Referer": cur_url})
            r2.raise_for_status()
            html, cur_url = r2.text, r2.url
        if "sicyca.dinamika.ac.id" in cur_url or "gate.dinamika.ac.id" in cur_url:
            logging.info("   --> Login dan proses SSO berhasil.")
            return True
        else:
            raise Exception("Gagal mendarat di domain yang benar setelah SSO.")
    except Exception as e:
        logging.error(f"   --> Proses login gagal: {e}")
        return False

def get_authenticated_session():
    global _authenticated_session
    with _session_lock:
        if _authenticated_session and check_session_validity(_authenticated_session):
            logging.info("Menggunakan sesi global yang ada di memori.")
            return _authenticated_session
        
        # 2. Jika tidak ada, buat baru
        logging.info("Membuat sesi baru...")
        new_session = create_session()
        
        # 3. Coba load dari file cookies
        if load_cookies(new_session):
            # Paksa cek ke server karena kita baru muat dari file
            if check_session_validity(new_session, force_check=True):
                _authenticated_session = new_session
                return _authenticated_session
        
        # 4. Login ulang jika cookie file mati
        if login_gateDinamika(new_session):
            save_cookies(new_session) 
            _authenticated_session = new_session
            # Reset timer validitas agar tidak langsung dicek lagi
            global _last_validity_check
            _last_validity_check = time.time()
            return _authenticated_session
            
        return None

# Fungsi cek status sesi tanpa memicu login baru
def get_session_status():
    """
    Fungsi ringan untuk memeriksa status cookie yang tersimpan tanpa
    memicu login baru. Mengembalikan True jika valid, False jika tidak.
    """
    logging.info("Memulai pengecekan status sesi di latar belakang...")
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"})
    
    # Coba muat cookie dan periksa validitasnya
    if load_cookies(session) and check_session_validity(session):
        return True
    get_authenticated_session()
    return _authenticated_session is not None and check_session_validity(_authenticated_session)
    

def scrape_data():
    logging.info("\n--- Memulai Scraping Jadwal ---")
    sess = get_authenticated_session()
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

def scrape_krs():
    logging.info("\n--- Memulai Scraping KRS ---")
    sess = get_authenticated_session()
    if not sess: return pd.DataFrame()

    krs_url = urljoin(TARGET_URL, "/akademik/krs")
    try:
        resp = sess.get(krs_url, timeout=30, headers={"Referer": TARGET_URL})
        # if "gate.dinamika.ac.id" in resp.url or "/login" in resp.url:
        #     reset_session_memory()
        #     return pd.DataFrame()

        soup = BeautifulSoup(resp.text, "lxml")
        table = soup.find("table", id="tableView")
        # Fallback logic tetep sama...
        if not table:
             text_node = soup.find(string=re.compile(r'KARTU RENCANA STUDI', re.IGNORECASE))
             if text_node:
                target_div = text_node.find_parent("div", class_="tabletitle")
                if target_div: table = target_div.find_next("table")
        
        if not table: return pd.DataFrame()

        data = []
        rows = table.find_all("tr")
        
        for tr in rows:
            cols = tr.find_all("td")
            if not cols or len(cols) < 10: continue

            # --- UPDATE: AMBIL PARAMETER ONCLICK ---
            # Kita butuh 'mk', 'kls', 'grup' dari fungsi JS: showModal...(kelas, kode_mk, ...)
            # Contoh: showModalMatakuliah('P1','36934','Pemrograman Mobile Lanjut');
            
            param_mk = ""
            param_kls = ""
            param_grup = ""
            
            # Cari link di kolom Matakuliah (index 2)
            link_mk = cols[2].find("a")
            if link_mk and link_mk.get("onclick"):
                onclick_text = link_mk.get("onclick")
                # Regex untuk ambil argument di dalam tanda kutip
                # Matches: 'P1', '36934', ...
                args = re.findall(r"'([^']*)'", onclick_text)
                
                # Pola parameter sicyca biasanya: (kelas, mk, nama_mk) ATAU (kelas, mk, grup, nama_mk)
                # Kita coba ambil amannya
                if len(args) >= 2:
                    param_kls = args[0]
                    param_mk = args[1]
                # Kadang grup ada di arg ke-2 atau 3 tergantung fungsi, tapi MK & Kelas yg utama

            row_data = {
                "Hari": cols[0].get_text(strip=True),
                "Waktu": cols[1].get_text(strip=True),
                "Matakuliah": cols[2].get_text(strip=True),
                # Skip Brilian (Index 3)
                "Ruang": cols[4].get_text(strip=True),
                "SKS": cols[5].get_text(strip=True),
                "Nilai": cols[6].get_text(strip=True), 
                "Nilai Minimal": cols[7].get_text(strip=True),
                "Kehadiran": cols[8].get_text(strip=True),
                "Keterangan": cols[9].get_text(strip=True),
                
                # Tambahkan Hidden Params buat Frontend fetch detail
                "param_mk": param_mk,
                "param_kls": param_kls,
                "param_grup": param_grup 
            }
            data.append(row_data)

        df = pd.DataFrame(data)
        return df

    except Exception as e:
        logging.error(f"Error KRS: {e}")
        return pd.DataFrame()

def scrape_krs_detail(params: Dict[str, str]) -> Dict[str, Any]:
    """
    Mengambil detail KRS. Menangani struktur Tabel murni (Nilai/Kehadiran) 
    dan struktur Campuran (Matakuliah: Info Dosen + Tabel Peserta).
    """
    logging.info(f"\n--- Scraping KRS Detail: {params} ---")
    sess = get_authenticated_session()
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

def _generic_search(endpoint, query, label):
    """Helper function untuk search mhs/staff agar tidak duplikasi kode"""
    logging.info(f"\n--- Cari {label}: '{query}' ---")
    sess = get_authenticated_session()
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

def fetch_photo_from_sicyca(role, id_):
    """
    Fetch foto dari Sicyca menggunakan session authenticated.
    role: 'mahasiswa' atau 'staff'
    id_: NIM (untuk mahasiswa) atau NIK (untuk staff)
    Returns: bytes of image content, or None if failed.
    """
    sess = get_authenticated_session()
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
        
    
        
def fetch_data_ultah(force_refresh: bool = False) -> Dict[str, Any]:
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

    sess = get_authenticated_session()
    if not sess:
        raise Exception(status_code=401, detail="Gagal autentikasi ke Sicyca")

    # --- coba ambil CSRF token ---
    token = None

    # 2. Fallback: Parse dari Halaman (INI YANG DIGANTI)
    logging.info("Mencoba scrape global_token dari Halaman Dashboard Sicyca...")
    try:
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
    payload = {"nim": USER, "token": token, "ultah": True}
    logging.info("Memanggil API Sicyca untuk data ulang tahun...")
    logging.info(f"   --> API URL: {api_url}")
    logging.info(f"   --> Payload: nim={USER}, token={token}, ultah=True")
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

    # 3) simpan cache & return
    _cache_data = {
        "tanggal_hari_ini": now.strftime("%d %B %Y"),
        "jumlah": len(rows),
        "rows": rows
    }
    _cache_expire_at = _midnight_epoch()
    return _cache_data