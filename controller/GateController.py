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
# VALIDITY_CHECK_INTERVAL = 300 
PROXY_URL = os.getenv("HTTP_PROXY_URL")

_session_lock = threading.Lock()
_active_sessions = {} 

gate_user_model = GateUser()
gate_session_model = GateSession()

def create_session_obj():
    """
    Membuat objek session dengan retry dan proxy.
    """
    logging.info("Membuat objek session baru...")
    s = requests.Session()
    retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    
    if PROXY_URL and len(PROXY_URL) > 5:
        s.proxies = { "http": PROXY_URL, "https": PROXY_URL }
    
    # Header Default
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Connection": "keep-alive"
    })
    return s

def save_cookies(session, gate_user_id):
    """
    Menyimpan cookies ke DB. 
    FIX: Mengambil dictionary cookies, bukan objek session utuh.
    """
    logging.info(f"Menyimpan cookies untuk Gate User ID: {gate_user_id}...")
    try:
        ua = session.headers.get("User-Agent", "")
        # Konversi CookieJar ke Dictionary agar mudah disimpan JSON/Text di DB
        cookies_dict = session.cookies.get_dict()
        
        # Pastikan model menerima (user_id, dict_cookies, user_agent)
        gate_session_model.save_cookies(gate_user_id, cookies_dict, ua)
    except Exception as e:
        logging.error(f"Gagal save cookies: {e}")

def load_cookies(session, user_id):
    """
    Memuat cookies dari DB.
    FIX: Mengembalikan juga User-Agent agar konsisten.
    """
    logging.info(f"Memuat cookies dari DB untuk User ID: {user_id}...")
    try:
        # Asumsi model return tuple/dict: (cookie_jar, user_agent) atau hanya cookie_jar
        # Sesuaikan dengan return model kamu. 
        # Jika model.load_cookies return dict cookies langsung:
        result = gate_session_model.load_cookies(user_id)
        
        if result:
            # Handling jika result berisi UA juga (tergantung implementasi model)
            if isinstance(result, tuple) and len(result) == 2:
                cookie_data, saved_ua = result
                if saved_ua:
                    session.headers.update({"User-Agent": saved_ua})
            else:
                cookie_data = result

            if cookie_data:
                session.cookies.update(cookie_data)
                return True
        return False
    except Exception as e:
        logging.error(f"Gagal load cookies: {e}")
        return False

def login_gateDinamika(session, gate_username, gate_password):
    try:
        logging.info(f"1. [Login] Mengakses Gate untuk user: {gate_username}...")
        
        # Reset header referer/origin biar bersih
        session.headers.pop("Origin", None)
        session.headers.pop("Referer", None)

        r = session.get(f"{GATE_ROOT}/login", allow_redirects=True, timeout=20)
        
        if r.url.rstrip('/') == GATE_ROOT.rstrip('/') and "id=\"login-dropdown\"" not in r.text:
            logging.info("[Login Gate] Sesi masih aktif (Redirected).")
            return True

        soup = BeautifulSoup(r.text, "lxml")
        form = soup.find("form", id="gate-login-form") or soup.find("form")
        
        if not form:
            if "dashboard" in r.url: return True
            logging.error(f"[Login Gate] Form login tidak ditemukan.")
            return False

        action_url = urljoin(r.url, form.get("action") or r.url)
        payload = {inp.get("name"): inp.get("value", "") for inp in form.find_all("input") if inp.get("name")}
        
        if 'userid' in payload: payload['userid'] = gate_username
        elif 'username' in payload: payload['username'] = gate_username
        if 'password' in payload: payload['password'] = gate_password
        
        headers = {
            "Origin": f"{urlparse(r.url).scheme}://{urlparse(r.url).netloc}",
            "Referer": r.url,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        logging.info("2. [Login] Mengirim kredensial...")
        resp = session.post(action_url, data=payload, headers=headers, allow_redirects=True, timeout=20)
        resp.raise_for_status()
        
        # Cek Salah Password Dini
        if "These credentials do not match our records" in resp.text:
            logging.warning("[Login Gate] Password Salah!")
            return False

        logging.info("3. [Login] Menangani alur redirect SSO...")
        html, cur_url = resp.text, resp.url
        
        for i in range(5):
            if "sicyca.dinamika.ac.id" in cur_url or (GATE_ROOT in cur_url and "login" not in cur_url):
                if 'id="login-dropdown"' not in html:
                    # PENTING: Lakukan satu request ke dashboard Sicyca untuk 'finalisasi' cookie
                    # Karena kadang cookie aplikasi belum set kalau cuma sampai gate dashboard
                    session.get(f"{TARGET_URL}/dashboard", timeout=10)
                    logging.info("   --> Login SSO sukses.")
                    return True

            soup = BeautifulSoup(html, "lxml")
            form = soup.find("form")
            if not form: break
            
            action_url = urljoin(cur_url, form.get("action") or cur_url)
            payload2 = {inp.get("name"): inp.get("value", "") for inp in form.find_all("input") if inp.get("name")}
            
            # Request SSO berikutnya
            r2 = session.post(action_url, data=payload2, allow_redirects=True, timeout=20, headers={"Referer": cur_url})
            html, cur_url = r2.text, r2.url
            
        if "sicyca" in cur_url or "dashboard" in cur_url:
            return True
        
        logging.warning(f"[Login Gate] GAGAL. URL Akhir: {cur_url}")
        return False

    except Exception as e:
        logging.error(f"[Login Gate] Error: {e}")
        return False

def check_validity(session):
    """
    Cek validitas session dengan penanganan error jaringan yang lebih aman.
    """
    dashboard_url = urljoin(TARGET_URL, "/dashboard")
    logging.info(f"   --> Memeriksa validitas sesi ke: {dashboard_url}")
    
    try:
        # Timeout diperpendek untuk validasi biar gak lemot
        response = session.get(dashboard_url, allow_redirects=True, timeout=10)
        final_url = response.url.lower()
        
        # 1. SUKSES Sicyca
        if response.status_code == 200 and "sicyca" in final_url and "login" not in final_url:
            return True

        # 2. SUKSES Gate Dashboard (Valid tapi belum masuk app)
        if final_url.rstrip('/') == GATE_ROOT.rstrip('/') and "login" not in final_url:
            return True

        # 3. GAGAL (Pasti)
        if "login" in final_url or "masuk ke sistem" in response.text.lower():
            logging.warning(f"   --> Session Invalid (Redirect login).")
            return False
            
        return True

    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
        # Kalau timeout/koneksi putus, ANGGAP TRUE dulu agar tidak logout user.
        # Nanti saat scraping data asli akan retry otomatis.
        logging.warning("   --> Gagal koneksi saat validasi (Asumsi Valid).")
        return True
    except Exception as e:
        logging.error(f"Error check validity: {e}")
        return False

# def get_authenticated_session(user_id):
#     """
#     Main Logic: Memory -> DB -> Login
#     """
#     global _active_sessions
#     if not user_id: return None

#     with _session_lock:
#         now = time.time()
#         user_data = _active_sessions.get(user_id)

#         # 1. CEK MEMORI
#         if user_data:
#             session = user_data['session']
#             if now - user_data['last_check'] > VALIDITY_CHECK_INTERVAL:
#                 if not check_validity(session):
#                     logging.info(f"Session User {user_id} EXPIRED.")
#                     del _active_sessions[user_id]
#                 else:
#                     user_data['last_check'] = now
#                     return session
#             else:
#                 return session

#         # 2. RESTORE DARI DB
#         s = create_session_obj()
#         gate_id, g_user, g_pass = gate_user_model.get_credentials_by_user_id(user_id)
        
#         if not g_user:
#             return None

#         if load_cookies(s, user_id):
#             logging.info(f"Validasi cookies DB User {user_id}...")
#             if check_validity(s):
#                 logging.info("Session DB Valid.")
#                 _active_sessions[user_id] = {'session': s, 'last_check': now, 'gate_user_id': gate_id}
#                 return s
#             else:
#                 logging.info("Session DB Invalid/Expired.")
#                 s = create_session_obj() # Bikin baru, yang lama sudah kotor

#         # 3. LOGIN BARU
#         logging.info(f"Login ulang User {user_id}...")
#         if login_gateDinamika(s, g_user, g_pass):
#             save_cookies(s, gate_id) # Simpan versi fresh
#             _active_sessions[user_id] = {'session': s, 'last_check': now, 'gate_user_id': gate_id}
#             return s
        
#         return None

def get_authenticated_session(user_id):
    """
    Mengambil session valid. 
    REVISI: SELALU cek validitas ke URL (sicyca/gate). 
    Tidak ada lagi pengecekan tanggal/waktu (VALIDITY_CHECK_INTERVAL dihapus).
    """
    global _active_sessions
    if not user_id: return None

    with _session_lock:
        user_data = _active_sessions.get(user_id)

        # 1. CEK MEMORI
        if user_data:
            session = user_data['session']
            
            # --- PERUBAHAN DI SINI ---
            # Kita HAPUS "if now - last_check > INTERVAL".
            # Kita GANTI dengan: Selalu cek ke server.
            # Ini menjawab request: "Cuma pengecekkan di sicyca/gate dashboard"
            
            if check_validity(session):
                # Valid -> Pakai
                return session
            else:
                # Invalid -> Hapus dari memori & lanjut ke DB/Login ulang
                logging.info(f"Session Memori User {user_id} INVALID (Tes URL Gagal).")
                del _active_sessions[user_id]

        # 2. BUAT SESSION & LOAD DB
        s = create_session_obj()
        gate_id, g_user, g_pass = gate_user_model.get_credentials_by_user_id(user_id)
        
        if not g_user:
            logging.warning(f"User ID {user_id} belum setup Gate.")
            return None

        # Coba restore dari DB
        if load_cookies(s, user_id):
            logging.info(f"Cookies User {user_id} dimuat dari DB. Melakukan validasi URL...")
            
            # Cek ke server apakah cookie DB ini masih sakti?
            if check_validity(s):
                logging.info(f"Session User {user_id} RESTORED dari Database & VALID.")
                _active_sessions[user_id] = {
                    'session': s, 'gate_user_id': gate_id
                }
                return s
            else:
                logging.info(f"Session User {user_id} dari DATABASE sudah kedaluwarsa.")
                s.cookies.clear() 
        
        # 3. LOGIN BARU
        logging.info(f"Melakukan LOGIN ULANG ke Gate untuk User {user_id}...")
        
        if login_gateDinamika(s, g_user, g_pass):
            save_cookies(s, gate_id) 
            _active_sessions[user_id] = {
                'session': s, 'gate_user_id': gate_id
            }
            return s
        
        return None

def gate_sso_launch(user_id, target_url):
    """
    Browser-side Gate Login:
    1. Ambil CSRF token dari gate.dinamika.ac.id/login
    2. Ambil kredensial asli user dari DB (dekripsi)
    3. Return data form untuk auto-submit dari browser ke Gate
    
    Browser yang POST langsung ke Gate → Gate set SSO_TOKEN cookie → 
    Semua app kampus bisa diakses.
    
    Returns:
        dict: {"csrf_token", "userid", "password", "target_url"} atau None
    """
    if not user_id:
        return None
    
    try:
        # 1. Ambil kredensial dari DB
        gate_id, gate_username, gate_password = gate_user_model.get_credentials_by_user_id(user_id)
        
        if not gate_username or not gate_password:
            logging.warning(f"[SSO Launch] Kredensial Gate tidak ditemukan untuk User {user_id}")
            return None
        
        # 2. Fetch CSRF token dari Gate login page
        logging.info(f"[SSO Launch] Mengambil CSRF token dari Gate...")
        s = create_session_obj()
        r = s.get(f"{GATE_ROOT}/login", timeout=15)
        
        csrf_token = ""
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "lxml")
            token_input = soup.find("input", {"name": "_token"})
            if token_input:
                csrf_token = token_input.get("value", "")
            else:
                # Coba meta tag
                meta_token = soup.find("meta", {"name": "csrf-token"})
                if meta_token:
                    csrf_token = meta_token.get("content", "")
        
        if not csrf_token:
            logging.warning("[SSO Launch] CSRF token tidak ditemukan!")
            return None
        
        logging.info(f"[SSO Launch] CSRF token didapat. Menyiapkan form untuk User {user_id} → {target_url}")
        
        return {
            "csrf_token": csrf_token,
            "userid": gate_username,
            "password": gate_password,
            "target_url": target_url
        }
        
    except Exception as e:
        logging.error(f"[SSO Launch] Error: {e}")
        return None


def _build_gate_login_html(csrf_token, userid, password, target_url):
    """
    Membuat halaman HTML dengan form hidden yang auto-submit ke Gate login.
    Setelah Gate login sukses, JS redirect ke target app.
    Password di-sanitize untuk HTML attributes.
    """
    # Escape values untuk keamanan HTML attribute
    import html as html_mod
    safe_token = html_mod.escape(csrf_token, quote=True)
    safe_userid = html_mod.escape(userid, quote=True)
    safe_password = html_mod.escape(password, quote=True)
    safe_target = html_mod.escape(target_url, quote=True)
    
    return f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Menghubungkan ke Layanan Kampus...</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: #0f172a;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            color: #e2e8f0;
        }}
        .container {{
            text-align: center;
            padding: 2rem;
        }}
        .spinner {{
            width: 48px; height: 48px;
            border: 4px solid rgba(99, 102, 241, 0.2);
            border-top-color: #6366f1;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin: 0 auto 1.5rem;
        }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
        h2 {{ font-size: 1.25rem; font-weight: 600; margin-bottom: 0.5rem; }}
        p {{ font-size: 0.875rem; color: #94a3b8; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="spinner"></div>
        <h2>Sedang login ke Gate...</h2>
        <p>Kamu akan dialihkan ke layanan kampus.</p>
    </div>
    <form id="gate-login" method="POST" action="https://gate.dinamika.ac.id/login">
        <input type="hidden" name="_token" value="{safe_token}">
        <input type="hidden" name="userid" value="{safe_userid}">
        <input type="hidden" name="password" value="{safe_password}">
    </form>
    <script>
        // Auto-submit ke Gate, lalu nanti Gate redirect ke dashboard
        // Kita gak bisa kontrol redirect Gate, tapi SSO_TOKEN sudah ke-set
        document.getElementById('gate-login').submit();
    </script>
</body>
</html>"""


def reset_session_user(user_id):
    with _session_lock:
        if user_id in _active_sessions:
            del _active_sessions[user_id]
            
    try:
        gate_session_model.delete_session_by_user_id(user_id)
    except Exception:
        pass

def get_session_status(user_id):
    return {"active": True if user_id in _active_sessions else False}