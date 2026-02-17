# app.py

import os
import re
import pandas as pd
from flask import Flask, send_from_directory, request, render_template, redirect, url_for, json, session, current_app, make_response, g, Response, flash, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from concurrent.futures import ThreadPoolExecutor
import logging
import pytz
import json
from datetime import datetime, timedelta
import time

import jwt
from connection import get_connection
# import base64  # Untuk encode image ke base64
from logging.handlers import RotatingFileHandler
from cachetools import TTLCache  # Install: pip install cachetools
from api.api import api_bp, init_api, SSKM_LAST_DUPLICATE
from models.auth_api import auth_bp
from flask_cors import CORS
from paymentGateway import payment_bp
from manajemenUltah import ultah_model, parse_tanggal_sicyca
from googleCalendar import google_cal_service
from cryptography.fernet import Fernet

# Impor SEMUA fungsi scraper
from scrapper_requests import scrape_data, search_mahasiswa, dahsboard_nilai, fetch_sks, fetch_sskm_data
from controller.GateController import reset_session_user
from middleware.auth_quard import login_required, check_permission
from werkzeug.middleware.proxy_fix import ProxyFix
from models.auth_api import _revoke_refresh_token, _revoke_all_user_sessions
from dotenv import load_dotenv
from models.gate import GateUser
from controller.LogbookController import (
    get_logbooks_by_user, get_logbook_by_id_and_user, create_logbook, update_logbook, 
    delete_logbook, get_entries_by_logbook, add_entry, delete_entry, generate_word,
    get_entry_by_id, update_entry # <--- TAMBAHIN INI DI IMPORTNYA
)
from controller.UserController import get_all_users, get_all_roles, create_user, change_user_role, update_user_detail, delete_user, reset_user_password, update_user_password
from models.auth_api import generate_access_token, generate_refresh_token
from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
    base64url_to_bytes
)
from webauthn.helpers.structs import (
    UserVerificationRequirement,
    AuthenticatorSelectionCriteria,
    AuthenticatorAttachment,
    ResidentKeyRequirement
)
import base64
from controller.WebAuthnController import save_credential, get_credentials_by_user, get_user_by_credential, update_sign_count


load_dotenv()  # biar bisa baca file .env

app = Flask(__name__)
CORS(app, supports_credentials=True)

# CORS(
#     app,
#     supports_credentials=True,
#     origins=[
#         "http://172.16.2.148:5000",
#         "http://localhost:5000"
#     ]
# )


app.register_blueprint(auth_bp, url_prefix='/api/auth')

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Register Payment Gateway Blueprint
app.register_blueprint(payment_bp)
# Inisialisasi scheduler SEKALI saat modul di-import
SCHEDULER_TZ = pytz.timezone(os.getenv("TIMEZONE"))


scheduler = BackgroundScheduler(timezone=SCHEDULER_TZ)

# ==================================================================
# === KONFIGURASI LOGGING ===
# ==================================================================
# Hapus handler default Flask agar tidak duplikat
app.logger.removeHandler(app.logger.handlers[0])

log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
log_file = 'app.log'
# Gunakan RotatingFileHandler untuk membatasi ukuran file log (5MB, 2 file backup)
file_handler = RotatingFileHandler(log_file, maxBytes=1024*1024*5, backupCount=2, encoding='utf-8')
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.INFO)

# Handler untuk menampilkan log di konsol terminal
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter)
stream_handler.setLevel(logging.INFO)

# Dapatkan root logger dan tambahkan handler-handler yang sudah dibuat
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)
# ==================================================================

# Setup cache untuk foto (TTL 30 detik, max 100 items)
photo_cache = TTLCache(maxsize=100, ttl=30)
logging.info(f"Scheduler timezone diatur ke: {SCHEDULER_TZ}")
# Jalankan sekali saat start (opsional)
def boot_scrape_if_needed():
    try:
        if not os.path.exists(JSON_FILE):
            run_scraper_and_save()
        else:
            with open(JSON_FILE, encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict) or "data" not in data or len(data["data"]) == 0:
                run_scraper_and_save()
    except Exception as e:
        logging.warning(f"Boot scrape gagal: {e}")
        
        # Konfigurasi Domain WebAuthn (Ambil dari .env)
RP_ID = os.getenv("WEBAUTHN_RP_ID", "localhost") 
RP_NAME = os.getenv("WEBAUTHN_RP_NAME", "The Putras Tools")
ORIGIN = os.getenv("WEBAUTHN_ORIGIN", "http://localhost:5000")
# logging.info(f"[WebAuthn Config] Aktif di RP_ID: '{RP_ID}' dengan ORIGIN: '{ORIGIN}'")

executor = ThreadPoolExecutor(max_workers=3)
JSON_FILE = 'jadwal.json'
ICS_FILE = 'jadwal_kegiatan.ics'
JADWAL_STATUS = {"status": "ready", "message": "Siap."}

# ===== SSKM IN-MEMORY STORAGE =====
# Store SSKM attendance data in memory for real-time streaming (Dictionary: room_code -> list)
SSKM_ROOMS = {}
app.secret_key = os.getenv("SECRET_KEY")  # Untuk session
# if not app.secret_key:
    
#     logging.error("FATAL ERROR: SECRET_KEY tidak diatur di environment!")
#     raise ValueError("SECRET_KEY tidak diatur. Set di file .env atau environment variable.")
# logging.info("Secret Key untuk session berhasil diatur.")

if not app.secret_key:
    app.secret_key = 'fallback_secret_for_dev'  # Jangan pakai di prod!
    app.config['SECRET_KEY'] = app.secret_key  # Set ke config juga, biar current_app.config bisa akses



# IS_PRODUCTION = os.getenv("FLASK_ENV") == "production"

# app.config.update(
#     SESSION_COOKIE_HTTPONLY=True,
#     SESSION_COOKIE_SAMESITE='None' if IS_PRODUCTION else 'Lax',
#     SESSION_COOKIE_SECURE=IS_PRODUCTION,  # False kalau localhost
#     SESSION_PERMANENT=True,
#     PERMANENT_SESSION_LIFETIME=3600 * 24 * 7,
#     SESSION_COOKIE_PATH='/',
#     SESSION_COOKIE_DOMAIN=None,  # biar domain fleksibel
#     SESSION_REFRESH_EACH_REQUEST=True
# )
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=False
)


# Session(app) # <--- TAMBAHIN INI





month_translation = { 'Januari': 'January', 'Februari': 'February', 'Maret': 'March', 'April': 'April', 'Mei': 'May', 'Juni': 'June', 'Juli': 'July', 'Agustus': 'August', 'September': 'September', 'Oktober': 'October', 'November': 'November', 'Desember': 'December' }
majorID = { "39010": "D3 Sistem Informasi", "41010": "S1 Sistem Informasi", "41011": "S1 Sistem Informasi", "41020": "S1 Teknik Komputer", "42010": "S1 Desain Komunikasi Visual", "42020": "S1 Desain Produk", "43010": "S1 Manajemen", "43020": "S1 Akuntansi", "51016": "D4 Produksi Film dan Televisi" }

# Fungsi validasi (sudah ada, tidak ubah)
def _valid_role(x):
    return x in ("mahasiswa", "staff")

# Fungsi untuk deteksi prodi dari NIM
def get_prodi_from_nim(nim):
    """Auto-detect prodi dari NIM berdasarkan kode prodi (digit 3-7)"""
    if nim and len(nim) >= 7:
        kode_prodi = nim[2:7]  # Ambil digit ke-3 sampai 7
        return majorID.get(kode_prodi, None)
    return None

def get_current_status():
    return JADWAL_STATUS



init_api(photo_cache, majorID, executor, get_current_status, log_file, _valid_role, SSKM_ROOMS)
app.register_blueprint(api_bp, url_prefix='/api')

# Jalankan scraper dan simpan hasilnya ke file JSON
def run_scraper_and_save():
    global JADWAL_STATUS
    
    # Format waktu saat ini
    now = datetime.now()
    waktu_str = now.strftime("%A, %d %B %Y %H:%M:%S")
    
    JADWAL_STATUS = {
        "status": "loading", 
        "message": f"Proses scraping dimulai: {waktu_str}"
    }
    
    logging.info("=== MENJALANKAN SCRAPING JADWAL ===")
    
    try:
        # 1. Jalankan Scraper
        # scrape_data biasanya return DataFrame pandas
        data_raw = scrape_data()
        
        data_records = []
        
        # 2. Konversi Data (Handle DataFrame atau List)
        if hasattr(data_raw, 'empty'): # Cek jika ini Pandas DataFrame
            if not data_raw.empty:
                data_records = data_raw.to_dict(orient='records')
        elif isinstance(data_raw, list):
            data_records = data_raw
            
        # 3. Logic: SELALU SIMPAN (Entah ada data atau kosong)
        # Tujuannya agar metadata 'last_scraped' selalu terupdate di file JSON.
        
        json_output = {
            "metadata": {
                "last_scraped": waktu_str,
                "total_jadwal": len(data_records)
            },
            "data": data_records
        }

        # Simpan ke file
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(json_output, f, indent=4, ensure_ascii=False)

        # 4. Update Status Akhir
        if data_records:
            msg = f"Data diperbarui: {len(data_records)} jadwal pada {waktu_str}"
            logging.info(f"--> Sukses. {len(data_records)} jadwal disimpan.")
        else:
            msg = f"Update selesai (0 Jadwal/Libur) pada {waktu_str}"
            logging.info("--> Sukses. Tidak ada jadwal (file JSON tetap diupdate metadatanya).")

        JADWAL_STATUS = {
            "status": "ready", 
            "message": msg
        }

    except Exception as e:
        waktu_error = datetime.now().strftime("%A, %d %B %Y %H:%M:%S")
        err_msg = f"Scraping gagal: {str(e)}"
        
        JADWAL_STATUS = {
            "status": "error", 
            "message": f"{err_msg} pada {waktu_error}"
        }
        logging.error(f"--> Error: {e}")

    logging.info("=== SCRAPING JADWAL SELESAI ===")


def create_ics_from_json(json_path, ics_path):
    try:
        # Baca file JSON yang bisa punya struktur baru (metadata + data)
        with open(json_path, 'r', encoding='utf-8') as f:
            data_json = json.load(f)

        # Cek apakah ini struktur baru atau lama
        if isinstance(data_json, dict) and "data" in data_json:
            events = data_json["data"]
        else:
            # fallback: struktur lama (langsung list)
            events = data_json

        if not events:
            raise ValueError("Data jadwal kosong atau tidak valid.")

        ics_content = "BEGIN:VCALENDAR\nVERSION:2.0\nCALSCALE:GREGORIAN\n"

        for event in events:
            try:
                date_str = event.get("Hari, Tanggal", "")
                time_range_str = event.get("Jam", "")
                if not date_str or not time_range_str:
                    continue

                start_time_val, end_time_val = time_range_str.split('-')
                start_date_time_str = re.sub(r"^\w+, ", "", date_str) + ' ' + start_time_val
                end_date_time_str = re.sub(r"^\w+, ", "", date_str) + ' ' + end_time_val

                for idn, eng in month_translation.items():
                    start_date_time_str = start_date_time_str.replace(idn, eng)
                    end_date_time_str = end_date_time_str.replace(idn, eng)
                # Jika tahun hanya 2 digit, tambahkan '20' di depannya
                def normalize_year(date_str):
                    parts = date_str.split()
                    if len(parts) >= 3 and len(parts[1]) > 0 and len(parts[2]) == 2:  # contoh: ['22', 'October', '25']
                        parts[2] = "20" + parts[2]
                        return " ".join(parts)
                    return date_str
                
                start_date_time_str = normalize_year(start_date_time_str)
                end_date_time_str = normalize_year(end_date_time_str)
                
                start_time = datetime.strptime(start_date_time_str, "%d %B %Y %H:%M")
                end_time = datetime.strptime(end_date_time_str, "%d %B %Y %H:%M")


                ics_content += (
                    "BEGIN:VEVENT\n"
                    f"SUMMARY:{event.get('Nama Matakuliah', 'Tanpa Nama')}\n"
                    f"DTSTART:{start_time.strftime('%Y%m%dT%H%M%S')}\n"
                    f"DTEND:{end_time.strftime('%Y%m%dT%H%M%S')}\n"
                    f"LOCATION:{event.get('Ruangan', 'Tidak Diketahui')}\n"
                    f"DESCRIPTION:Keterangan: {event.get('Keterangan', '-')}\n"
                    f"STATUS:{event.get('Status Kuliah', '-')}\n"
                    "END:VEVENT\n"
                )
            except Exception as e:
                logging.warning(f"Gagal konversi event: {e}")
                continue

        ics_content += "END:VCALENDAR\n"

        with open(ics_path, 'w', encoding='utf-8') as f:
            f.write(ics_content)

        logging.info(f"File {ics_path} berhasil diperbarui.")
        return True

    except Exception as e:
        logging.error(f"Error create_ics_from_json: {e}")
        raise
        
# @app.before_request
# def debug_cookies():
#     print("[DEBUG COOKIE] Cookie header:", request.headers.get('Cookie'))
#     logging.info(f"[DEBUG COOKIE] Cookie header: {request.headers.get('Cookie')}")

@app.after_request
def log_cookie_header(resp):
    # logging.info(f"[AFTER RESPONSE] Set-Cookie={resp.headers.get('Set-Cookie')}")
    return resp



# Main route

@app.route('/login', methods=['GET'])
def login_page():
    # Ambil token dari session atau cookie
    token = session.get('access_token') or request.cookies.get('access_token')
    
    if token:
        try:
            secret = current_app.config.get('SECRET_KEY') or app.secret_key
            payload = jwt.decode(token, secret, algorithms=["HS256"], options={"require": ["exp", "iat", "sub"]}, leeway=30)
            
            exp_time = datetime.fromtimestamp(payload['exp'], SCHEDULER_TZ)
            if exp_time < datetime.now(SCHEDULER_TZ):
                raise jwt.ExpiredSignatureError("Token expired")

            logging.info("User udah login, redirecting to index...")
            return redirect(request.args.get('next') or url_for('index'))
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            session.clear() 

    # --- TAMBAHAN BARU: Cek di Database apakah ada minimal 1 data fingerprint? ---
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM webauthn_credentials")
    count = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    
    has_any_biometric = count > 0

    # Kirim variabel has_any_biometric ke template login.html
    return render_template('login.html', has_any_biometric=has_any_biometric)

# Logout Route 1 Session + Cookie
@app.route('/logout')
def logout_page():
    logging.info(f"User logging out...")
    
    # 1. Ambil refresh_token dari cookie
    refresh_token = request.cookies.get('refresh_token')
    
    # 2. PANGGIL FUNGSI DARI auth_api.py (JAUH LEBIH BERSIH!)
    if refresh_token:
        _revoke_refresh_token(refresh_token)
    else:
        logging.warning("Logout: Tidak menemukan refresh_token di cookie.")

    # 3. Buat response redirect (Sama kayak sebelumnya)
    resp = make_response(redirect(url_for('login_page')))
    
    # 4. Hapus session di server
    session.clear()
    
    # 5. Hapus KEDUA cookie di browser
    resp.set_cookie("access_token", "", expires=0, httponly=True, samesite="Lax")
    resp.set_cookie("refresh_token", "", expires=0, httponly=True, samesite="Lax")
    
    logging.info("Session and cookies cleared. Redirecting to login.")
    return resp

# Logout Route all Session + Cookie
@app.route('/logout-all')
@login_required # <-- Ini penting, buat mastiin kita tau siapa user-nya
def logout_all_page():
    logging.info(f"User logging out from ALL devices...")
    
    # 1. Dapatkan user_id dari 'g' 
    # (g.user diisi oleh decorator @login_required)
    if 'user' in g and g.user.get('sub'):
        user_id = g.user['sub'] # 'sub' adalah user_id di JWT
        logging.info(f"Revoking all sessions for user_id: {user_id}")
        
        # 2. Panggil fungsi internal dari auth_api.py
        _revoke_all_user_sessions(user_id)
        
    else:
        logging.warning("Logout All: Tidak bisa menemukan user_id dari token.")

    # 3. Hapus sesi LOKAL (sama persis kayak logout biasa)
    resp = make_response(redirect(url_for('login_page')))
    session.clear()
    resp.set_cookie("access_token", "", expires=0, httponly=True, samesite="Lax")
    resp.set_cookie("refresh_token", "", expires=0, httponly=True, samesite="Lax")
    
    logging.info("Current session cleared. Redirecting to login.")
    return resp

@app.route('/')
@login_required
def index():    
    user_id = g.user.get('sub')
    role_id = g.user.get('role_id')

    # Jika dia role Mahasiswa Non-Sicyca (4), langsung lempar ke tools
    if role_id == 4:
        return redirect(url_for('tools_page'))
    # Cek apakah user punya kredensial Gate
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM gate_users WHERE user_id = %s", (user_id,))
    gate_exists = cursor.fetchone()
    cursor.close()
    conn.close()
    # Kalau dia Mahasiswa (3) tapi belum setup Gate, arahkan ke tools juga
    if not gate_exists and role_id == 3:
        return redirect(url_for('tools_page'))
    # logging.info(f"[INDEX DEBUG] Session keys:", list(session.keys()))
    print("[INDEX DEBUG] Session keys:", list(session.keys()))
    try:
        # Baca JSON dengan struktur baru
        with open(JSON_FILE, encoding='utf-8') as f:
            df_json = json.load(f)

        metadata = df_json.get("metadata", {})
        # Ambil datanya sebagai list of dict, BUKAN DataFrame
        jadwal_data = df_json.get("data", [])

        # Ambil waktu terakhir scraping dari metadata
        last_scraped = metadata.get("last_scraped", "Belum pernah di-scrape")

        # Kirim data mentah ke template
        return render_template(
            'index.html', 
            jadwal_list=jadwal_data,    # <-- Kirim list-nya
            last_scraped=last_scraped  # <-- Kirim tanggal scrape-nya
        )

    except (FileNotFoundError, ValueError, json.JSONDecodeError): 
        msg = "JADWAL BELUM TERSEDIA. Jalankan scraper terlebih dahulu atau tunggu jadwal otomatis berikutnya."
        # Kirim list kosong dan pesan error
        return render_template(
            'index.html', 
            jadwal_list=[], 
            last_scraped=None,
            error_message=msg  # <-- Kirim pesan error
        )

    except Exception as e:
        logging.error(f"Error di route index: {e}")
        return render_template(
            'index.html', 
            jadwal_list=[], 
            last_scraped=None,
            error_message=f"Terjadi error: {str(e)}"
        )

@app.route('/tools')
@login_required
def tools_page():
    role_id = g.user.get('role_id', 3)
    
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Kalau Super Admin (1), ambil semua daftar tool. Kalau bukan, cek izinnya.
    if role_id == 1:
        cursor.execute("SELECT route_name FROM tools")
    else:
        cursor.execute("""
            SELECT t.route_name 
            FROM tools t
            JOIN role_permissions rp ON t.id = rp.tool_id
            WHERE rp.role_id = %s AND rp.is_allowed = 1
        """, (role_id,))
        
    allowed_tools_db = cursor.fetchall()
    # Ubah formatnya jadi list biasa misal: ['logbook_magang', 'cari_komunitas']
    allowed_tools = [t['route_name'] for t in allowed_tools_db]
    
    cursor.close()
    conn.close()
    
    # Kirim list allowed_tools ke HTML
    return render_template('tools.html', allowed_tools=allowed_tools)

@app.route('/pembayaran')
@login_required
@check_permission('pembayaran_qris')
def pembayaran_page():
    """Halaman pembayaran QRIS"""
    return render_template('pembayaran.html')

@app.route('/account')
@login_required
def account_page():
    user_id = g.user.get('sub')
    
    # 1. Ambil data gate user kalau udah ada
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT gate_username FROM gate_users WHERE user_id = %s", (user_id,))
    gate_info = cursor.fetchone()
    
    # Ambil info user dasar juga
    cursor.execute("SELECT username, email, role_id FROM users WHERE id = %s", (user_id,))
    user_info = cursor.fetchone()
    
    cursor.close()
    conn.close()

    gate_username = gate_info['gate_username'] if gate_info else ""

    return render_template('account.html', gate_username=gate_username, user_info=user_info)


@app.route('/account/update-gate', methods=['POST'])
@login_required
def update_gate_credentials():
    user_id = g.user.get('sub')
    gate_username = request.form.get('gate_username')
    gate_password = request.form.get('gate_password')
    
    if not gate_username or not gate_password:
        flash('Username dan Password Sicyca wajib diisi!', 'error')
        return redirect(url_for('account_page'))

    try:
        # Enkripsi Password pakai Fernet (sesuai skema database lu)
        # Pastikan lu punya variabel GATE_ENCRYPTION_KEY di file .env lu
        gate_secret = os.getenv('GATE_ENCRYPTION_KEY')
        if not gate_secret:
            raise ValueError("GATE_ENCRYPTION_KEY tidak ditemukan di environment!")
            
        cipher_suite = Fernet(gate_secret.encode('utf-8'))
        encrypted_password = cipher_suite.encrypt(gate_password.encode('utf-8')).decode('utf-8')

        conn = get_connection()
        cursor = conn.cursor()
        
        # Gunakan sistem UPSERT (Kalau belum ada di-insert, kalau udah ada di-update)
        query = """
            INSERT INTO gate_users (user_id, gate_username, gate_password) 
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE 
            gate_username = VALUES(gate_username), 
            gate_password = VALUES(gate_password)
        """
        cursor.execute(query, (user_id, gate_username, encrypted_password))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        flash('Kredensial Sicyca berhasil diperbarui!', 'success')
    except Exception as e:
        logging.error(f"[Account] Error update gate credentials: {e}")
        flash('Gagal memperbarui kredensial Sicyca.', 'error')

    return redirect(url_for('account_page'))

@app.route('/account/update-profile', methods=['POST'])
@login_required
def update_profile():
    user_id = g.user.get('sub') # Ambil ID user yang lagi login
    username = request.form.get('username')
    email = request.form.get('email')
    
    if not username:
        flash('Username tidak boleh kosong!', 'error')
        return redirect(url_for('account_page'))
        
    # Panggil controller yang udah ada
    success, message = update_user_detail(user_id, username, email)
    
    if success:
        flash('Profil berhasil diperbarui!', 'success')
    else:
        flash(message, 'error')
        
    return redirect(url_for('account_page'))

@app.route('/account/update-password', methods=['POST'])
@login_required
def update_password():
    user_id = g.user.get('sub') # Ambil ID user yang lagi login
    new_password = request.form.get('new_password')

    # Panggil Controller
    success, message = update_user_password(user_id, new_password)

    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')

    return redirect(url_for('account_page'))
# Route untuk reset session scraper (hapus cookies.json)
@app.route('/reset-scraper-session')
@login_required
def reset_scraper_session():
    try:
        # Ambil user_id dari context 'g' (dari @login_required)
        if 'user' in g and g.user.get('sub'):
            user_id = g.user['sub']
            
            # Panggil Controller untuk hapus sesi di Memori & Database
            reset_session_user(user_id)
            
            logging.info(f"[Reset Scraper] Sesi untuk User ID {user_id} berhasil di-reset sepenuhnya (DB & RAM).")
        else:
            logging.warning("[Reset Scraper] Gagal reset: User ID tidak ditemukan dalam token.")
            
    except Exception as e:
        logging.error(f"[Reset Scraper] Error: {e}")
    
    # Kembali ke dashboard
    return redirect(url_for('index'))

# Route untuk refresh jadwal manual
@app.route('/refresh-jadwal')
@login_required
def refresh_jadwal_route():
    # Jalankan scraper di background agar tidak memblokir
    executor.submit(run_scraper_and_save)
    # Langsung redirect, JavaScript akan menangani update UI
    return redirect(url_for('index'))

@app.route('/kalendar')
def kalendar_ics():
    try:
        # Pastikan file jadwal.json ada dan valid
        if not os.path.exists(JSON_FILE):
            return "<h3>File jadwal.json belum dibuat. Jalankan scraper dulu.</h3>", 404

        # Baca file dan ambil bagian data
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            df_json = json.load(f)
            data_records = df_json.get("data", [])
            metadata = df_json.get("metadata", {})

        if not data_records:
            return "<h3>Data jadwal belum tersedia atau kosong.</h3>", 404

        # Buat DataFrame dari data yang valid
        df = pd.DataFrame(data_records)

        # Simpan jadi file ICS
        create_ics_from_json(JSON_FILE, ICS_FILE)

        # Ambil waktu update dari metadata (opsional)
        waktu = metadata.get("last_scraped", "Tidak diketahui")

        logging.info(f"File ICS dibuat berdasarkan data terakhir: {waktu}")

        return send_from_directory(
            os.path.abspath('.'),
            path=ICS_FILE,
            as_attachment=True,
            download_name=f'jadwal_kuliah_{datetime.now().strftime("%Y%m%d_%H%M")}.ics'
        )

    except (FileNotFoundError, ValueError):
        return "<h3>File jadwal.json tidak ditemukan atau rusak.</h3>", 404
    except Exception as e:
        return f"<pre>Error saat membuat ICS: {str(e)}</pre>", 500



@app.route('/pencarian-komunitas', methods=['GET'])
@login_required
def pencarian_komunitas_route():
    return render_template('undika/sicyca/pencarian_mhsstaff.html')


@app.route('/cari-mahasiswa')
@login_required
def cari_mahasiswa_redirect():
    return redirect(url_for('pencarian_komunitas_route'))

@app.route('/log-program')
@login_required
@check_permission('log_program')
def log_program():
    log_content = "Membaca log..."
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            lines.reverse()
            log_content = "".join(lines)
    return render_template('log_page.html', log_content=log_content)


@app.route('/sosmed-download')
@login_required
@check_permission('sosmed_download')
def sosmed_download():
    """Menyajikan file HTML utama."""
    return render_template('downloadSosmed.html')

@app.route('/gate_undika')
@login_required
def gate_undika():
    user_id = g.user.get('sub')
    role_id = g.user.get('role_id')

    # Jika dia role Mahasiswa Non-Sicyca (4), langsung lempar ke tools
    if role_id == 4:
        return redirect(url_for('tools_page'))
    # Cek apakah user punya kredensial Gate
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM gate_users WHERE user_id = %s", (user_id,))
    gate_exists = cursor.fetchone()
    cursor.close()
    conn.close()
    # Kalau dia Mahasiswa (3) tapi belum setup Gate, arahkan ke tools juga
    if not gate_exists and role_id == 3:
        return redirect(url_for('tools_page'))
    
    
    return render_template('undika/gate/gateUndika.html')

@app.route('/sicyca_undika')
@login_required
def sicyca_undika():
    """Menyajikan file HTML utama dan mengirimkan data lengkap (Profil, Jadwal, SKS, Nilai, SSKM)."""
    user_id = g.user.get('sub')
    
    # ================= 1. Credentials & Profil =================
    gate_model = GateUser()
    _, username, _ = gate_model.get_credentials_by_user_id(user_id)
    nim = username if username else "-"
    
    profil = {
        "nama": "Mahasiswa",
        "nim": nim,
        "prodi": "-",
        "dosen_wali": "-",
        "foto_profil": url_for('static', filename='no_photo.jpg'),
        "ipk": "-", 
        "ips": "-"
    }
    
    if nim != "-":
        profil["foto_profil"] = url_for('api.get_my_profile_photo') # Pastikan route api.get_my_profile_photo ada
        try:
             df_mhs = search_mahasiswa(nim) # Pastikan fungsi search_mahasiswa sudah diimport
             if not df_mhs.empty:
                 row = df_mhs.iloc[0]
                 profil["nama"] = row.get("Nama", profil["nama"])
                 profil["dosen_wali"] = row.get("Dosen Wali", profil["dosen_wali"])
                 
                 # Logika Prodi
                 if nim and len(nim) >= 7:
                     kodeprodi = nim[2:7] # Ambil digit ke-3 sampai 7 dari NIM
                     # Ambil dari dictionary majorID, atau fallback ke data excel, atau default "-"
                     profil["prodi"] = majorID.get(kodeprodi, row.get("Prodi", "-"))
        except Exception as e:
            logging.error(f"[Sicyca Undika] Error fetch profile: {e}")

    # ================= 2. Jadwal Hari Ini =================
    jadwal_hari_ini = []
    hari_ini_str = ""
    try:
        days_id = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu']
        months_id = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']
        now = datetime.now(SCHEDULER_TZ) # Pastikan SCHEDULER_TZ diimport
        hari_ini_str = f"{days_id[now.weekday()]}, {now.day} {months_id[now.month]} {now.year}"
        
        if os.path.exists(JSON_FILE): # Pastikan JSON_FILE path benar
             with open(JSON_FILE, 'r', encoding='utf-8') as f:
                data_json = json.load(f)
                all_jadwal = data_json.get("data", [])
                for j in all_jadwal:
                    # Filter sederhana berdasarkan string hari
                    hari_tgl = j.get("Hari, Tanggal", "")
                    if days_id[now.weekday()].lower() in hari_tgl.lower(): 
                         jadwal_hari_ini.append({
                             "nama_mk": j.get("Nama Matakuliah", "-"),
                             "jam": j.get("Jam", "-"),
                             "ruang": j.get("Ruang", "-"),
                             "dosen": j.get("Dosen", "-")
                         })
    except Exception as e:
        logging.error(f"[Sicyca Undika] Error fetch jadwal: {e}")

    # ================= 3. Data Akademik (SKS, Nilai, SSKM) =================
    # A. Fetch SKS (Termasuk IPK/IPS)
    sks_tempuh = 0
    semester_est = 1
    try:
        sks_raw = fetch_sks(user_id=user_id) # Pastikan fungsi fetch_sks diimport
        if sks_raw and 'data' in sks_raw:
            data_sks = sks_raw['data']
            sks_tempuh = int(data_sks.get('sks_tempuh', 0))
            
            # Estimasi Semester: (SKS + 19) // 20
            if sks_tempuh > 0:
                semester_est = (sks_tempuh + 19) // 20
            else:
                semester_est = 1
            
            # Simpan IPK/IPS ke profil sementara
            if 'ipk' in data_sks: profil["ipk"] = data_sks['ipk']
            if 'ips' in data_sks: profil["ips"] = data_sks['ips']
            
    except Exception as e:
        logging.error(f"[Sicyca] Error fetch SKS: {e}")

    # B. Fetch Nilai Ujian
# B. Fetch Nilai Ujian
    nilai_rows = []
    try:
        # GANTI DARI "nilaiujian" KE "dashboard_nilai_ujian"
        # Agar strukturnya sesuai dengan tabel kecil di dashboard (Matakuliah & NILAI)
        nilai_raw = dahsboard_nilai({"t": "dashboard_nilai_ujian"}, user_id=user_id)
        
        if nilai_raw.get('success') and nilai_raw.get('tables'):
            raw_rows = nilai_raw['tables'][0].get('rows', [])
            
            for r in raw_rows:
                nilai_rows.append({
                    "matkul": r.get('Matakuliah', '-'),
                    
                    # Dashboard tidak punya kolom UTS/UAS, jadi kita strip atau kosongkan
                    "uts": "-", 
                    "uas": "-",
                    
                    # Ambil Nilai (di dashboard isinya Angka: 85, 100, dst)
                    "grade": r.get('NILAI', '-')
                })
                
            logging.info(f"[Sicyca Undika] Nilai Dashboard found: {len(nilai_rows)} items")
            
    except Exception as e:
        logging.error(f"[Sicyca Undika] Error fetch Nilai: {e}")

    # C. Fetch SSKM
    sskm_poin = 0
    sskm_persen = 0
    try:
        sskm_result = fetch_sskm_data(user_id=user_id) # Pastikan fetch_sskm_data diimport
        
        if sskm_result['success']:
            sskm_poin = sskm_result['total_poin']
            
            # Hitung Persentase (Target 100 poin untuk lulus)
            sskm_persen = int((sskm_poin / 100) * 100)
            if sskm_persen > 100: sskm_persen = 100
            
    except Exception as e:
        logging.error(f"[Sicyca] Error fetch SSKM: {e}")

    # ================= KIRIM DATA KE HTML =================
    data = {
        "nama": profil["nama"],
        "nim": profil["nim"],
        "prodi": profil["prodi"],
        "dosen_wali": profil["dosen_wali"],
        "foto_profil": profil["foto_profil"],
        
        "hari_ini": hari_ini_str,
        "jadwal": jadwal_hari_ini,
        
        "semester": semester_est,
        "sks_tempuh": sks_tempuh,
        
        "nilai_ujian": nilai_rows,
        
        # PERBAIKAN: Menambahkan IPK dan IPS yang sebelumnya hilang
        "ipk": profil["ipk"],
        "ips": profil["ips"],
        
        "sskm_poin": sskm_poin,
        "sskm_persen": sskm_persen
    }
    
    return render_template('undika/sicyca/dashboardsicycaUndika.html', data=data)

@app.route('/krs_sicyca')
@login_required
def krs_sicyca():
    """Menyajikan file HTML utama."""
    return render_template('undika/sicyca/krsSicyca.html')

@app.route('/sskm_record')
# @login_required
def sskm_record():
    """Menyajikan file HTML utama."""
    return render_template('sskm-record.html')

# ============================
# MANAJEMEN ULTAH ROUTES (SSR)
# ============================
from scrapper_requests import fetch_data_ultah, fetch_photo_from_sicyca
import base64

@app.route('/manajemenUltah')
@login_required
def manajemen_ultah():
    """Halaman utama - render data dari DB + SICYCA"""
    user_id = g.user.get('sub')
    
    db_records = ultah_model.get_all()
    
    sicyca_data = fetch_data_ultah()
    sicyca_list = sicyca_data.get('rows', []) if not sicyca_data.get('error') else []
    
    existing_names = {r['nama'].lower() for r in db_records}
    sicyca_filtered = [s for s in sicyca_list if s.get('nama', '').lower() not in existing_names]
    
    # Get Google account status
    google_info = google_cal_service.get_token_by_user(user_id)
    
    return render_template('manajemenUltah.html', 
                           records=db_records,
                           sicyca_list=sicyca_filtered,
                           today=sicyca_data.get('tanggal_hari_ini', ''),
                           google_user=google_info)

@app.route('/manajemenUltah/add', methods=['POST'])
@login_required
def ultah_add():
    """Tambah data ultah baru"""
    nama = request.form.get('nama', '').strip()
    nim = request.form.get('nim', '').strip()
    tanggal = request.form.get('tanggal')
    bulan = request.form.get('bulan')
    tahun_lahir = request.form.get('tahun_lahir')
    prodi = request.form.get('prodi', '').strip()
    simpan_foto = request.form.get('simpan_foto') == 'on'
    
    if not nama or not tanggal or not bulan:
        flash('Nama, Tanggal, dan Bulan wajib diisi!', 'error')
        return redirect(url_for('manajemen_ultah'))
    
    if nim and ultah_model.check_nim_exists(nim):
        flash(f'NIM {nim} sudah terdaftar!', 'error')
        return redirect(url_for('manajemen_ultah'))
    
    foto_base64 = None
    if simpan_foto and nim:
        foto_bytes = fetch_photo_from_sicyca('mahasiswa', nim)
        if foto_bytes:
            foto_base64 = base64.b64encode(foto_bytes).decode('utf-8')
    
    data = {
        'nama': nama,
        'nim': nim if nim else None,
        'tanggal': int(tanggal),
        'bulan': int(bulan),
        'tahun_lahir': int(tahun_lahir) if tahun_lahir else None,
        'foto_base64': foto_base64,
        'prodi': prodi if prodi else get_prodi_from_nim(nim),  # Auto-detect dari NIM
        'is_from_sicyca': 0
    }
    
    if ultah_model.create(data):
        flash('Data ultah berhasil ditambahkan!', 'success')
    else:
        flash('Gagal menambahkan data ultah!', 'error')
    
    return redirect(url_for('manajemen_ultah'))

@app.route('/manajemenUltah/edit/<int:record_id>', methods=['POST'])
@login_required
def ultah_edit(record_id):
    """Update data ultah"""
    nama = request.form.get('nama', '').strip()
    nim = request.form.get('nim', '').strip()
    tanggal = request.form.get('tanggal')
    bulan = request.form.get('bulan')
    tahun_lahir = request.form.get('tahun_lahir')
    prodi = request.form.get('prodi', '').strip()
    
    if not nama or not tanggal or not bulan:
        flash('Nama, Tanggal, dan Bulan wajib diisi!', 'error')
        return redirect(url_for('manajemen_ultah'))
    
    if nim and ultah_model.check_nim_exists(nim, exclude_id=record_id):
        flash(f'NIM {nim} sudah terdaftar!', 'error')
        return redirect(url_for('manajemen_ultah'))
    
    existing = ultah_model.get_by_id(record_id)
    foto_base64 = existing.get('foto_base64') if existing else None
    
    data = {
        'nama': nama,
        'nim': nim if nim else None,
        'tanggal': int(tanggal),
        'bulan': int(bulan),
        'tahun_lahir': int(tahun_lahir) if tahun_lahir else None,
        'foto_base64': foto_base64,
        'prodi': prodi if prodi else get_prodi_from_nim(nim)  # Auto-detect dari NIM
    }
    
    if ultah_model.update(record_id, data):
        flash('Data ultah berhasil diupdate!', 'success')
    else:
        flash('Gagal mengupdate data ultah!', 'error')
    
    return redirect(url_for('manajemen_ultah'))

@app.route('/manajemenUltah/delete/<int:record_id>', methods=['POST'])
@login_required
def ultah_delete(record_id):
    """Hapus data ultah"""
    # Cek opsi delete Google Calendar
    if request.form.get('delete_gcal') == 'on':
        record = ultah_model.get_by_id(record_id)
        if record and record.get('google_calendar_event_id'):
            user_id = g.user.get('sub')
            google_cal_service.delete_event(user_id, record['google_calendar_event_id'])
            
    if ultah_model.delete(record_id):
        flash('Data ultah berhasil dihapus!', 'success')
    else:
        flash('Gagal menghapus data ultah!', 'error')
    
    return redirect(url_for('manajemen_ultah'))

@app.route('/manajemenUltah/save-sicyca', methods=['POST'])
@login_required
def ultah_save_sicyca():
    """Simpan data dari list SICYCA ke database"""
    nama = request.form.get('nama', '').strip()
    prodi = request.form.get('prodi', '').strip()
    tanggal_lahir = request.form.get('tanggal_lahir', '').strip()
    nim = request.form.get('nim', '').strip()
    simpan_foto = request.form.get('simpan_foto') == 'on'
    
    if not nama:
        flash('Data tidak valid!', 'error')
        return redirect(url_for('manajemen_ultah'))
    
    tanggal, bulan, tahun = parse_tanggal_sicyca(tanggal_lahir)
    
    if not tanggal or not bulan:
        flash('Format tanggal tidak valid!', 'error')
        return redirect(url_for('manajemen_ultah'))
    
    if nim and ultah_model.check_nim_exists(nim):
        flash(f'NIM {nim} sudah terdaftar!', 'error')
        return redirect(url_for('manajemen_ultah'))
    
    foto_base64 = None
    if simpan_foto and nim:
        foto_bytes = fetch_photo_from_sicyca('mahasiswa', nim)
        if foto_bytes:
            foto_base64 = base64.b64encode(foto_bytes).decode('utf-8')
    
    data = {
        'nama': nama,
        'nim': nim if nim else None,
        'tanggal': tanggal,
        'bulan': bulan,
        'tahun_lahir': tahun,
        'foto_base64': foto_base64,
        'prodi': prodi if prodi else get_prodi_from_nim(nim),  # Auto-detect dari NIM
        'is_from_sicyca': 1
    }
    
    if ultah_model.create(data):
        flash(f'Data ultah {nama} berhasil disimpan!', 'success')
    else:
        flash('Gagal menyimpan data ultah!', 'error')
    
    return redirect(url_for('manajemen_ultah'))

@app.route('/manajemenUltah/lookup', methods=['GET'])
@login_required
def ultah_lookup_nim():
    """Lookup data mahasiswa by NIM"""
    nim = request.args.get('nim')
    if not nim:
        return Response(json.dumps({'success': False, 'message': 'NIM required'}), mimetype='application/json')
        
    try:
        # Search via scraper
        df = search_mahasiswa(nim)
        
        if not df.empty:
            # Ambil baris pertama
            item = df.iloc[0]
            # Convert keys to lowercase for safety
            data = {k.lower(): v for k, v in item.items()}
            
            result = {
                'success': True,
                'nama': data.get('nama', ''),
                'prodi': data.get('prodi', ''),
                'nim': data.get('nim', nim)
            }
            return Response(json.dumps(result), mimetype='application/json')
        else:
             return Response(json.dumps({'success': False, 'message': 'Data tidak ditemukan'}), mimetype='application/json')
    except Exception as e:
        logging.error(f"Error lookup NIM: {e}")
        return Response(json.dumps({'success': False, 'message': str(e)}), mimetype='application/json')

@app.route('/manajemenUltah/sync-calendar/<int:record_id>', methods=['POST'])
@login_required
def ultah_sync_calendar(record_id):
    """Sync single data ultah ke Google Calendar"""
    user_id = g.user.get('sub')
    
    # Cek apakah sudah connect Google
    token_info = google_cal_service.get_token_by_user(user_id)
    if not token_info:
        flash('Silakan hubungkan akun Google terlebih dahulu.', 'warning')
        return redirect(url_for('manajemen_ultah'))
    
    # 1. Parse Parameters from Unified Modal
    color_id = request.form.get('color_id')
    
    # Attendees (JSON list or comma separated)
    attendees_raw = request.form.get('attendees', '')
    attendees = []
    try:
        attendees = json.loads(attendees_raw)
        if not isinstance(attendees, list):
            attendees = []
    except:
        attendees = [e.strip() for e in attendees_raw.split(',') if e.strip()]
    
    # Reminders (JSON list of {method, minutes})
    reminders_raw = request.form.get('reminders_json', '')
    reminders = []
    if reminders_raw:
        try:
            reminders = json.loads(reminders_raw)
        except:
            logging.warn("Failed parsing reminders JSON")

    # Ambil record
    record = ultah_model.get_by_id(record_id)
    if not record:
        flash('Data tidak ditemukan!', 'error')
        return redirect(url_for('manajemen_ultah'))
    
    # Hapus event lama jika ada
    if record.get('google_calendar_event_id'):
        google_cal_service.delete_event(user_id, record.get('google_calendar_event_id'))
        
    # Buat Event Baru dengan Overrides
    event_id = google_cal_service.create_birthday_event(
        user_id, 
        record, 
        overrides={
            'colorId': color_id,
            'attendees': attendees,
            'reminders': reminders
        }
    )
    
    if event_id:
        ultah_model.update_google_event_id(record_id, event_id)
        flash('Berhasil sync ke Google Calendar!', 'success')
    else:
        flash('Gagal sync ke Google Calendar.', 'error')
        
    return redirect(url_for('manajemen_ultah'))

# ========== GOOGLE OAUTH ROUTES ==========

@app.route('/manajemenUltah/google/auth')
@login_required
def ultah_google_auth():
    """Redirect ke Google OAuth"""
    auth_url, state = google_cal_service.get_auth_url()
    session['google_oauth_state'] = state
    return redirect(auth_url)

@app.route('/manajemenUltah/google/callback')
@login_required
def ultah_google_callback():
    """Handle OAuth callback dari Google"""
    user_id = g.user.get('sub')
    
    try:
        credentials, user_data = google_cal_service.handle_callback(request.url)
        google_cal_service.save_token(user_id, credentials, user_data)
        flash(f'Berhasil terhubung dengan akun Google: {user_data.get("name")}', 'success')
    except Exception as e:
        logging.error(f"[GoogleOAuth] Error: {e}")
        flash('Gagal menghubungkan akun Google.', 'error')
    
    return redirect(url_for('manajemen_ultah'))

@app.route('/manajemenUltah/google/disconnect', methods=['POST'])
@login_required
def ultah_google_disconnect():
    """Disconnect Google account"""
    user_id = g.user.get('sub')
    
    if google_cal_service.delete_token(user_id):
        # Reset kolom google_calendar_event_id di database (clean DB)
        try:
            conn = get_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE ultah_records SET google_calendar_event_id = NULL")
                conn.commit()
                cursor.close()
                conn.close()
            flash('Akun Google berhasil diputuskan dan status sync di-reset.', 'success')
        except Exception as e:
            logging.error(f"Error reseting sync status: {e}")
            flash('Akun Google putus, tapi gagal reset status DB.', 'warning')
    else:
        flash('Gagal memutuskan akun Google.', 'error')
        
    return redirect(url_for('manajemen_ultah'))

@app.route('/manajemenUltah/settings', methods=['POST'])
@login_required
def ultah_save_settings():
    """Simpan pengaturan sinkronisasi Google Calendar"""
    user_id = g.user.get('sub')
    
    color_id = request.form.get('color_id')
    raw_attendees = request.form.get('default_attendees', '').strip()
    
    # Parse attendees to list
    if raw_attendees.startswith('['):
        try:
            default_attendees = json.loads(raw_attendees)
        except:
            default_attendees = []
    else:
        default_attendees = [x.strip() for x in raw_attendees.split(',') if x.strip()]
    
    settings = {
        'color_id': color_id,
        'default_attendees': default_attendees
    }
    
    if google_cal_service.save_settings(user_id, settings):
        flash('Pengaturan berhasil disimpan!', 'success')
    else:
        flash('Gagal menyimpan pengaturan.', 'error')
        
    return redirect(url_for('manajemen_ultah'))

# ========== BULK OPERATIONS ==========

@app.route('/manajemenUltah/bulk-delete', methods=['POST']) 
@login_required
def ultah_bulk_delete():
    """Bulk delete records"""
    user_id = g.user.get('sub')
    record_ids = request.form.getlist('record_ids')
    
    if not record_ids:
        flash('Tidak ada data yang dipilih!', 'warning')
        return redirect(url_for('manajemen_ultah'))
    
    deleted_count = 0
    for record_id in record_ids:
        try:
            record = ultah_model.get_by_id(int(record_id))
            if record:
                # Hapus event dari Google Calendar jika ada
                if record.get('google_calendar_event_id'):
                    google_cal_service.delete_event(user_id, record['google_calendar_event_id'])
                
                if ultah_model.delete(int(record_id)):
                    deleted_count += 1
        except Exception as e:
            logging.error(f"[BulkDelete] Error: {e}")
    
    flash(f'{deleted_count} data berhasil dihapus!', 'success')
    return redirect(url_for('manajemen_ultah'))

@app.route('/manajemenUltah/bulk-sync', methods=['POST'])
@login_required
def ultah_bulk_sync():
    """Bulk sync records ke Google Calendar"""
    user_id = g.user.get('sub')
    
    # Cek apakah sudah connect Google
    token_info = google_cal_service.get_token_by_user(user_id)
    if not token_info:
        flash('Silakan hubungkan akun Google terlebih dahulu.', 'warning')
        return redirect(url_for('manajemen_ultah'))
    
    record_ids = request.form.getlist('record_ids')
    attendees_raw = request.form.get('attendees', '')
    attendees = []
    try:
        # Coba parse sebagai JSON (karena frontend kirim format ["a@b.com"])
        attendees = json.loads(attendees_raw)
        if not isinstance(attendees, list):
            attendees = []
    except:
        # Fallback jika bukan JSON (comma separated)
        attendees = [e.strip() for e in attendees_raw.split(',') if e.strip()]
    # --------------------------------------------------
    if not record_ids:
        flash('Tidak ada data yang dipilih!', 'warning')
        return redirect(url_for('manajemen_ultah'))
    
    synced_count = 0
    for record_id in record_ids:
        try:
            record = ultah_model.get_by_id(int(record_id))
            if record:
                # Hapus event lama jika ada
                if record.get('google_calendar_event_id'):
                    google_cal_service.delete_event(user_id, record['google_calendar_event_id'])
                
                # Create event baru
                event_id = google_cal_service.create_birthday_event(user_id, record, overrides={'attendees': attendees})
                
                if event_id:
                    conn = get_connection()
                    if conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE ultah_records SET google_calendar_event_id = %s WHERE id = %s",
                            (event_id, int(record_id))
                        )
                        conn.commit()
                        cursor.close()
                        conn.close()
                    synced_count += 1
        except Exception as e:
            logging.error(f"[BulkSync] Error: {e}")
    
    flash(f'{synced_count} data berhasil disinkronkan ke Google Calendar!', 'success')
    return redirect(url_for('manajemen_ultah'))

# SSE Endpoint untuk streaming count
@app.route('/stream/recap-count')           
def stream_recap_count():
    """Server-Sent Events endpoint untuk streaming jumlah orang yang terecap"""
    room_code = request.args.get('room')
    
    def generate():
        last_count = 0
        last_duplicate_time = 0
        
        while True:
            try:
                # Check Room Validity
                if not room_code or room_code not in SSKM_ROOMS:
                     # Send zero data if room invalid or not created yet
                     yield f"data: {json.dumps({'total': 0, 'uuid': 0, 'nim': 0, 'error': 'Room not found'})}\n\n"
                     time.sleep(2)
                     continue

                current_room_data = SSKM_ROOMS[room_code]
                
                # Calculate counts
                current_count = len(current_room_data)
                uuid_count = sum(1 for item in current_room_data if item.get('uuid'))
                nim_count = sum(1 for item in current_room_data if item.get('nim'))
                
                payload = {
                    "total": current_count,
                    "uuid": uuid_count,
                    "nim": nim_count
                }
                
                # Check for NEW data (increment only)
                if current_count > last_count:
                     if current_count > 0:
                        latest_item = current_room_data[-1]
                        payload["new_scan"] = {
                            "type": "NIM" if latest_item.get('nim') else "UUID",
                            "value": latest_item.get('nim') or latest_item.get('uuid')
                        }
                
                # Check for DUPLICATE warning (Room Specific)
                # SSKM_LAST_DUPLICATE structure: { 'room_code': { 'type': ..., 'value': ..., 'timestamp': ... } }
                if room_code in SSKM_LAST_DUPLICATE:
                    last_evt = SSKM_LAST_DUPLICATE[room_code]
                    if last_evt.get('timestamp', 0) > last_duplicate_time:
                        payload["duplicate"] = {
                            "type": last_evt['type'],
                            "value": last_evt['value']
                        }
                        last_duplicate_time = last_evt['timestamp']

                last_count = current_count
                
                # Format SSE: data: <json>\n\n
                yield f"data: {json.dumps(payload)}\n\n"
                time.sleep(1)  # Update every 1 second for faster feedback
            except GeneratorExit:
                break
    
    return Response(generate(), mimetype='text/event-stream')

# Route untuk halaman recap
@app.route('/recap-hadir')
def recap_hadir():
    """Halaman real-time counter kehadiran SSKM"""
    return render_template('recapOrangSSKM.html')

@app.route('/testhtml')
def test_html():
    """Halaman real-time counter kehadiran SSKM"""
    return render_template('test.html')

# ======================================================
# ROUTES LOGBOOK MAGANG
# ======================================================

# 1. Halaman Awal: List Semua Logbook
@app.route('/logbook', methods=['GET'])
@login_required # Proteksi route
@check_permission('logbook_magang')
def logbook_list():
    current_user = g.user.get('sub') # Ambil User ID dari JWT
    
    # Ambil logbook KHUSUS punya user ini aja
    logbooks = get_logbooks_by_user(current_user)
    return render_template('logBook/list.html', logbooks=logbooks)

# 2. Halaman Setup Logbook Baru
@app.route('/logbook/setup', methods=['GET', 'POST'])
@login_required
def logbook_setup():
    current_user = g.user.get('sub')
    
    if request.method == 'POST':
        # Simpan logbook baru dengan menyertakan ID usernya
        new_id = create_logbook(current_user, request.form)
        return redirect(url_for('logbook_detail', logbook_id=new_id))
        
    return render_template('logBook/setup.html', logbook=None)

# 3. Edit Setup Logbook (INI YANG TADI DUPLIKAT DAN SALAH ROUTE)
@app.route('/logbook/edit/<int:logbook_id>', methods=['GET', 'POST'])
@login_required
@check_permission('logbook_magang')
def logbook_edit(logbook_id):
    current_user = g.user.get('sub')
    
    if request.method == 'POST':
        update_logbook(logbook_id, request.form, current_user)
        return redirect(url_for('logbook_detail', logbook_id=logbook_id))
        
    # Ambil datanya buat diisi ke form
    logbook = get_logbook_by_id_and_user(logbook_id, current_user)
    if not logbook:
        return "Akses Ditolak! Ini bukan logbook Anda.", 403
        
    return render_template('logBook/setup.html', logbook=logbook)

# 4. Hapus Setup Logbook
@app.route('/logbook/delete/<int:logbook_id>')
@login_required
@check_permission('logbook_magang')
def logbook_delete(logbook_id):
    current_user = g.user.get('sub')
    delete_logbook(logbook_id, current_user)
    return redirect(url_for('logbook_list'))

# 5. HALAMAN UTAMA LOGBOOK (Isi Kegiatan Harian)
@app.route('/logbook/<int:logbook_id>', methods=['GET'])
@login_required
@check_permission('logbook_magang')
def logbook_detail(logbook_id):
    current_user = g.user.get('sub')
    
    # Cek apakah logbook ini beneran milik dia
    logbook = get_logbook_by_id_and_user(logbook_id, current_user)
    if not logbook:
        return "Akses Ditolak! Ini bukan logbook Anda.", 403
        
    entries = get_entries_by_logbook(logbook_id)
    return render_template('logBook/detail.html', logbook=logbook, entries=entries)

# 6. Tambah Kegiatan Harian
@app.route('/logbook/<int:logbook_id>/add_entry', methods=['POST'])
@login_required
@check_permission('logbook_magang')
def logbook_add_entry(logbook_id):
    current_user = g.user.get('sub')
    
    # Keamanan: Pastikan logbook milik dia sebelum nambah kegiatan
    logbook = get_logbook_by_id_and_user(logbook_id, current_user)
    if logbook:
        add_entry(logbook_id, request.form, request.files)
        
    return redirect(url_for('logbook_detail', logbook_id=logbook_id))
# 6.5 Edit Kegiatan Harian
@app.route('/logbook/<int:logbook_id>/edit_entry/<int:entry_id>', methods=['GET', 'POST'])
@login_required
@check_permission('logbook_magang')
def logbook_edit_entry(logbook_id, entry_id):
    current_user = g.user.get('sub')
    
    # Keamanan: Pastikan logbook ini beneran milik dia sebelum ngedit
    logbook = get_logbook_by_id_and_user(logbook_id, current_user)
    if not logbook:
        return "Akses Ditolak!", 403

    # Jika disubmit (POST)
    if request.method == 'POST':
        update_entry(entry_id, request.form, request.files)
        return redirect(url_for('logbook_detail', logbook_id=logbook_id))

    # Jika cuma ngebuka halaman (GET)
    entry = get_entry_by_id(entry_id)
    if not entry:
        return "Data kegiatan tidak ditemukan", 404

    return render_template('logBook/edit_entry.html', logbook=logbook, entry=entry)
# 7. Hapus Kegiatan Harian
@app.route('/logbook/<int:logbook_id>/delete_entry/<int:entry_id>')
@login_required
@check_permission('logbook_magang')
def logbook_delete_entry(logbook_id, entry_id):
    current_user = g.user.get('sub')
    
    # Keamanan: Pastikan logbook milik dia sebelum hapus kegiatan
    logbook = get_logbook_by_id_and_user(logbook_id, current_user)
    if logbook:
        delete_entry(entry_id)
        
    return redirect(url_for('logbook_detail', logbook_id=logbook_id))

# 8. Download Word
@app.route('/logbook/<int:logbook_id>/download', methods=['GET'])
@login_required
@check_permission('logbook_magang')
def logbook_download(logbook_id):
    current_user = g.user.get('sub')
    return generate_word(logbook_id, current_user)


# ======================================================
# ROUTES SUPER ADMIN (1 HTML DENGAN TABS)
# ======================================================

@app.route('/admin/panel')
@login_required
def admin_panel():
    if g.user.get('role_id') != 1:
        return "Akses Ditolak! Anda bukan Super Admin.", 403
        
    # Panggil fungsi dari UserController
    users = get_all_users()
    all_roles = get_all_roles(include_super_admin=True)
    roles_for_tools = get_all_roles(include_super_admin=False)
    
    # Bagian Tools & Izin (Tetap di sini atau bisa dipisah ke ToolController nanti)
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, nama_tool, route_name FROM tools")
    tools = cursor.fetchall()
    
    cursor.execute("SELECT role_id, tool_id, is_allowed FROM role_permissions")
    perms = cursor.fetchall()
    perm_map = {(p['role_id'], p['tool_id']): p['is_allowed'] for p in perms}
    cursor.close()
    conn.close()
    
    return render_template('admin_panel.html', users=users, all_roles=all_roles, roles=roles_for_tools, tools=tools, perm_map=perm_map)

@app.route('/admin/add-user', methods=['POST'])
@login_required
def add_user():
    if g.user.get('role_id') != 1:
        return "Akses Ditolak!", 403
        
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    role_id = request.form.get('role_id')
    
    if not username or not password or not role_id:
        flash('Username, Password, dan Role wajib diisi!', 'error')
        return redirect(url_for('admin_panel'))
        
    # Lempar datanya ke UserController
    success, message = create_user(username, email, password, role_id)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
        
    return redirect(url_for('admin_panel'))

@app.route('/admin/update-role', methods=['POST'])
@login_required
def update_role():
    if g.user.get('role_id') != 1:
        return "Ditolak", 403
        
    user_id = request.form.get('user_id')
    role_id = request.form.get('role_id')
    
    # Lempar datanya ke UserController
    if change_user_role(user_id, role_id):
        flash('Role user berhasil diubah!', 'success')
    else:
        flash('Gagal mengubah role user.', 'error')
        
    return redirect(url_for('admin_panel'))
@app.route('/admin/toggle-tool', methods=['POST'])
@login_required
def toggle_tool():
    # Proteksi extra: Pastikan cuma Super Admin yang bisa ubah
    if g.user.get('role_id') != 1:
        return jsonify({'error': 'Akses Ditolak!'}), 403
        
    data = request.json
    role_id = data.get('role_id')
    tool_id = data.get('tool_id')
    is_allowed = data.get('is_allowed')
    
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Pake fitur sakti MySQL UPSERT (Insert if not exist, Update if exist)
        query = """
            INSERT INTO role_permissions (role_id, tool_id, is_allowed) 
            VALUES (%s, %s, %s) 
            ON DUPLICATE KEY UPDATE is_allowed = VALUES(is_allowed)
        """
        cursor.execute(query, (role_id, tool_id, is_allowed))
        conn.commit()
        return jsonify({'success': True, 'message': 'Izin berhasil diubah!'})
    except Exception as e:
        logging.error(f"[Toggle Tool] Error: {e}")
        return jsonify({'success': False, 'message': 'Terjadi kesalahan server.'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/admin/update-user', methods=['POST'])
@login_required
def admin_update_user():
    if g.user.get('role_id') != 1: return "Ditolak", 403
    
    user_id = request.form.get('user_id')
    username = request.form.get('username')
    email = request.form.get('email')
    
    success, message = update_user_detail(user_id, username, email)
    flash(message, 'success' if success else 'error')
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete-user/<int:user_id>')
@login_required
def admin_delete_user(user_id):
    if g.user.get('role_id') != 1: return "Ditolak", 403
    
    # Keamanan: Jangan biarkan admin menghapus dirinya sendiri
    if str(user_id) == str(g.user.get('sub')):
        flash('Anda tidak bisa menghapus akun Anda sendiri!', 'error')
        return redirect(url_for('admin_panel'))
        
    if delete_user(user_id):
        flash('User berhasil dihapus!', 'success')
    else:
        flash('Gagal menghapus user.', 'error')
    return redirect(url_for('admin_panel'))
    
@app.route('/admin/reset-password/<int:user_id>')
@login_required
def admin_reset_password(user_id):
    if g.user.get('role_id') != 1: 
        return "Ditolak", 403
        
    if reset_user_password(user_id):
        flash(f'Password berhasil direset ke "mhs123"!', 'success')
    else:
        flash('Gagal mereset password.', 'error')
        
    return redirect(url_for('admin_panel'))


@app.route('/webauthn/register/options', methods=['POST'])
@login_required
def webauthn_register_options():
    user_id = str(g.user.get('sub'))
    
    # Ambil username dari token (kalau ada)
    username = g.user.get('username')

    # JIKA KOSONG (karena JWT lama nggak nyimpen username), ambil dari Database
    if not username:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
        user_db = cursor.fetchone()
        cursor.close()
        conn.close()
        
        # Pastikan username gak boleh kosong
        username = user_db['username'] if user_db else f"user_{user_id}"

    # Bikin opsi tantangan buat alat fingerprint
    options = generate_registration_options(
        rp_id=RP_ID,
        rp_name=RP_NAME,
        user_id=user_id.encode('utf-8'),
        user_name=username,  # Sekarang dijamin terisi!
        user_display_name=username,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM, 
            user_verification=UserVerificationRequirement.REQUIRED,
            resident_key=ResidentKeyRequirement.REQUIRED
        )
    )

    # Simpan 'challenge' ke session sementara buat diverifikasi nanti
    session['webauthn_registration_challenge'] = options.challenge

    # Kirim format JSON ke frontend
    return Response(options_to_json(options), mimetype='application/json')

@app.route('/webauthn/register/verify', methods=['POST'])
@login_required
def webauthn_register_verify():
    challenge = session.get('webauthn_registration_challenge')
    if not challenge:
        return jsonify({"success": False, "msg": "Challenge tidak ditemukan"}), 400

    credential_data = request.json # Data dari frontend

    try:
        verification = verify_registration_response(
            credential=credential_data,
            expected_challenge=challenge,
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN
        )

        # FIX UTAMA: Ambil credential ID langsung dari string yang dikirim Browser!
        # Jangan pakai base64.b64encode punya Python biar string-nya 100% cocok pas login.
        cred_id_b64 = credential_data.get('id') 
        
        # Public key tetap di-encode karena cuma dibaca sama Python
        pub_key_b64 = base64.b64encode(verification.credential_public_key).decode('utf-8')

        # Simpan ke Database
        user_id = g.user.get('sub')
        save_credential(user_id, cred_id_b64, pub_key_b64, verification.sign_count, "")
        
        session.pop('webauthn_registration_challenge', None)

        return jsonify({"success": True, "msg": "Sidik jari berhasil didaftarkan!"})

    except Exception as e:
        print(f"WebAuthn Verify Error: {e}")
        return jsonify({"success": False, "msg": str(e)}), 400
        
@app.route('/webauthn/login/options', methods=['POST'])
def webauthn_login_options():
    options = generate_authentication_options(
        rp_id=RP_ID,
        user_verification=UserVerificationRequirement.REQUIRED
    )
    session['webauthn_auth_challenge'] = options.challenge
    
    # FIX: Pake Response biar browser tau ini tipe datanya JSON!
    return Response(options_to_json(options), mimetype='application/json')


@app.route('/webauthn/login/verify', methods=['POST'])
def webauthn_login_verify():
    challenge = session.get('webauthn_auth_challenge')
    if not challenge:
        return jsonify({"success": False, "msg": "Challenge tidak ditemukan"}), 400

    credential_data = request.json
    cred_id_b64 = credential_data.get('id')

    user_data = get_user_by_credential(cred_id_b64)
    if not user_data:
        return jsonify({"success": False, "msg": "Perangkat ini belum terdaftar."}), 404

    try:
        verification = verify_authentication_response(
            credential=credential_data,
            expected_challenge=challenge,
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
            credential_public_key=base64.b64decode(user_data['public_key']),
            credential_current_sign_count=user_data['sign_count']
        )
        if verification.new_sign_count <= user_data['sign_count']:
            logging.warning(f"Potensi Replay Attack terdeteksi untuk user {user_data['id']}!")
            return jsonify({"success": False, "msg": "Deteksi keamanan: Token tidak valid."}), 403
            
        update_sign_count(cred_id_b64, verification.new_sign_count)

        # Proses pembuatan token JWT
        access_token = generate_access_token(user_data['id'], user_data['role_id'])
        refresh_token = generate_refresh_token()
        expires_at = datetime.now(SCHEDULER_TZ) + timedelta(days=30)
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_sessions (user_id, refresh_token, expires_at, ip_address, user_agent, revoked, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """, (user_data['id'], refresh_token, expires_at, request.remote_addr, request.headers.get('User-Agent'), 0))
        conn.commit()
        cursor.close()
        conn.close()

        session['user_id'] = user_data['id']
        session.modified = True

        resp = jsonify({"success": True, "msg": "Login Biometrik berhasil!", "redirect": url_for('index')})
        
        if isinstance(access_token, bytes):
            access_token = access_token.decode('utf-8')
            
        resp.set_cookie("access_token", access_token, httponly=True, secure=False, samesite="Lax", max_age=1800)
        resp.set_cookie("refresh_token", refresh_token, httponly=True, secure=False, samesite="Lax", max_age=3600*24*30)

        return resp

    except Exception as e:
        logging.error(f"WebAuthn Login Error: {e}")
        return jsonify({"success": False, "msg": "Verifikasi sidik jari gagal."}), 400
# if __name__ == "__main__":
#     should_run_scraper = False

#     if not os.path.exists(JSON_FILE):
#         logging.info(f"File {JSON_FILE} tidak ditemukan. Menjalankan scraper jadwal awal...")
#         should_run_scraper = True
#     else:
#         try:
#             # Baca struktur file JSON
#             with open(JSON_FILE, encoding='utf-8') as f:
#                 data = json.load(f)

#             # Pastikan format sesuai dan ada data
#             if isinstance(data, dict) and "data" in data and len(data["data"]) > 0:
#                 logging.info(f"File {JSON_FILE} ditemukan dan berisi {len(data['data'])} jadwal.")
#             else:
#                 logging.warning(f"File {JSON_FILE} kosong atau format tidak sesuai. Menjalankan scraper ulang...")
#                 should_run_scraper = True

#         except Exception as e:
#             logging.warning(f"File {JSON_FILE} rusak atau tidak bisa dibaca ({e}). Menjalankan scraper ulang...")
#             should_run_scraper = True

#     if should_run_scraper:
#         run_scraper_and_save()

# scheduler = BackgroundScheduler(daemon=True)
# Daftarkan job harian jam 05:00 WIB
scheduler.add_job(run_scraper_and_save, 'cron', hour=5, minute=0, id="scrape-05")
scheduler.start()
boot_scrape_if_needed()
    
logging.info("\nScheduler jadwal telah dimulai. Akan berjalan setiap hari jam 05:00 pagi.")
logging.info("Aplikasi web Flask siap di http://0.0.0.0:5000\n")