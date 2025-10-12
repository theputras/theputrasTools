# scrapper_requests.py

import os
import requests
from bs4 import BeautifulSoup
import pandas as pd
from dotenv import load_dotenv
from urllib.parse import urljoin, urlparse, quote
import re
import json
from datetime import datetime, timedelta
import threading
import logging # Tambahkan import logging

load_dotenv()
USER = os.getenv("SICYCA_USER")
PASS = os.getenv("SICYCA_PASS")
if not USER or not PASS:
    raise SystemExit("Set SICYCA_USER dan SICYCA_PASS di .env")

TARGET_URL = "https://sicyca.dinamika.ac.id"
GATE_ROOT = "https://gate.dinamika.ac.id"
COOKIES_FILE = "cookies.json"

_session_lock = threading.Lock()
_authenticated_session = None

def save_cookies(session):
    data_to_save = { "cookies": session.cookies.get_dict(), "last_access_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S") }
    with open(COOKIES_FILE, 'w') as f:
        json.dump(data_to_save, f)
    logging.info("   --> Cookies baru berhasil disimpan ke cookies.json")

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

def check_session_validity(session):
    logging.info("   --> Memeriksa validitas sesi dengan mengakses Sicyca Dashboard...")
    dashboard_url = urljoin(TARGET_URL, "/dashboard")
    try:
        response = session.get(dashboard_url, allow_redirects=True, timeout=15)
        response.raise_for_status()
        if "/dashboard" in response.url:
            logging.info("   --> Sesi Sicyca masih valid.")
            return True
    except requests.RequestException: pass
    logging.warning("   --> Sesi Sicyca sudah tidak valid.")
    return False

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
        new_session = requests.Session()
        new_session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"})
        if load_cookies(new_session) and check_session_validity(new_session):
            logging.info("Membuat sesi global baru dari cookies file.")
            _authenticated_session = new_session
            return _authenticated_session
        logging.info("Memulai proses login baru untuk sesi global...")
        if login_gateDinamika(new_session):
            save_cookies(new_session)
            logging.info("   --> Membuat sesi bersih dan memuat cookies baru...")
            clean_session = requests.Session()
            clean_session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"})
            load_cookies(clean_session)
            _authenticated_session = clean_session
            return _authenticated_session
        logging.error("Gagal total mendapatkan sesi terotentikasi.")
        return None
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

def search_mahasiswa(query):
    logging.info(f"\n--- Memulai Pencarian Mahasiswa: '{query}' ---")
    sess = get_authenticated_session()
    if not sess: return pd.DataFrame()
    try:
        safe_query = quote(query)
        search_url = urljoin(TARGET_URL, f"/komunitas/mahasiswa/?q={safe_query}")
        resp_search = sess.get(search_url, timeout=30, headers={"Referer": TARGET_URL})
        resp_search.raise_for_status()
        soup = BeautifulSoup(resp_search.text, "lxml")
        text_node = soup.find(string=re.compile(r'Hasil Pencarian', re.IGNORECASE))
        target_div = text_node.find_parent("div", class_="tabletitle") if text_node else None
        if not target_div:
            logging.info("   --> Tidak ada hasil pencarian mahasiswa.")
            return pd.DataFrame()
        table = target_div.find_next("table", class_=re.compile(r"\bsicycatable\b"))
        if not table: raise Exception("Tabel hasil mahasiswa tidak ditemukan.")
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        rows = [[td.get_text(strip=True) for td in tr.find_all("td")] for tr in table.find_all("tr") if tr.find("td")]
        df_results = pd.DataFrame(rows, columns=headers)
        df_results.columns = df_results.columns.str.strip()
        logging.info(f"   --> Pencarian mahasiswa berhasil, {len(df_results)} data ditemukan.")
        return df_results
    except Exception as e:
        logging.error(f"Error saat mencari mahasiswa: {e}")
        return pd.DataFrame()

def search_staff(query):
    logging.info(f"\n--- Memulai Pencarian Staff: '{query}' ---")
    sess = get_authenticated_session()
    if not sess: return pd.DataFrame()
    try:
        safe_query = quote(query)
        search_url = urljoin(TARGET_URL, f"/komunitas/staff/?q={safe_query}")
        resp_search = sess.get(search_url, timeout=30, headers={"Referer": TARGET_URL})
        resp_search.raise_for_status()
        soup = BeautifulSoup(resp_search.text, "lxml")
        text_node = soup.find(string=re.compile(r'Hasil Pencarian', re.IGNORECASE))
        target_div = text_node.find_parent("div", class_="tabletitle") if text_node else None
        if not target_div:
            logging.info("   --> Tidak ada hasil pencarian staff.")
            return pd.DataFrame()
        table = target_div.find_next("table", class_=re.compile(r"\bsicycatable\b"))
        if not table: raise Exception("Tabel hasil staff tidak ditemukan.")
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        rows = [[td.get_text(strip=True) for td in tr.find_all("td")] for tr in table.find_all("tr") if tr.find("td")]
        df_results = pd.DataFrame(rows, columns=headers)
        df_results.columns = df_results.columns.str.strip()
        logging.info(f"   --> Pencarian staff berhasil, {len(df_results)} data ditemukan.")
        return df_results
    except Exception as e:
        logging.error(f"Error saat mencari staff: {e}")
        return pd.DataFrame()
        
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