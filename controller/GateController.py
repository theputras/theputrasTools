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
    Sesuai dengan konfigurasi di old-scrapper_requests.py
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
    })
    return s

def save_cookies(session, gate_user_id):
    logging.info(f"Menyimpan cookies untuk Gate User ID: {gate_user_id}...")
    try:
        ua = session.headers.get("User-Agent", "")
        # Simpan cookie jar ke database
        gate_session_model.save_cookies(gate_user_id, session, ua)
    except Exception as e:
        logging.error(f"Gagal save cookies: {e}")

def load_cookies(session, user_id):
    logging.info(f"Memuat cookies dari DB untuk User ID: {user_id}...")
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
    """
    Logika login yang disamakan dengan old-scrapper_requests.py
    Menangani redirect SSO dengan loop form parsing.
    """
    try:
        logging.info(f"1. [Login] Mengakses Gate ({GATE_ROOT}) untuk user: {gate_username}...")
        
        # 1. Buka Halaman Login
        r = session.get(f"{GATE_ROOT}/login", allow_redirects=True, timeout=30)
        
        # Cek jika ternyata sudah login (kadang redirect sso otomatis)
        if r.url.rstrip('/') == GATE_ROOT.rstrip('/') and "id=\"login-dropdown\"" not in r.text:
            logging.info("[Login Gate] Sesi masih aktif (Redirected to Dashboard).")
            return True

        soup = BeautifulSoup(r.text, "lxml")
        form = soup.find("form", id="gate-login-form") or soup.find("form")
        
        if not form:
            # Fallback check
            if "dashboard" in r.url: return True
            logging.error(f"[Login Gate] Form login tidak ditemukan.")
            return False

        action_url = urljoin(r.url, form.get("action") or r.url)
        payload = {inp.get("name"): inp.get("value", "") for inp in form.find_all("input") if inp.get("name")}
        
        # 2. Isi User/Pass
        # Mapping key input yang mungkin beda-beda
        if 'userid' in payload: payload['userid'] = gate_username
        elif 'username' in payload: payload['username'] = gate_username
        
        if 'password' in payload: payload['password'] = gate_password
        
        # Header Khusus Login (Origin & Referer WAJIB)
        headers = {
            "Origin": f"{urlparse(r.url).scheme}://{urlparse(r.url).netloc}",
            "Referer": r.url,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        logging.info("2. [Login] Mengirim kredensial...")
        resp = session.post(action_url, data=payload, headers=headers, allow_redirects=True, timeout=30)
        resp.raise_for_status()
        
        # 3. Handle SSO Redirects (Looping form post otomatis)
        # Ini meniru logika old-scrapper yang menangani "redirect sso"
        logging.info("3. [Login] Menangani alur redirect SSO...")
        html, cur_url = resp.text, resp.url
        
        for i in range(5):
            # Cek jika sudah masuk Sicyca atau Dashboard Gate
            if "sicyca.dinamika.ac.id" in cur_url or (GATE_ROOT in cur_url and "login" not in cur_url):
                # Double check content
                if 'id="login-dropdown"' not in html:
                    logging.info("   --> Login dan proses SSO berhasil.")
                    return True

            # Cari form redirect (biasanya hidden form untuk SSO)
            soup = BeautifulSoup(html, "lxml")
            form = soup.find("form")
            if not form: break # Tidak ada form lagi, berarti finish atau stuck
            
            action_url = urljoin(cur_url, form.get("action") or cur_url)
            payload2 = {inp.get("name"): inp.get("value", "") for inp in form.find_all("input") if inp.get("name")}
            
            # Post lanjutannya
            r2 = session.post(action_url, data=payload2, allow_redirects=True, timeout=30, headers={"Referer": cur_url})
            html, cur_url = r2.text, r2.url
            
        # Cek Final State
        if "sicyca.dinamika.ac.id" in cur_url or "dashboard" in cur_url:
            return True
        if cur_url.rstrip('/') == GATE_ROOT.rstrip('/') and 'id="login-dropdown"' not in html:
            return True

        logging.warning(f"[Login Gate] GAGAL. URL Akhir: {cur_url}")
        return False

    except Exception as e:
        logging.error(f"[Login Gate] Error: {e}")
        return False

def check_validity(session):
    """
    Cek validitas session. 
    Menggunakan logika SIMPLE dari old-scrapper_requests.py agar tidak false-negative.
    """
    dashboard_url = urljoin(TARGET_URL, "/dashboard")
    logging.info(f"   --> Memeriksa validitas sesi ke server: {dashboard_url}")
    
    try:
        # PENTING: JANGAN pakai custom header Referer di sini jika di old script tidak ada.
        # Biarkan request natural seperti browser refresh.
        response = session.get(dashboard_url, allow_redirects=True, timeout=15)
        
        final_url = response.url.lower()
        
        # 1. Indikator SUKSES: Masuk Sicyca
        if response.status_code == 200 and "/dashboard" in final_url and "sicyca" in final_url:
            return True

        # 2. Indikator SUKSES: Masuk Gate Dashboard (Induk Session Valid)
        # Terkadang sicyca redirect ke gate dashboard kalau belum ada session app sicyca, 
        # tapi session gate masih hidup. Ini dianggap valid karena next request akan auto-sso.
        if final_url.rstrip('/') == GATE_ROOT.rstrip('/'):
            if "login" not in final_url and 'id="login-dropdown"' not in response.text:
                logging.info("   --> Redirected ke Gate Dashboard (Valid).")
                return True

        # 3. Indikator GAGAL: Login Page
        if "login" in final_url or "Masuk ke Sistem" in response.text:
            logging.warning(f"   --> Session Invalid (Redirected to Login): {final_url}")
            return False
            
        # Fallback: Jika status 200 tapi URL aneh, anggap valid dulu biar gak logout paksa
        return True

    except Exception as e:
        logging.error(f"Error check validity: {e}")
        # Jika error koneksi, jangan return False (biar gak force logout user pas internet lemot)
        # Return True sementara (assume valid)
        return True

def get_authenticated_session(user_id):
    """
    Mengambil session valid untuk user_id (Auto-Login/Load DB).
    """
    global _active_sessions
    if not user_id: return None

    with _session_lock:
        now = time.time()
        user_data = _active_sessions.get(user_id)

        # 1. CEK MEMORI
        if user_data:
            session = user_data['session']
            last_check = user_data['last_check']
            
            # Cek interval 5 menit
            if now - last_check > VALIDITY_CHECK_INTERVAL:
                if not check_validity(session):
                    logging.info(f"Session Memori User {user_id} EXPIRED/INVALID.")
                    del _active_sessions[user_id]
                else:
                    user_data['last_check'] = now
                    return session
            else:
                return session

        # 2. BUAT SESSION & LOAD DB (Recovery saat Restart Flask)
        s = create_session_obj()
        gate_id, g_user, g_pass = gate_user_model.get_credentials_by_user_id(user_id)
        
        if not g_user:
            logging.warning(f"User ID {user_id} belum setup Gate.")
            return None

        # Coba restore dari DB
        if load_cookies(s, user_id):
            logging.info(f"Cookies User {user_id} dimuat dari DB. Melakukan validasi...")
            
            # Cek ke server apakah cookie DB ini masih sakti?
            if check_validity(s):
                logging.info(f"Session User {user_id} RESTORED dari Database & VALID.")
                _active_sessions[user_id] = {
                    'session': s, 'last_check': now, 'gate_user_id': gate_id
                }
                return s
            else:
                logging.info(f"Session User {user_id} dari DATABASE sudah kedaluwarsa.")
                s.cookies.clear() # Bersihkan sampah cookie lama
        
        # 3. LOGIN BARU (Jika DB kosong atau Expired)
        logging.info(f"Melakukan LOGIN ULANG ke Gate untuk User {user_id}...")
        
        if login_gateDinamika(s, g_user, g_pass):
            save_cookies(s, gate_id) # Simpan token baru yang segar
            _active_sessions[user_id] = {
                'session': s, 'last_check': now, 'gate_user_id': gate_id
            }
            return s
        
        return None

def reset_session_user(user_id):
    """
    Menghapus sesi scraper dari Memori DAN Database.
    """
    # 1. Hapus dari Memory (RAM)
    with _session_lock:
        if user_id in _active_sessions:
            del _active_sessions[user_id]
            logging.info(f"[Reset Session] Sesi memori User {user_id} dihapus.")

    # 2. Hapus dari Database (Disk/MySQL)
    try:
        if gate_session_model.delete_session_by_user_id(user_id):
            logging.info(f"[Reset Session] Sesi database User {user_id} berhasil dihapus.")
        else:
            logging.warning(f"[Reset Session] Gagal menghapus sesi database User {user_id} (Mungkin tidak ada).")
    except Exception as e:
        logging.error(f"[Reset Session] Error saat menghapus DB: {e}")

def get_session_status(user_id):
    if not user_id: return {"active": False, "message": "No User ID"}
    # Cek ringan tanpa request ke server (opsional)
    return {"active": True, "message": "Session Managed"}