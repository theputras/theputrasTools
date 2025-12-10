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
VALIDITY_CHECK_INTERVAL = 300 
PROXY_URL = os.getenv("HTTP_PROXY_URL")

_session_lock = threading.Lock()
_active_sessions = {} 

gate_user_model = GateUser()
gate_session_model = GateSession()

def create_session_obj():
    """
    Membuat objek session dengan retry dan proxy (jika ada).
    """
    logging.info("Membuat objek session baru...")
    s = requests.Session()
    retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    
    if PROXY_URL and len(PROXY_URL) > 5:
        s.proxies = { "http": PROXY_URL, "https": PROXY_URL }
    
    # Header Browser Lengkap (Penting buat nipu server)
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    })
    return s

def save_cookies(session, gate_user_id):
    logging.info(f"Menyimpan cookies untuk Gate User ID: {gate_user_id}...")
    try:
        ua = session.headers.get("User-Agent", "")
        gate_session_model.save_cookies(gate_user_id, session, ua)
    except Exception as e:
        logging.error(f"Gagal save cookies: {e}")

def load_cookies(session, user_id):
    logging.info(f"Memuat cookies untuk User ID: {user_id}...")
    try:
        cookie_jar = gate_session_model.load_cookies(user_id)
        if cookie_jar:
            session.cookies.update(cookie_jar)
            return True
        return False
    except Exception as e:
        logging.error(f"Gagal load cookies: {e}")
        return False

def login_gateDinamika(session, gate_username, gate_password):
    try:
        logging.info(f"[Login Gate] Login baru untuk user: {gate_username}...")
        
        # 1. GET Login Page
        r = session.get(f"{GATE_ROOT}/login", allow_redirects=True, timeout=30)
        
        # Cek kalau ternyata sudah login (Redirected ke Dashboard)
        # Indikator: URL root DAN tidak ada form login
        if r.url.rstrip('/') == GATE_ROOT.rstrip('/') and "id=\"login-dropdown\"" not in r.text:
            logging.info("[Login Gate] Sesi masih aktif. Login dianggap SUKSES.")
            return True

        soup = BeautifulSoup(r.text, "lxml")
        form = soup.find("form", id="gate-login-form")
        if not form: form = soup.find("form", id="gate-login-form-2")
        
        if not form:
            logging.error(f"[Login Gate] Form login tidak ditemukan.")
            return False

        action_url = urljoin(r.url, form.get("action") or r.url)
        payload = {inp.get("name"): inp.get("value", "") for inp in form.find_all("input") if inp.get("name")}
        
        # 2. Isi Kredensial (userid & password)
        payload['userid'] = gate_username
        payload['password'] = gate_password
        if 'username' in payload: del payload['username']

        # 3. Header Khusus POST (Origin & Referer WAJIB)
        post_headers = {
            "Origin": "https://gate.dinamika.ac.id",
            "Referer": r.url,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        # 4. POST Login
        resp = session.post(action_url, data=payload, headers=post_headers, allow_redirects=True, timeout=30)
        
        # 5. Validasi Hasil
        final_url = resp.url.lower()
        html_content = resp.text

        # Jika sukses masuk Sicyca atau Dashboard
        if "sicyca.dinamika.ac.id" in final_url or "dashboard" in final_url:
             logging.info(f"[Login Gate] SUKSES! Masuk ke: {resp.url}")
             return True
        
        # Cek Dashboard Gate (root url)
        if final_url.rstrip('/') == GATE_ROOT.rstrip('/'):
            # Cek apakah masih ada tombol login?
            if 'id="login-dropdown"' in html_content:
                logging.warning("[Login Gate] GAGAL. Masih ada tombol LOGIN di homepage.")
                return False
            else:
                logging.info("[Login Gate] SUKSES. Masuk Dashboard Gate.")
                return True

        logging.warning(f"[Login Gate] GAGAL. URL Akhir: {resp.url}")
        return False

    except Exception as e:
        logging.error(f"[Login Gate] Error: {e}")
        return False

def check_validity(session):
    """
    Cek apakah session valid.
    FIX: Mengecek ke Gate Dashboard & Mengizinkan Redirect (SSO Friendly).
    """
    try:
        # Cek langsung ke "Pusat" (Gate), karena kalau Gate login, Sicyca pasti login.
        dashboard_url = f"{TARGET_URL}/dashboard" 
        logging.info(f"Memeriksa validitas session dengan mengakses: {dashboard_url}")
        
        # PENTING: allow_redirects=True agar tidak error saat SSO oper-operan
        response = session.get(dashboard_url, allow_redirects=True, timeout=20)
        
        final_url = response.url.lower()
        
        # 1. Indikator SUKSES: Masuk Sicyca
        if TARGET_URL in final_url:
            return True

        # 2. Indikator SUKSES: Masuk Gate Dashboard (Sesi hidup, tapi mungkin nyasar dikit)
        if final_url.rstrip('/') == GATE_ROOT.rstrip('/') or "dashboard" in final_url:
            # Pastikan bukan halaman login
            if "login" not in final_url and 'id="login-dropdown"' not in response.text:
                return True

        # 3. Indikator GAGAL: Terlempar ke Halaman Login Gate
        if GATE_ROOT in final_url and "login" in final_url:
            return False

        # 4. Fallback: Cek konten HTML jika URL-nya aneh
        if response.status_code == 200 and "Masuk ke Sistem" not in response.text:
            return True
            
        return False

    except Exception as e:
        logging.error(f"Error check validity: {e}")
        return False

def get_authenticated_session(user_id):
    """
    Mengambil session valid untuk user_id (Auto-Login/Load DB).
    """
    global _active_sessions
    logging.info(f"Mengambil session untuk User ID: {user_id}")
    if not user_id:
        return None

    with _session_lock:
        now = time.time()
        user_data = _active_sessions.get(user_id)

        # 1. CEK MEMORI (_active_sessions)
        if user_data:
            session = user_data['session']
            last_check = user_data['last_check']
            
            # Cek interval validitas
            if now - last_check > VALIDITY_CHECK_INTERVAL:
                # Jika sesi di memori sudah invalid
                if not check_validity(session):
                    logging.info(f"Session Memori User {user_id} EXPIRED. Menghapus dari memori.")
                    del _active_sessions[user_id]
                    # Lanjut ke langkah bawah (Buat Sesi Baru)
                else:
                    # Masih valid, update timer
                    user_data['last_check'] = now
                    return session
            else:
                return session

        # 2. BUAT OBJECT SESSION BARU
        s = create_session_obj()
        
        # Ambil credentials
        gate_id, g_user, g_pass = gate_user_model.get_credentials_by_user_id(user_id)
        if not g_user:
            logging.warning(f"User ID {user_id} belum setup Gate.")
            return None

        # 3. CEK DATABASE (Load Cookies)
        # Kita load dulu untuk melihat apakah masih bisa diselamatkan
        cookies_loaded = load_cookies(s, user_id)
        
        if cookies_loaded:
            if check_validity(s):
                logging.info(f"Session User {user_id} restored dari DB & VALID.")
                _active_sessions[user_id] = {
                    'session': s, 'last_check': now, 'gate_user_id': gate_id
                }
                return s
            else:
                logging.info(f"Session User {user_id} dari DATABASE EXPIRED.")
                # === PERBAIKAN DI SINI ===
                # Karena cookie DB expired, kita WAJIB membersihkannya sebelum login ulang.
                # Jika tidak, cookie lama akan bentrok dengan request login baru.
                s.cookies.clear() 
                logging.info(f"Cookies lama dibersihkan untuk login fresh.")
        
        # 4. LOGIN BARU (Fresh Login)
        logging.info(f"Melakukan LOGIN ULANG ke Gate untuk User {user_id}...")
        
        if login_gateDinamika(s, g_user, g_pass):
            # Simpan cookie baru ke DB
            save_cookies(s, gate_id) 
            
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
    logging.info(f"Memeriksa session User ID: {user_id}")
    if not user_id: return {"active": False, "message": "No User ID"}
    return {"active": True, "message": "Session Valid"} if get_authenticated_session(user_id) else {"active": False, "message": "Invalid"}