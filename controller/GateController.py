# controller/GateController.py

import os
import time
import threading
import logging
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter, Retry
from urllib.parse import urljoin, urlparse

# Import Model
from models.gate import GateUser, GateSession

load_dotenv()

# Konfigurasi
GATE_ROOT = "https://gate.dinamika.ac.id"
TARGET_URL = "https://sicyca.dinamika.ac.id"
VALIDITY_CHECK_INTERVAL = 300  # 5 menit
PROXY_URL = os.getenv("HTTP_PROXY_URL")

# === GLOBAL STATE ===
_session_lock = threading.Lock()
_active_sessions = {} 

# Inisialisasi Model
gate_user_model = GateUser()
gate_session_model = GateSession()

def create_session_obj():
    """Membuat session request baru."""
    s = requests.Session()
    retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    
    if PROXY_URL:
        s.proxies = { "http": PROXY_URL, "https": PROXY_URL }
    
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
    })
    return s


def login_gateDinamika(session, gate_username, gate_password):
    """
    Melakukan login ke Gate Dinamika.
    FIX: Menangani kasus 'Already Logged In' agar tidak crash.
    """
    try:
        logging.info(f"[Login Gate] Mencoba login untuk user: {gate_username}...")
        
        # 1. GET Login Page
        r = session.get(f"{GATE_ROOT}/login", allow_redirects=True, timeout=30)
        
        # === FIX UTAMA: CEK JIKA SUDAH LOGIN ===
        # Jika server melempar kita ke Dashboard/Home, berarti kita sudah login.
        # URL biasanya 'https://gate.dinamika.ac.id/' atau ada kata 'dashboard'
        if r.url.rstrip('/') == GATE_ROOT.rstrip('/') or "dashboard" in r.url:
            logging.info("[Login Gate] Ternyata sesi masih aktif (Redirected ke Dashboard). Login dianggap SUKSES.")
            return True
        # =======================================

        r.raise_for_status()
        
        soup = BeautifulSoup(r.text, "lxml")
        
        # Cari form login
        form = soup.find("form", id="gate-login-form")
        if not form:
            form = soup.find("form", id="gate-login-form-2")
        
        if not form:
            # Fallback aman
            pwd_input = soup.find("input", {"type": "password"})
            if pwd_input:
                form = pwd_input.find_parent("form")
        
        if not form:
            # Debugging jika form benar-benar tidak ada dan bukan dashboard
            page_title = soup.title.string.strip() if soup.title else "No Title"
            logging.error(f"[Login Gate] Form login TIDAK DITEMUKAN. Title Halaman: '{page_title}'. URL: {r.url}")
            return False

        action_url = urljoin(r.url, form.get("action") or r.url)
        payload = {inp.get("name"): inp.get("value", "") for inp in form.find_all("input") if inp.get("name")}
        
        # Isi User & Pass
        payload['userid'] = gate_username
        payload['password'] = gate_password
        
        if 'username' in payload: del payload['username']

        headers = {
            "Referer": r.url, 
            "Origin": f"{urlparse(r.url).scheme}://{urlparse(r.url).netloc}",
            "User-Agent": session.headers['User-Agent']
        }
        
        # 3. POST Credentials
        resp = session.post(action_url, data=payload, allow_redirects=True, timeout=30, headers=headers)
        resp.raise_for_status()
        
        # 4. Handle Redirects
        html, cur_url = resp.text, resp.url
        for _ in range(5):
            # Cek Sukses Sicyca
            if "sicyca.dinamika.ac.id" in cur_url:
                logging.info(f"[Login Gate] SUKSES login (Sicyca). Redirect ke: {cur_url}")
                return True
                
            # Cek Sukses Dashboard Gate
            if cur_url.rstrip('/') == GATE_ROOT.rstrip('/') or "dashboard" in cur_url:
                 if "login" not in cur_url.lower(): # Pastikan bukan dashboard/login
                    logging.info(f"[Login Gate] SUKSES login (Gate). URL: {cur_url}")
                    return True

            # Cek Form Lanjutan (SSO/CAS)
            soup = BeautifulSoup(html, "lxml")
            form = soup.find("form")
            if not form: break 
            
            action_url = urljoin(cur_url, form.get("action") or cur_url)
            payload2 = {inp.get("name"): inp.get("value", "") for inp in form.find_all("input") if inp.get("name")}
            
            r2 = session.post(action_url, data=payload2, allow_redirects=True, timeout=30, headers={"Referer": cur_url})
            html, cur_url = r2.text, r2.url

        if "sicyca.dinamika.ac.id" in cur_url or "gate.dinamika.ac.id" in cur_url:
             if "login" not in cur_url.lower():
                logging.info(f"[Login Gate] SUKSES. URL Final: {cur_url}")
                return True
        
        logging.warning(f"[Login Gate] GAGAL. URL Final: {cur_url}")
        return False

    except Exception as e:
        logging.error(f"[Login Gate] Error Exception: {e}")
        return False


def check_validity(session):
    """Cek apakah session valid dengan menembak Dashboard."""
    try:
        dashboard_url = urljoin(TARGET_URL, "/dashboard")
        # Allow redirects False biar kita tau kalau dilempar (302) ke login
        response = session.get(dashboard_url, allow_redirects=False, timeout=10)
        
        # Jika status 302 dan header Location mengandung 'login' -> Expired
        if response.status_code in (302, 301):
            loc = response.headers.get("Location", "").lower()
            if "login" in loc:
                return False
                
        # Jika status 200 OK
        if response.status_code == 200:
            # Pastikan bukan halaman login yang statusnya 200
            if "Masuk ke Sistem" in response.text or "userid" in response.text:
                return False
            return True
            
        return False
    except Exception:
        return False

# === FUNGSI UTAMA (PUBLIC) ===

def get_authenticated_session(user_id):
    """
    ALUR KETAT:
    1. Cek Memori (_active_sessions). Valid? Return.
    2. Cek DB (gate_sessions). Ada? -> Load -> Valid? -> Return.
    3. Login Baru (Sicyca). Sukses? -> Simpan DB -> Return.
    """
    global _active_sessions

    if not user_id: return None

    with _session_lock:
        now = time.time()
        
        # 1. CEK MEMORI
        user_data = _active_sessions.get(user_id)
        if user_data:
            session = user_data['session']
            last_check = user_data['last_check']
            
            # Cek interval validitas
            if now - last_check > VALIDITY_CHECK_INTERVAL:
                if check_validity(session):
                    _active_sessions[user_id]['last_check'] = now
                    return session
                else:
                    logging.info(f"Session Memori User {user_id} EXPIRED. Menghapus dari memori.")
                    del _active_sessions[user_id]
                    # Lanjut ke langkah bawah (Cek DB / Login Ulang)
            else:
                return session

        # Buat session object baru
        s = create_session_obj()
        
        # Ambil data User Gate untuk persiapan (sekalian dapat gate_user_id)
        gate_id, g_user, g_pass = gate_user_model.get_credentials_by_user_id(user_id)
        if not g_user:
            logging.warning(f"User ID {user_id} belum setup Gate.")
            return None

        # 2. CEK DATABASE (Load Cookies)
        logging.info(f"Mengecek cookies di database untuk User {user_id}...")
        cookie_jar = gate_session_model.load_cookies(user_id)
        
        if cookie_jar:
            s.cookies.update(cookie_jar) # Pasang cookie
            if check_validity(s):
                logging.info(f"Session User {user_id} dari DATABASE VALID.")
                _active_sessions[user_id] = {
                    'session': s, 'last_check': now, 'gate_user_id': gate_id
                }
                return s
            else:
                logging.info(f"Session User {user_id} dari DATABASE EXPIRED.")
        
        # 3. LOGIN BARU (Login Ulang)
        logging.info(f"Melakukan LOGIN ULANG ke Gate untuk User {user_id}...")
        if login_gateDinamika(s, g_user, g_pass):
            # Login sukses -> Simpan cookie baru ke DB
            ua = s.headers.get("User-Agent", "")
            gate_session_model.save_cookies(gate_id, s, ua)
            
            _active_sessions[user_id] = {
                'session': s, 'last_check': now, 'gate_user_id': gate_id
            }
            return s
        
        return None

def reset_session_user(user_id):
    with _session_lock:
        if user_id in _active_sessions:
            del _active_sessions[user_id]

def get_session_status(user_id):
    if not user_id: return {"active": False, "message": "No User ID"}
    session = get_authenticated_session(user_id)
    if session:
        return {"active": True, "message": "Session Valid"}
    return {"active": False, "message": "Session Invalid"}