# app.py

import base64
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

# import base64  # Untuk encode image ke base64
from logging.handlers import RotatingFileHandler

import google.oauth2.credentials
import jwt
import pandas as pd
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from cachetools import TTLCache  # Install: pip install cachetools
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    current_app,
    flash,
    g,
    json,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_cors import CORS
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)
from werkzeug.middleware.proxy_fix import ProxyFix

from api.api import SSKM_LAST_DUPLICATE, api_bp, init_api
from connection import get_connection
from controller.GateController import (
    _build_gate_login_html,
    gate_sso_launch,
    reset_session_user,
)
from controller.LogbookController import (
    add_entry,
    approve_signature,
    create_logbook,
    delete_entry,
    delete_logbook,
    delete_resume,
    delete_single_image,
    generate_pdf_monthly,
    generate_word,
    get_entries_by_logbook,
    get_entry_by_id,
    get_entry_id_by_uuid,
    get_image_by_id,
    get_logbook_by_id_and_user,
    get_logbook_by_nim_and_uuid,
    get_logbook_id_by_uuid,
    get_logbooks_by_user,
    get_resumes_by_logbook,
    get_signatures_by_logbook,
    replace_image_file,
    revoke_signature,
    save_resume,
    save_signature_file,
    update_entry,
    update_image_metadata,
    update_logbook,
)
from controller.manajemenultahController import parse_tanggal_sicyca, ultah_model
from controller.UserController import (
    change_user_role,
    create_user,
    delete_user,
    get_all_roles,
    get_all_users,
    reset_user_password,
    update_user_detail,
    update_user_password,
)
from controller.WebAuthnController import (
    get_credentials_by_user,
    get_user_by_credential,
    save_credential,
    update_sign_count,
)
from extensions import limiter
from middleware.auth_quard import check_permission, login_required
from models.auth_api import (
    _revoke_all_user_sessions,
    _revoke_refresh_token,
    auth_bp,
    generate_access_token,
    generate_refresh_token,
)
from models.gate import GateUser
from models.googleOuth import google_cal_service

# Impor SEMUA fungsi scraper
from scrapper_requests import (
    dahsboard_nilai,
    fetch_sks,
    fetch_sskm_data,
    scrape_data,
    search_mahasiswa,
)

load_dotenv()  # biar bisa baca file .env

app = Flask(__name__)
# Konfigurasi Rate Limiter
limiter.init_app(app)


@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify(
        {
            "success": False,
            "msg": f"Terlalu banyak percobaan. Silakan coba lagi nanti. (Limit: {e.description})",
        }
    ), 429


# Batasi hanya domain asli lu yang boleh kirim credentials
CORS(
    app,
    supports_credentials=True,
    origins=[
        "http://localhost:5000",
        "https://tools.theputras.my.id",  # Ganti dengan domain asli lu
        "https://www.theputras.my.id",  # Ganti dengan domain asli lu
    ],
)

# CORS(
#     app,
#     supports_credentials=True,
#     origins=[
#         "http://172.16.2.148:5000",
#         "http://localhost:5000"
#     ]
# )

# Disable HTTPS requirement for OAuth testing (HAPUS ATAU COMMENT SAAT DEPLOY KE PRODUCTION!)
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
app.register_blueprint(auth_bp, url_prefix="/api/auth")


app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Inisialisasi scheduler SEKALI saat modul di-import
SCHEDULER_TZ = pytz.timezone(os.getenv("TIMEZONE"))


scheduler = BackgroundScheduler(timezone=SCHEDULER_TZ)

# ==================================================================
# === KONFIGURASI LOGGING ===
# ==================================================================
# Hapus handler default Flask agar tidak duplikat
app.logger.removeHandler(app.logger.handlers[0])

log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
log_file = "app.log"
# Gunakan RotatingFileHandler untuk membatasi ukuran file log (5MB, 2 file backup)
file_handler = RotatingFileHandler(
    log_file, maxBytes=1024 * 1024 * 5, backupCount=2, encoding="utf-8"
)
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
            with open(JSON_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if (
                not isinstance(data, dict)
                or "data" not in data
                or len(data["data"]) == 0
            ):
                run_scraper_and_save()
    except Exception as e:
        logging.warning(f"Boot scrape gagal: {e}")

        # Konfigurasi Domain WebAuthn (Ambil dari .env)


RP_ID = os.getenv("WEBAUTHN_RP_ID", "localhost")
RP_NAME = os.getenv("WEBAUTHN_RP_NAME", "The Putras Tools")
ORIGIN = os.getenv("WEBAUTHN_ORIGIN", "http://localhost:5000")
# logging.info(f"[WebAuthn Config] Aktif di RP_ID: '{RP_ID}' dengan ORIGIN: '{ORIGIN}'")

executor = ThreadPoolExecutor(max_workers=3)
JSON_FILE = "jadwal.json"
ICS_FILE = "jadwal_kegiatan.ics"
JADWAL_STATUS = {}

# ===== SSKM IN-MEMORY STORAGE =====
# Store SSKM attendance data in memory for real-time streaming (Dictionary: room_code -> list)
SSKM_ROOMS = {}
app.secret_key = os.getenv("SECRET_KEY")  # Untuk session
# if not app.secret_key:

#     logging.error("FATAL ERROR: SECRET_KEY tidak diatur di environment!")
#     raise ValueError("SECRET_KEY tidak diatur. Set di file .env atau environment variable.")
# logging.info("Secret Key untuk session berhasil diatur.")

if not app.secret_key:
    raise ValueError(
        "FATAL ERROR: SECRET_KEY wajib diisi di .env untuk alasan keamanan!"
    )


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
cookie_secure_env = os.getenv("COOKIE_SECURE", "0") == "1"
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=cookie_secure_env,
)

logging.info(f"[Security Config] Session Cookie Secure: {cookie_secure_env}")
# Session(app) # <--- TAMBAHIN INI


month_translation = {
    "Januari": "January",
    "Februari": "February",
    "Maret": "March",
    "April": "April",
    "Mei": "May",
    "Juni": "June",
    "Juli": "July",
    "Agustus": "August",
    "September": "September",
    "Oktober": "October",
    "November": "November",
    "Desember": "December",
}
majorID = {
    "39010": "D3 Sistem Informasi",
    "41010": "S1 Sistem Informasi",
    "41011": "S1 Sistem Informasi (RPL)",
    "41020": "S1 Teknik Komputer",
    "42010": "S1 Desain Komunikasi Visual",
    "42020": "S1 Desain Produk",
    "43010": "S1 Manajemen",
    "43020": "S1 Akuntansi",
    "51016": "D4 Produksi Film dan Televisi",
}


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


def get_current_status(user_id=None):
    status_data = {"status": "ready", "message": "Siap."}
    if user_id and user_id in JADWAL_STATUS:
        # Pake .copy() biar gak ngerubah original dict di memori secara nggak sengaja
        status_data = JADWAL_STATUS[user_id].copy()

    # Inject last_scraped check
    if user_id:
        try:
            from models.schedule import user_schedule_model

            last_scraped, _ = user_schedule_model.get_schedules_by_user(user_id)
            status_data["last_scraped"] = last_scraped
        except Exception as e:
            status_data["last_scraped"] = "Belum pernah di-scrape"
            logging.error(f"[get_current_status] Error fetch last_scraped: {e}")

    return status_data


init_api(
    photo_cache,
    majorID,
    executor,
    get_current_status,
    log_file,
    _valid_role,
    SSKM_ROOMS,
)
app.register_blueprint(api_bp, url_prefix="/api")


# Jalankan scraper dan simpan hasilnya ke database per user
def run_scraper_and_save(user_id=None):
    from models.schedule import user_schedule_model
    from scrapper_requests import _get_current_user_id

    target_user = _get_current_user_id(user_id)

    global JADWAL_STATUS

    # Format waktu saat ini
    now = datetime.now()
    waktu_str = now.strftime("%A, %d %B %Y %H:%M:%S")

    JADWAL_STATUS[target_user] = {
        "status": "loading",
        "message": f"Proses scraping dimulai: {waktu_str}",
    }

    logging.info(f"=== MENJALANKAN SCRAPING JADWAL UNTUK USER_ID {target_user} ===")

    try:
        # 1. Jalankan Scraper
        data_raw = scrape_data(target_user)

        data_records = []

        # 2. Konversi Data (Handle DataFrame atau List)
        if hasattr(data_raw, "empty"):  # Cek jika ini Pandas DataFrame
            if not data_raw.empty:
                data_records = data_raw.to_dict(orient="records")
        elif isinstance(data_raw, list):
            data_records = data_raw

        # 3. Logic: Simpan ke DB menggunakan model schedule
        success = user_schedule_model.save_schedules(
            target_user, waktu_str, data_records
        )

        # 4. Update Status Akhir
        if success:
            if data_records:
                msg = f"Data diperbarui: {len(data_records)} jadwal pada {waktu_str}"
                logging.info(f"--> Sukses. {len(data_records)} jadwal disimpan ke DB.")
            else:
                msg = f"Update selesai (0 Jadwal/Libur) pada {waktu_str}"
                logging.info("--> Sukses. Tidak ada jadwal/libur.")
        else:
            msg = f"Gagal menyimpan jadwal ke database pada {waktu_str}"
            logging.error(f"--> {msg}")

        JADWAL_STATUS[target_user] = {"status": "ready", "message": msg}

    except Exception as e:
        waktu_error = datetime.now().strftime("%A, %d %B %Y %H:%M:%S")
        err_msg = f"Scraping gagal: {str(e)}"

        JADWAL_STATUS[target_user] = {
            "status": "error",
            "message": f"{err_msg} pada {waktu_error}",
        }
        logging.error(f"--> Error: {e}")

    logging.info("=== SCRAPING JADWAL SELESAI ===")


def create_ics_for_user(user_id, ics_path):
    try:
        from models.schedule import user_schedule_model

        waktu, events = user_schedule_model.get_schedules_by_user(user_id)

        if not events:
            raise ValueError("Data jadwal kosong atau tidak valid.")

        ics_content = (
            "BEGIN:VCALENDAR\n"
            "VERSION:2.0\n"
            "PRODID:-//ThePutrasTools//NONSGML v1.0//EN\n"
            "CALSCALE:GREGORIAN\n"
            "X-WR-CALNAME:Jadwal Kuliah\n"
            "X-WR-TIMEZONE:Asia/Jakarta\n"
            "BEGIN:VTIMEZONE\n"
            "TZID:Asia/Jakarta\n"
            "BEGIN:STANDARD\n"
            "DTSTART:19700101T000000\n"
            "TZNAME:WIB\n"
            "TZOFFSETFROM:+0700\n"
            "TZOFFSETTO:+0700\n"
            "END:STANDARD\n"
            "END:VTIMEZONE\n"
        )

        for event in events:
            try:
                date_str = event.get("Hari, Tanggal", "")
                time_range_str = event.get("Jam", "")
                if not date_str or not time_range_str:
                    continue

                start_time_val, end_time_val = time_range_str.split("-")
                start_date_time_str = (
                    re.sub(r"^\w+, ", "", date_str) + " " + start_time_val
                )
                end_date_time_str = re.sub(r"^\w+, ", "", date_str) + " " + end_time_val

                for idn, eng in month_translation.items():
                    start_date_time_str = start_date_time_str.replace(idn, eng)
                    end_date_time_str = end_date_time_str.replace(idn, eng)

                # Jika tahun hanya 2 digit, tambahkan '20' di depannya
                def normalize_year(date_str):
                    parts = date_str.split()
                    if (
                        len(parts) >= 3 and len(parts[1]) > 0 and len(parts[2]) == 2
                    ):  # contoh: ['22', 'October', '25']
                        parts[2] = "20" + parts[2]
                        return " ".join(parts)
                    return date_str

                start_date_time_str = normalize_year(start_date_time_str)
                end_date_time_str = normalize_year(end_date_time_str)

                start_time_naive = datetime.strptime(
                    start_date_time_str, "%d %B %Y %H:%M"
                )
                end_time_naive = datetime.strptime(end_date_time_str, "%d %B %Y %H:%M")

                ics_content += (
                    "BEGIN:VEVENT\n"
                    f"SUMMARY:{event.get('Nama Matakuliah', 'Tanpa Nama')}\n"
                    f"DTSTART;TZID=Asia/Jakarta:{start_time_naive.strftime('%Y%m%dT%H%M%S')}\n"
                    f"DTEND;TZID=Asia/Jakarta:{end_time_naive.strftime('%Y%m%dT%H%M%S')}\n"
                    f"LOCATION:{event.get('Ruangan', 'Tidak Diketahui')}\n"
                    f"DESCRIPTION:Keterangan: {event.get('Keterangan', '-')}\\nPengajar: {event.get('Dosen', '-')}\n"
                    f"STATUS:{event.get('Status Kuliah', '-')}\n"
                    "END:VEVENT\n"
                )
            except Exception as e:
                logging.warning(f"Gagal konversi event: {e}")
                continue

        ics_content += "END:VCALENDAR\n"

        with open(ics_path, "w", encoding="utf-8") as f:
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


@app.route("/login", methods=["GET"])
@limiter.limit("5 per minute")  # Batasi cuma 5x percobaan per menit per IP
def login_page():
    # Ambil token dari session atau cookie
    token = session.get("access_token") or request.cookies.get("access_token")

    if token:
        try:
            secret = current_app.config.get("SECRET_KEY") or app.secret_key
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                options={"require": ["exp", "iat", "sub"]},
                leeway=30,
            )

            exp_time = datetime.fromtimestamp(payload["exp"], SCHEDULER_TZ)
            if exp_time < datetime.now(SCHEDULER_TZ):
                raise jwt.ExpiredSignatureError("Token expired")

            logging.info("User udah login, redirecting to index...")
            next_url = request.args.get("next", "")
            if not next_url.startswith("/") or next_url.startswith("//"):
                next_url = url_for("index")
            return redirect(next_url)
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
    return render_template("login.html", has_any_biometric=has_any_biometric)


# Logout Route 1 Session + Cookie
@app.route("/logout")
def logout_page():
    logging.info(f"User logging out...")

    # 1. Ambil refresh_token dari cookie
    refresh_token = request.cookies.get("refresh_token")

    # 2. PANGGIL FUNGSI DARI auth_api.py (JAUH LEBIH BERSIH!)
    if refresh_token:
        _revoke_refresh_token(refresh_token)
    else:
        logging.warning("Logout: Tidak menemukan refresh_token di cookie.")

    # 3. Buat response redirect (Sama kayak sebelumnya)
    resp = make_response(redirect(url_for("login_page")))

    # 4. Hapus session di server
    session.clear()

    # 5. Hapus KEDUA cookie di browser
    resp.set_cookie("access_token", "", expires=0, httponly=True, samesite="Lax")
    resp.set_cookie("refresh_token", "", expires=0, httponly=True, samesite="Lax")

    logging.info("Session and cookies cleared. Redirecting to login.")
    return resp


# Logout Route all Session + Cookie
@app.route("/logout-all")
@login_required  # <-- Ini penting, buat mastiin kita tau siapa user-nya
def logout_all_page():
    logging.info(f"User logging out from ALL devices...")

    # 1. Dapatkan user_id dari 'g'
    # (g.user diisi oleh decorator @login_required)
    if "user" in g and g.user.get("sub"):
        user_id = g.user["sub"]  # 'sub' adalah user_id di JWT
        logging.info(f"Revoking all sessions for user_id: {user_id}")

        # 2. Panggil fungsi internal dari auth_api.py
        _revoke_all_user_sessions(user_id)

    else:
        logging.warning("Logout All: Tidak bisa menemukan user_id dari token.")

    # 3. Hapus sesi LOKAL (sama persis kayak logout biasa)
    resp = make_response(redirect(url_for("login_page")))
    session.clear()
    resp.set_cookie("access_token", "", expires=0, httponly=True, samesite="Lax")
    resp.set_cookie("refresh_token", "", expires=0, httponly=True, samesite="Lax")

    logging.info("Current session cleared. Redirecting to login.")
    return resp


@app.route("/")
@login_required
def index():
    user_id = g.user.get("sub")
    role_id = g.user.get("role_id")

    # Jika dia role Mahasiswa Non-Sicyca (4), langsung lempar ke tools
    if role_id == 4:
        return redirect(url_for("tools_page"))

    # Jika dia role Konselor (5), arahkan ke dashboard konselor
    if role_id == 5:
        return redirect(url_for("konselor_dashboard"))

    # Cek apakah user punya kredensial Gate
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM gate_users WHERE user_id = %s", (user_id,))
    gate_exists = cursor.fetchone()
    cursor.close()
    conn.close()
    # Kalau dia Mahasiswa (3) tapi belum setup Gate, arahkan ke tools juga
    if not gate_exists and role_id == 3:
        return redirect(url_for("tools_page"))
    # logging.info(f"[INDEX DEBUG] Session keys:", list(session.keys()))
    print("[INDEX DEBUG] Session keys:", list(session.keys()))
    try:
        from models.schedule import user_schedule_model

        last_scraped, jadwal_data = user_schedule_model.get_schedules_by_user(user_id)
        calendar_uuid = user_schedule_model.get_or_create_calendar_uuid(user_id)

        # LAZY LOADING LOGIC
        needs_scrape = False
        if not jadwal_data and last_scraped == "Belum pernah di-scrape":
            needs_scrape = True
        elif last_scraped and last_scraped != "Belum pernah di-scrape":
            try:
                # Format dari scraper: "%A, %d %B %Y %H:%M:%S"
                # Kita coba fallback manual agar tidak kena masalah locale bahasa Indonesia
                # Jika repot diparse, cara gampang: cek umurnya kalau > 24 jam.
                # Sayangnya parse string %A, %d %B %Y agak tricky dengan locale.
                # Jadi kita biarkan user refresh manual kalau parse gagal. Tapi kita coba parse aja dulu.
                import locale
                dt_scraped = datetime.strptime(last_scraped, "%A, %d %B %Y %H:%M:%S")
                now = datetime.now()
                today_5am = now.replace(hour=5, minute=0, second=0, microsecond=0)
                
                if now >= today_5am and dt_scraped < today_5am:
                    needs_scrape = True
                elif now < today_5am and dt_scraped < (today_5am - timedelta(days=1)):
                    needs_scrape = True
            except ValueError:
                # Parse gagal karena locale (misal "Senin, 24 April 2026 ...")
                # Kita asumsikan aja butuh scrape kalau jadwal kosong
                if not jadwal_data: needs_scrape = True

        if needs_scrape:
            # Cegah double execution dengan mengecek status yang ada di memory
            status_jadwal = JADWAL_STATUS.get(user_id, {}).get("status")
            if status_jadwal != "loading":
                logging.info(f"[LAZY SCRAPE] Menjalankan jadwal otomatis untuk user_id: {user_id}")
                executor.submit(run_scraper_and_save, user_id)
                # Tambahkan fake message agar frontend tahu sedang loading
                last_scraped = "Memproses pembaruan otomatis di belakang layar..."

        if not jadwal_data and last_scraped == "Belum pernah di-scrape":
            msg = "JADWAL BELUM TERSEDIA. Sedang menarik jadwal di latar belakang..."
            return render_template(
                "index.html",
                jadwal_list=[],
                last_scraped=last_scraped,
                error_message=msg,
                calendar_uuid=calendar_uuid,
            )

        # Kirim data mentah ke template
        return render_template(
            "index.html",
            jadwal_list=jadwal_data,
            last_scraped=last_scraped,
            calendar_uuid=calendar_uuid,
        )

    except Exception as e:
        logging.error(f"Error di route index: {e}")
        return render_template(
            "index.html",
            jadwal_list=[],
            last_scraped=None,
            error_message=f"Terjadi error: {str(e)}",
        )


@app.route("/konselor")
@login_required
def konselor_dashboard():
    """Dashboard khusus untuk user dengan role Konselor."""
    role_id = g.user.get("role_id")

    # Hanya role Konselor (5) dan Super Admin (1) yang boleh akses
    if role_id not in [1, 5]:
        return redirect(url_for("index"))

    return render_template("konselorApp/indexKonselor.html")



# === KONSELOR: Jadwal Main ===
@app.route("/konselor/jadwal")
@login_required
def konselor_jadwal_main():
    role_id = g.user.get("role_id")
    if role_id not in [1, 5]:
        return redirect(url_for("index"))
    
    from controller.KonselorController import get_all_layanan
    return render_template("konselorApp/jadwalKonsul_konselor/jadwal_main.html", layanan_list=get_all_layanan())

@app.route("/konselor/jadwal/data")
@login_required
def konselor_jadwal_data():
    role_id = g.user.get("role_id")
    if role_id not in [1, 5]:
        return jsonify({"success": False, "message": "Akses ditolak"}), 403
        
    from controller.KonselorController import get_jadwal_by_date
    user_id = g.user.get("sub")
    
    today = datetime.now(SCHEDULER_TZ).strftime("%Y-%m-%d")
    jadwal_hari_ini = get_jadwal_by_date(user_id, today, today)
    
    tomorrow = (datetime.now(SCHEDULER_TZ) + timedelta(days=1)).strftime("%Y-%m-%d")
    jadwal_mendatang = get_jadwal_by_date(user_id, tomorrow)
    
    return jsonify({
        "success": True,
        "hari_ini": jadwal_hari_ini,
        "mendatang": jadwal_mendatang
    })

@app.route("/konselor/jadwal/create", methods=["POST"])
@login_required
def konselor_jadwal_create():
    role_id = g.user.get("role_id")
    if role_id not in [1, 5]:
        return jsonify({"success": False, "message": "Akses ditolak"}), 403
        
    from controller.KonselorController import create_jadwal
    user_id = g.user.get("sub")
    success, msg = create_jadwal(user_id, request.form)
    return jsonify({"success": success, "message": msg})

@app.route("/konselor/jadwal/reschedule", methods=["POST"])
@login_required
def konselor_jadwal_reschedule():
    role_id = g.user.get("role_id")
    if role_id not in [1, 5]:
        return jsonify({"success": False, "message": "Akses ditolak"}), 403
        
    from controller.KonselorController import reschedule_jadwal
    user_id = g.user.get("sub")
    jadwal_id = request.form.get("id")
    success, msg = reschedule_jadwal(jadwal_id, user_id, request.form)
    return jsonify({"success": success, "message": msg})

@app.route("/konselor/jadwal/update-status", methods=["POST"])
@login_required
def konselor_jadwal_update_status():
    role_id = g.user.get("role_id")
    if role_id not in [1, 5]:
        return jsonify({"success": False, "message": "Akses ditolak"}), 403
        
    from controller.KonselorController import update_status_jadwal
    user_id = g.user.get("sub")
    jadwal_id = request.form.get("id")
    status = request.form.get("status")
    
    if not jadwal_id or not status:
        return jsonify({"success": False, "message": "Data tidak lengkap"}), 400
        
    success, msg = update_status_jadwal(jadwal_id, user_id, status)
    return jsonify({"success": success, "message": msg})

@app.route("/konselor/jadwal/slots")
@login_required
def konselor_jadwal_slots():
    role_id = g.user.get("role_id")
    if role_id not in [1, 5]:
        return jsonify({"success": False, "message": "Akses ditolak"}), 403
        
    from controller.KonselorController import get_available_slots
    user_id = g.user.get("sub")
    tanggal = request.args.get("tanggal")
    if not tanggal:
         return jsonify({"success": False, "message": "Tanggal wajib diisi"})
         
    slots = get_available_slots(user_id, tanggal)
    return jsonify({"success": True, "slots": slots})

@app.route("/konselor/live-session")
@login_required
def konselor_live_session():
    role_id = g.user.get("role_id")
    if role_id not in [1, 5]:
        return redirect(url_for("index"))
        
    from controller.KonselorController import get_jadwal_detail, update_status_jadwal, get_all_kategori, get_all_tindak_lanjut
    user_id = g.user.get("sub")
    jadwal_id = request.args.get("id")
    
    if not jadwal_id:
        return redirect(url_for("konselor_jadwal_main"))
        
    jadwal = get_jadwal_detail(jadwal_id)
    if not jadwal or str(jadwal['konselor_user_id']) != str(user_id):
         flash("Jadwal tidak ditemukan.", "error")
         return redirect(url_for("konselor_jadwal_main"))
         
    if jadwal['status'] in ['Selesai', 'Dibatalkan']:
         flash("Sesi sudah selesai atau dibatalkan.", "error")
         return redirect(url_for("konselor_jadwal_main"))
         
    if jadwal['status'] in ['Menunggu', 'Jeda']:
        update_status_jadwal(jadwal_id, user_id, 'Berlangsung')
        # Re-fetch untuk mendapatkan update waktu_mulai dan total_pause_ms yang baru
        jadwal = get_jadwal_detail(jadwal_id)
        
    if jadwal.get('waktu_mulai'):
        from datetime import datetime
        if isinstance(jadwal['waktu_mulai'], datetime):
             jadwal['waktu_mulai'] = jadwal['waktu_mulai'].isoformat()
        else:
             jadwal['waktu_mulai'] = str(jadwal['waktu_mulai'])
        
    return render_template("konselorApp/jadwalKonsul_konselor/live_session.html", 
                           jadwal=jadwal, 
                           kategori_list=get_all_kategori(), 
                           tindak_lanjut_list=get_all_tindak_lanjut())

@app.route("/konselor/live-session/finish", methods=["POST"])
@login_required
def konselor_live_session_finish():
    role_id = g.user.get("role_id")
    if role_id not in [1, 5]:
        return jsonify({"success": False, "message": "Akses ditolak"}), 403
        
    from controller.KonselorController import update_status_jadwal, get_jadwal_detail, create_sesi
    user_id = g.user.get("sub")
    jadwal_id = request.form.get("jadwal_id")
    
    jadwal = get_jadwal_detail(jadwal_id)
    if not jadwal or str(jadwal['konselor_user_id']) != str(user_id):
        return jsonify({"success": False, "message": "Jadwal tidak ditemukan."})
        
    form_data = {
        'nim': jadwal['nim'],
        'nama': jadwal['nama'],
        'prodi': jadwal['prodi'],
        'jenis_layanan_id': jadwal['layanan_id'],
        'tanggal_sesi': jadwal['tanggal'],
        'topik': request.form.get('topik'),
        'kategori_masalah_ids': request.form.get('kategori_masalah_ids'),
        'catatan_kesimpulan': request.form.get('catatan_kesimpulan'),
        'tindak_lanjut': request.form.get('tindak_lanjut'),
        'waktu_mulai': request.form.get('waktu_mulai'),
        'waktu_selesai': request.form.get('waktu_selesai')
    }
    
    success_sesi, msg_sesi = create_sesi(user_id, form_data)
    if success_sesi:
        update_status_jadwal(jadwal_id, user_id, 'Selesai')
        return jsonify({"success": True, "message": "Sesi berhasil diselesaikan."})
    else:
        return jsonify({"success": False, "message": msg_sesi})


# === KONSELOR: Catat Sesi Baru ===
@app.route("/konselor/catat", methods=["GET", "POST"])
@login_required
def konselor_catat_sesi():
    """Form pencatatan sesi konseling baru."""
    role_id = g.user.get("role_id")
    if role_id not in [1, 5]:
        return redirect(url_for("index"))

    from controller.KonselorController import (
        get_all_kategori, get_all_layanan, get_all_tindak_lanjut, create_sesi
    )

    if request.method == "POST":
        user_id = g.user.get("sub")
        success, message = create_sesi(user_id, request.form)
        return jsonify({"success": success, "message": message})

    # GET — render form
    return render_template(
        "konselorApp/catat_sesi.html",
        prodi_list=majorID,
        kategori_list=get_all_kategori(),
        jenis_layanan_list=get_all_layanan(),
        tindak_lanjut_list=get_all_tindak_lanjut()
    )


# === KONSELOR: Lookup NIM via Scrapper ===
@app.route("/konselor/lookup-nim")
@login_required
def konselor_lookup_nim():
    """AJAX endpoint: cari data mahasiswa dari Sicyca via NIM."""
    role_id = g.user.get("role_id")
    if role_id not in [1, 5]:
        return jsonify({"success": False, "message": "Akses ditolak"}), 403

    from controller.KonselorController import censor_name

    nim = request.args.get("nim", "").strip()
    if not nim:
        return jsonify({"success": False, "message": "NIM wajib diisi."})

    try:
        # Jalankan di thread pool (sama kayak fitur komunitas)
        # Supaya _get_current_user_id tidak fallback ke bot user
        user_id = g.user.get("sub")
        future = executor.submit(search_mahasiswa, nim, user_id=user_id)
        df = future.result(timeout=30)
        if df.empty:
            return jsonify({"success": False, "message": "Data mahasiswa tidak ditemukan."})

        row = df.iloc[0]
        data = {k.lower(): v for k, v in row.items()}

        nama_raw = data.get("nama", "")
        dosen_wali = data.get("dosen wali", "")
        prodi_raw = data.get("prodi", "")

        # Coba resolve prodi dari NIM via majorID
        prodi_resolved = ""
        if nim and len(nim) >= 7:
            kode_prodi = nim[2:7]
            prodi_resolved = majorID.get(kode_prodi, prodi_raw)
        else:
            prodi_resolved = prodi_raw

        return jsonify({
            "success": True,
            "nama_raw": nama_raw,
            "nama_sensor": censor_name(nama_raw),
            "dosen_wali": dosen_wali,
            "prodi": prodi_resolved
        })
    except Exception as e:
        logging.error(f"[Konselor] Lookup NIM error: {e}")
        return jsonify({"success": False, "message": "Gagal lookup data mahasiswa."})


# === KONSELOR: Dashboard Rekap ===
@app.route("/konselor/rekap")
@login_required
def konselor_rekap():
    """Halaman dashboard rekap sesi konseling."""
    role_id = g.user.get("role_id")
    if role_id not in [1, 5]:
        return redirect(url_for("index"))

    from controller.KonselorController import get_all_kategori, get_all_layanan, get_all_tindak_lanjut
    return render_template(
        "konselorApp/rekap_sesi.html",
        prodi_list=majorID,
        kategori_list=get_all_kategori(),
        jenis_layanan_list=get_all_layanan(),
        tindak_lanjut_list=get_all_tindak_lanjut()
    )


# === KONSELOR: Excel Import/Export ===
@app.route("/konselor/template/download")
@login_required
def konselor_download_template():
    """Download template excel untuk import sesi"""
    from controller.KonselorController import download_template_excel
    role_id = g.user.get("role_id")
    if role_id not in [1, 5]:
        return jsonify({"success": False, "message": "Akses ditolak"}), 403
    return download_template_excel()

@app.route("/konselor/sesi/import", methods=["POST"])
@login_required
def konselor_import_sesi():
    """Import sesi dari excel dan auto-fill dari Sicyca"""
    from controller.KonselorController import import_sesi_excel
    role_id = g.user.get("role_id")
    if role_id not in [1, 5]:
        return jsonify({"success": False, "message": "Akses ditolak"}), 403
    
    # Passing the current user_id for the scraper to use
    user_id = g.user.get("sub")
    return import_sesi_excel(request, user_id)

# === KONSELOR: Rekap Data (JSON) ===
@app.route("/konselor/rekap/data")
@login_required
def konselor_rekap_data():
    """JSON data rekap + riwayat sesi."""
    role_id = g.user.get("role_id")
    if role_id not in [1, 5]:
        return jsonify({"success": False, "message": "Akses ditolak"}), 403

    from controller.KonselorController import get_rekap, get_riwayat_sesi
    user_id = g.user.get("sub")
    tahun = request.args.get("tahun", type=int)

    stats = get_rekap(user_id, tahun=tahun)
    sessions = get_riwayat_sesi(user_id, tahun=tahun)

    # Serialize dates
    for s in sessions:
        if s.get("tanggal_sesi"):
            s["tanggal_sesi"] = str(s["tanggal_sesi"])
        if s.get("created_at"):
            s["created_at"] = str(s["created_at"])

    return jsonify({"success": True, "stats": stats, "sessions": sessions})


# === KONSELOR: Hapus Sesi ===
@app.route("/konselor/sesi/delete", methods=["POST"])
@login_required
def konselor_delete_sesi():
    """Hapus sesi konseling."""
    role_id = g.user.get("role_id")
    if role_id not in [1, 5]:
        return jsonify({"success": False, "message": "Akses ditolak"}), 403

    from controller.KonselorController import delete_sesi
    user_id = g.user.get("sub")
    session_id = request.form.get("session_id")

    if not session_id:
        return jsonify({"success": False, "message": "ID sesi tidak valid."})

    success, message = delete_sesi(session_id, user_id)
    return jsonify({"success": success, "message": message})


# === KONSELOR: Update Sesi ===
@app.route("/konselor/sesi/update", methods=["POST"])
@login_required
def konselor_update_sesi():
    """Update sesi konseling."""
    role_id = g.user.get("role_id")
    if role_id not in [1, 5]:
        return jsonify({"success": False, "message": "Akses ditolak"}), 403

    from controller.KonselorController import update_sesi
    user_id = g.user.get("sub")
    session_id = request.form.get("session_id")

    if not session_id:
        return jsonify({"success": False, "message": "ID sesi tidak valid."})

    success, message = update_sesi(session_id, user_id, request.form)
    return jsonify({"success": success, "message": message})


# === KONSELOR: Kelola Master Data ===
@app.route("/konselor/kelola")
@login_required
def konselor_kelola_master():
    """Halaman CRUD master data (Kategori Masalah & Jenis Layanan)."""
    role_id = g.user.get("role_id")
    if role_id not in [1, 5]:
        return redirect(url_for("index"))

    from controller.KonselorController import get_all_kategori, get_all_layanan, get_all_tindak_lanjut
    return render_template(
        "konselorApp/kelola_master.html",
        kategori_list=get_all_kategori(),
        layanan_list=get_all_layanan(),
        tindak_lanjut_list=get_all_tindak_lanjut()
    )


# === KONSELOR: CRUD Kategori Masalah ===
@app.route("/konselor/kategori", methods=["POST"])
@login_required
def konselor_kategori():
    """CRUD untuk kategori masalah."""
    role_id = g.user.get("role_id")
    if role_id not in [1, 5]:
        return jsonify({"success": False, "message": "Akses ditolak"}), 403

    from controller.KonselorController import (
        create_kategori, update_kategori, delete_kategori
    )

    action = request.form.get("action")
    nama = request.form.get("nama", "").strip()
    item_id = request.form.get("id", type=int)

    if action == "create":
        if not nama:
            return jsonify({"success": False, "message": "Nama tidak boleh kosong."})
        success, message = create_kategori(nama)
        # Get new ID
        new_id = None
        if success:
            from models.konselor import kategori_masalah_model
            all_kat = kategori_masalah_model.get_all()
            for k in all_kat:
                if k["nama"] == nama:
                    new_id = k["id"]
                    break
        return jsonify({"success": success, "message": message, "id": new_id})

    elif action == "update":
        if not item_id or not nama:
            return jsonify({"success": False, "message": "Data tidak lengkap."})
        success, message = update_kategori(item_id, nama)
        return jsonify({"success": success, "message": message})

    elif action == "delete":
        if not item_id:
            return jsonify({"success": False, "message": "ID tidak valid."})
        success, message = delete_kategori(item_id)
        return jsonify({"success": success, "message": message})

    return jsonify({"success": False, "message": "Action tidak valid."})


# === KONSELOR: CRUD Jenis Layanan ===
@app.route("/konselor/layanan", methods=["POST"])
@login_required
def konselor_layanan():
    """CRUD untuk jenis layanan."""
    role_id = g.user.get("role_id")
    if role_id not in [1, 5]:
        return jsonify({"success": False, "message": "Akses ditolak"}), 403

    from controller.KonselorController import (
        create_layanan, update_layanan, delete_layanan
    )

    action = request.form.get("action")
    nama = request.form.get("nama", "").strip()
    item_id = request.form.get("id", type=int)

    if action == "create":
        if not nama:
            return jsonify({"success": False, "message": "Nama tidak boleh kosong."})
        success, message = create_layanan(nama)
        new_id = None
        if success:
            from models.konselor import jenis_layanan_model
            all_lay = jenis_layanan_model.get_all()
            for l in all_lay:
                if l["nama"] == nama:
                    new_id = l["id"]
                    break
        return jsonify({"success": success, "message": message, "id": new_id})

    elif action == "update":
        if not item_id or not nama:
            return jsonify({"success": False, "message": "Data tidak lengkap."})
        success, message = update_layanan(item_id, nama)
        return jsonify({"success": success, "message": message})

    elif action == "delete":
        if not item_id:
            return jsonify({"success": False, "message": "ID tidak valid."})
        success, message = delete_layanan(item_id)
        return jsonify({"success": success, "message": message})

    return jsonify({"success": False, "message": "Action tidak valid."})


# === KONSELOR: CRUD Tindak Lanjut ===
@app.route("/konselor/tindak_lanjut", methods=["POST"])
@login_required
def konselor_tindak_lanjut():
    """CRUD untuk tindak lanjut."""
    role_id = g.user.get("role_id")
    if role_id not in [1, 5]:
        return jsonify({"success": False, "message": "Akses ditolak"}), 403

    from controller.KonselorController import (
        create_tindak_lanjut, update_tindak_lanjut, delete_tindak_lanjut
    )

    action = request.form.get("action")
    nama = request.form.get("nama", "").strip()
    item_id = request.form.get("id", type=int)

    if action == "create":
        if not nama:
            return jsonify({"success": False, "message": "Nama tidak boleh kosong."})
        success, message = create_tindak_lanjut(nama)
        new_id = None
        if success:
            from models.konselor import tindak_lanjut_model
            all_tl = tindak_lanjut_model.get_all()
            for tl in all_tl:
                if tl["nama"] == nama:
                    new_id = tl["id"]
                    break
        return jsonify({"success": success, "message": message, "id": new_id})

    elif action == "update":
        if not item_id or not nama:
            return jsonify({"success": False, "message": "Data tidak lengkap."})
        success, message = update_tindak_lanjut(item_id, nama)
        return jsonify({"success": success, "message": message})

    elif action == "delete":
        if not item_id:
            return jsonify({"success": False, "message": "ID tidak valid."})
        success, message = delete_tindak_lanjut(item_id)
        return jsonify({"success": success, "message": message})

    return jsonify({"success": False, "message": "Action tidak valid."})


@app.route("/tools")
@login_required
def tools_page():
    role_id = g.user.get("role_id", 3)

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Kalau Super Admin (1), ambil semua daftar tool. Kalau bukan, cek izinnya.
    if role_id == 1:
        cursor.execute("SELECT route_name FROM tools")
    else:
        cursor.execute(
            """
            SELECT t.route_name
            FROM tools t
            JOIN role_permissions rp ON t.id = rp.tool_id
            WHERE rp.role_id = %s AND rp.is_allowed = 1
        """,
            (role_id,),
        )

    allowed_tools_db = cursor.fetchall()
    # Ubah formatnya jadi list biasa misal: ['logbook_magang', 'cari_komunitas']
    allowed_tools = [t["route_name"] for t in allowed_tools_db]

    cursor.close()
    conn.close()

    # Kirim list allowed_tools ke HTML
    return render_template("tools.html", allowed_tools=allowed_tools)


@app.route("/pembayaran")
@login_required
@check_permission("pembayaran_qris")
def pembayaran_page():
    """Halaman pembayaran QRIS"""
    return render_template("pembayaran.html")


@app.route("/account")
@login_required
def account_page():
    user_id = g.user.get("sub")

    # 1. Ambil data gate user kalau udah ada
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT gate_username FROM gate_users WHERE user_id = %s", (user_id,)
    )
    gate_info = cursor.fetchone()

    # Ambil info user dasar juga
    cursor.execute(
        "SELECT username, email, role_id FROM users WHERE id = %s", (user_id,)
    )
    user_info = cursor.fetchone()

    cursor.close()
    conn.close()

    gate_username = gate_info["gate_username"] if gate_info else ""

    # Google account status (unified: Calendar + Drive)
    google_user = google_cal_service.get_token_by_user(user_id)

    return render_template(
        "account.html",
        gate_username=gate_username,
        user_info=user_info,
        google_user=google_user,
    )


@app.route("/account/update-gate", methods=["POST"])
@login_required
def update_gate_credentials():
    user_id = g.user.get("sub")
    gate_username = request.form.get("gate_username")
    gate_password = request.form.get("gate_password")

    if not gate_username or not gate_password:
        flash("Username dan Password Sicyca wajib diisi!", "error")
        return redirect(url_for("account_page"))

    try:
        # Enkripsi Password pakai Fernet (sesuai skema database lu)
        # Pastikan lu punya variabel GATE_ENCRYPTION_KEY di file .env lu
        gate_secret = os.getenv("GATE_ENCRYPTION_KEY")
        if not gate_secret:
            raise ValueError("GATE_ENCRYPTION_KEY tidak ditemukan di environment!")

        cipher_suite = Fernet(gate_secret.encode("utf-8"))
        encrypted_password = cipher_suite.encrypt(gate_password.encode("utf-8")).decode(
            "utf-8"
        )

        conn = get_connection()
        cursor = conn.cursor()

        # Gunakan sistem UPSERT (Kalau belum ada di-insert, kalau udah ada di-update)
        query = """
            INSERT INTO gate_users (user_id, gate_username, gate_password)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
            gate_username = EXCLUDED.gate_username,
            gate_password = EXCLUDED.gate_password
        """
        cursor.execute(query, (user_id, gate_username, encrypted_password))
        conn.commit()

        cursor.close()
        conn.close()

        flash("Kredensial Sicyca berhasil diperbarui!", "success")
    except Exception as e:
        logging.error(f"[Account] Error update gate credentials: {e}")
        flash("Gagal memperbarui kredensial Sicyca.", "error")

    return redirect(url_for("account_page"))


@app.route("/account/update-profile", methods=["POST"])
@login_required
def update_profile():
    user_id = g.user.get("sub")  # Ambil ID user yang lagi login
    username = request.form.get("username")
    email = request.form.get("email")

    if not username:
        flash("Username tidak boleh kosong!", "error")
        return redirect(url_for("account_page"))

    # Panggil controller yang udah ada
    success, message = update_user_detail(user_id, username, email)

    if success:
        flash("Profil berhasil diperbarui!", "success")
    else:
        flash(message, "error")

    return redirect(url_for("account_page"))


@app.route("/account/update-password", methods=["POST"])
@login_required
def update_password():
    user_id = g.user.get("sub")  # Ambil ID user yang lagi login
    new_password = request.form.get("new_password")

    # Panggil Controller
    success, message = update_user_password(user_id, new_password)

    if success:
        flash(message, "success")
    else:
        flash(message, "error")

    return redirect(url_for("account_page"))


# ============================
# JADWAL SHOLAT & KALENDER ROUTES
# ============================
from models.prayer import prayer_settings_model, ramadan_config_model


@app.route("/muslim-tools")
@login_required
def muslim_tools_page():
    """Halaman Muslim Tools — jadwal sholat, kalender Hijriah & Ramadhan."""
    return render_template("muslimTools/muslimTools.html")


@app.route("/account/prayer-settings", methods=["GET"])
@login_required
def get_prayer_settings():
    """Ambil settings prayer user saat ini."""
    user_id = g.user.get("sub")
    settings = prayer_settings_model.get_by_user_id(user_id)
    return jsonify({"success": True, "settings": settings})


@app.route("/account/prayer-settings", methods=["POST"])
@login_required
def save_prayer_settings():
    """Simpan/update settings prayer user."""
    user_id = g.user.get("sub")

    data = {
        "preference": request.form.get("preference", "nu"),
        "city": request.form.get("city", "Surabaya"),
        "state": request.form.get("state", ""),
        "country": request.form.get("country", "Indonesia"),
        "hijri_adj": int(request.form.get("hijri_adj", 0)),
    }

    # Validasi preference
    if data["preference"] not in ("muhammadiyah", "nu"):
        return jsonify({"success": False, "message": "Preferensi tidak valid."}), 400

    success = prayer_settings_model.upsert(user_id, data)
    if success:
        return jsonify({"success": True, "message": "Preferensi berhasil disimpan."})
    return jsonify({"success": False, "message": "Gagal menyimpan preferensi."}), 500


@app.route("/admin/ramadan-config", methods=["GET"])
@login_required
def get_ramadan_config():
    """Ambil semua Ramadan config (admin-only)."""
    role_id = g.user.get("role_id", 3)
    if role_id not in (1, 2):
        return jsonify({"success": False, "message": "Akses ditolak."}), 403

    configs = ramadan_config_model.get_all()

    # Convert date objects to string for JSON serialization
    for cfg in configs:
        for key in ["start_ramadan_muhammadiyah", "start_ramadan_pemerintah"]:
            if cfg.get(key) and hasattr(cfg[key], "isoformat"):
                cfg[key] = cfg[key].isoformat()
        for key in ["created_at", "updated_at"]:
            if cfg.get(key) and hasattr(cfg[key], "isoformat"):
                cfg[key] = cfg[key].isoformat()

    return jsonify({"success": True, "configs": configs})


@app.route("/admin/ramadan-config", methods=["POST"])
@login_required
def save_ramadan_config():
    """Simpan/update Ramadan config (admin-only)."""
    role_id = g.user.get("role_id", 3)
    user_id = g.user.get("sub")

    if role_id not in (1, 2):
        return jsonify({"success": False, "message": "Akses ditolak."}), 403

    data = {
        "hijri_year": request.form.get("hijri_year", type=int),
        "start_ramadan_muhammadiyah": request.form.get("start_ramadan_muhammadiyah"),
        "start_ramadan_pemerintah": request.form.get("start_ramadan_pemerintah"),
        "total_days": request.form.get("total_days", 30, type=int),
    }

    if not data["hijri_year"]:
        return jsonify({"success": False, "message": "Tahun Hijriah wajib diisi."}), 400

    success = ramadan_config_model.upsert(data, updated_by=user_id)
    if success:
        return jsonify(
            {"success": True, "message": "Konfigurasi Ramadhan berhasil disimpan."}
        )
    return jsonify({"success": False, "message": "Gagal menyimpan konfigurasi."}), 500


# Route untuk reset session scraper (hapus cookies.json)
@app.route("/reset-scraper-session")
@login_required
def reset_scraper_session():
    try:
        # Ambil user_id dari context 'g' (dari @login_required)
        if "user" in g and g.user.get("sub"):
            user_id = g.user["sub"]

            # Panggil Controller untuk hapus sesi di Memori & Database
            reset_session_user(user_id)

            logging.info(
                f"[Reset Scraper] Sesi untuk User ID {user_id} berhasil di-reset sepenuhnya (DB & RAM)."
            )
        else:
            logging.warning(
                "[Reset Scraper] Gagal reset: User ID tidak ditemukan dalam token."
            )

    except Exception as e:
        logging.error(f"[Reset Scraper] Error: {e}")

    # Kembali ke dashboard
    return redirect(url_for("index"))


# Route untuk refresh jadwal manual
@app.route("/refresh-jadwal")
@login_required
def refresh_jadwal_route():
    # Jalankan scraper di background agar tidak memblokir
    user_id = g.user.get("sub")
    executor.submit(run_scraper_and_save, user_id)
    # Langsung redirect, JavaScript akan menangani update UI
    return redirect(url_for("index"))


@app.route("/kalendar/<uuid>")
def kalendar_ics_uuid(uuid):
    try:
        from models.schedule import user_schedule_model

        waktu, events, user_id = user_schedule_model.get_schedules_by_uuid(uuid)

        if not user_id:
            return "<h3>Kalender tidak valid atau tidak ditemukan.</h3>", 404

        user_ics_file = f"jadwal_kegiatan_{user_id}.ics"

        # Simpan jadi file ICS
        create_ics_for_user(user_id, user_ics_file)

        logging.info(f"File ICS UUID {uuid} dibuat berdasarkan data terakhir: {waktu}")

        return send_from_directory(
            os.path.abspath("."),
            path=user_ics_file,
            as_attachment=True,
            download_name=f"jadwal_kuliah_{datetime.now().strftime('%Y%m%d_%H%M')}.ics",
        )

    except (FileNotFoundError, ValueError) as ve:
        return f"<h3>{str(ve)}</h3>", 404
    except Exception as e:
        return f"<pre>Error saat membuat ICS: {str(e)}</pre>", 500


@app.route("/pencarian-komunitas", methods=["GET"])
@login_required
def pencarian_komunitas_route():
    return render_template("undika/sicyca/pencarian_mhsstaff.html")


@app.route("/cari-mahasiswa")
@login_required
def cari_mahasiswa_redirect():
    return redirect(url_for("pencarian_komunitas_route"))


@app.route("/log-program")
@login_required
@check_permission("log_program")
def log_program():
    log_content = "Membaca log..."
    if os.path.exists(log_file):
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            lines.reverse()
            log_content = "".join(lines)
    return render_template("log_page.html", log_content=log_content)


@app.route("/sosmed-download")
@login_required
@check_permission("sosmed_download")
def sosmed_download():
    """Menyajikan file HTML utama."""
    return render_template("downloadSosmed.html")


@app.route("/gate_undika")
@login_required
def gate_undika():
    user_id = g.user.get("sub")
    role_id = g.user.get("role_id")

    # Jika dia role Mahasiswa Non-Sicyca (4), langsung lempar ke tools
    if role_id == 4:
        return redirect(url_for("tools_page"))
    # Cek apakah user punya kredensial Gate
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM gate_users WHERE user_id = %s", (user_id,))
    gate_exists = cursor.fetchone()
    cursor.close()
    conn.close()
    # Kalau dia Mahasiswa (3) tapi belum setup Gate, arahkan ke tools juga
    if not gate_exists and role_id == 3:
        return redirect(url_for("tools_page"))

    return render_template("undika/gate/gateUndika.html")


# === SSO REDIRECT LAUNCH ===
GATE_LAUNCH_APPS = {
    "brilian": "https://mybrilian.dinamika.ac.id",
    "support": "https://support.dinamika.ac.id",
    "prgo": "https://intranet.dinamika.ac.id/pr-go",
    "sicyca": "https://sicyca.dinamika.ac.id",
    "afiliasi": "https://afiliasi.dinamika.ac.id",
    "pkm": "https://pkm.dinamika.ac.id",
}


@app.route("/gate/launch/<app_key>")
@login_required
def gate_launch_app(app_key):
    """Browser-side Gate Login: POST credentials ke Gate dari browser user."""
    target_url = GATE_LAUNCH_APPS.get(app_key)
    if not target_url:
        flash("Aplikasi tidak ditemukan.", "error")
        return redirect(url_for("gate_undika"))

    user_id = g.user.get("sub")
    result = gate_sso_launch(user_id, target_url)

    if not result:
        flash(
            "Gagal menyiapkan login. Pastikan kredensial Gate sudah di-setup.", "error"
        )
        return redirect(url_for("gate_undika"))

    # Render HTML auto-submit form
    html = _build_gate_login_html(
        csrf_token=result["csrf_token"],
        userid=result["userid"],
        password=result["password"],
        target_url=result["target_url"],
    )
    return html


@app.route("/sicyca_undika")
@login_required
def sicyca_undika():
    """Menyajikan file HTML utama dan mengirimkan data lengkap (Profil, Jadwal, SKS, Nilai, SSKM)."""
    user_id = g.user.get("sub")

    # ================= 1. Credentials & Profil =================
    gate_model = GateUser()
    _, username, _ = gate_model.get_credentials_by_user_id(user_id)
    nim = username if username else "-"

    profil = {
        "nama": "Mahasiswa",
        "nim": nim,
        "prodi": "-",
        "dosen_wali": "-",
        "foto_profil": url_for("static", filename="no_photo.jpg"),
        "ipk": "-",
        "ips": "-",
    }

    if nim != "-":
        profil["foto_profil"] = url_for(
            "api.get_my_profile_photo"
        )  # Pastikan route api.get_my_profile_photo ada
        try:
            user_id = g.user.get("sub")
            df_mhs = search_mahasiswa(
                nim, user_id=user_id
            )  # Pastikan fungsi search_mahasiswa sudah diimport
            if not df_mhs.empty:
                row = df_mhs.iloc[0]
                profil["nama"] = row.get("Nama", profil["nama"])
                profil["dosen_wali"] = row.get("Dosen Wali", profil["dosen_wali"])

                # Logika Prodi
                if nim and len(nim) >= 7:
                    kodeprodi = nim[2:7]  # Ambil digit ke-3 sampai 7 dari NIM
                    # Ambil dari dictionary majorID, atau fallback ke data excel, atau default "-"
                    profil["prodi"] = majorID.get(kodeprodi, row.get("Prodi", "-"))
        except Exception as e:
            logging.error(f"[Sicyca Undika] Error fetch profile: {e}")

    # ================= 2. Jadwal Hari Ini =================
    jadwal_hari_ini = []
    hari_ini_str = ""
    try:
        days_id = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
        months_id = [
            "",
            "Januari",
            "Februari",
            "Maret",
            "April",
            "Mei",
            "Juni",
            "Juli",
            "Agustus",
            "September",
            "Oktober",
            "November",
            "Desember",
        ]
        now = datetime.now(SCHEDULER_TZ)  # Pastikan SCHEDULER_TZ diimport
        hari_ini_str = (
            f"{days_id[now.weekday()]}, {now.day} {months_id[now.month]} {now.year}"
        )

        from models.schedule import user_schedule_model

        _, all_jadwal = user_schedule_model.get_schedules_by_user(user_id)

        for j in all_jadwal:
            # Filter sederhana berdasarkan string hari
            hari_tgl = j.get("Hari, Tanggal", "")
            if days_id[now.weekday()].lower() in hari_tgl.lower():
                jadwal_hari_ini.append(
                    {
                        "nama_mk": j.get("Nama Matakuliah", "-"),
                        "jam": j.get("Jam", "-"),
                        "ruang": j.get("Ruang", "-"),
                        "dosen": j.get("Dosen", "-"),
                    }
                )
    except Exception as e:
        logging.error(f"[Sicyca Undika] Error fetch jadwal: {e}")

    # ================= 3. Data Akademik (SKS, Nilai, SSKM) =================
    # A. Fetch SKS (Termasuk IPK/IPS)
    sks_tempuh = 0
    semester_est = 1
    try:
        sks_raw = fetch_sks(user_id=user_id)  # Pastikan fungsi fetch_sks diimport
        if sks_raw and "data" in sks_raw:
            data_sks = sks_raw["data"]
            sks_tempuh = int(data_sks.get("sks_tempuh", 0))

            # Estimasi Semester: (SKS + 19) // 20
            if sks_tempuh > 0:
                semester_est = (sks_tempuh + 19) // 20
            else:
                semester_est = 1

            # Simpan IPK/IPS ke profil sementara
            if "ipk" in data_sks:
                profil["ipk"] = data_sks["ipk"]
            if "ips" in data_sks:
                profil["ips"] = data_sks["ips"]

    except Exception as e:
        logging.error(f"[Sicyca] Error fetch SKS: {e}")

    # B. Fetch Nilai Ujian
    # B. Fetch Nilai Ujian
    nilai_rows = []
    try:
        # GANTI DARI "nilaiujian" KE "dashboard_nilai_ujian"
        # Agar strukturnya sesuai dengan tabel kecil di dashboard (Matakuliah & NILAI)
        nilai_raw = dahsboard_nilai({"t": "dashboard_nilai_ujian"}, user_id=user_id)

        if nilai_raw.get("success") and nilai_raw.get("tables"):
            raw_rows = nilai_raw["tables"][0].get("rows", [])

            for r in raw_rows:
                nilai_rows.append(
                    {
                        "matkul": r.get("Matakuliah", "-"),
                        # Dashboard tidak punya kolom UTS/UAS, jadi kita strip atau kosongkan
                        "uts": "-",
                        "uas": "-",
                        # Ambil Nilai (di dashboard isinya Angka: 85, 100, dst)
                        "grade": r.get("NILAI", "-"),
                    }
                )

            logging.info(
                f"[Sicyca Undika] Nilai Dashboard found: {len(nilai_rows)} items"
            )

    except Exception as e:
        logging.error(f"[Sicyca Undika] Error fetch Nilai: {e}")

    # C. Fetch SSKM
    sskm_poin = 0
    sskm_persen = 0
    try:
        sskm_result = fetch_sskm_data(
            user_id=user_id
        )  # Pastikan fetch_sskm_data diimport

        if sskm_result["success"]:
            sskm_poin = sskm_result["total_poin"]

            # Hitung Persentase (Target 100 poin untuk lulus)
            sskm_persen = int((sskm_poin / 100) * 100)
            if sskm_persen > 100:
                sskm_persen = 100

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
        "sskm_persen": sskm_persen,
    }

    return render_template("undika/sicyca/dashboardsicycaUndika.html", data=data)


@app.route("/krs_sicyca")
@login_required
def krs_sicyca():
    """Menyajikan file HTML utama."""
    return render_template("undika/sicyca/krsSicyca.html")


@app.route("/sskm_record")
# @login_required
def sskm_record():
    """Menyajikan file HTML utama."""
    return render_template("sskm-record.html")


# ============================
# MANAJEMEN ULTAH ROUTES (SSR)
# ============================
import base64

from scrapper_requests import fetch_data_ultah, fetch_photo_from_sicyca


@app.route("/manajemenUltah")
@login_required
@check_permission("manajemen_ultah")
def manajemen_ultah():
    """Halaman utama - render data dari DB + SICYCA"""
    user_id = g.user.get("sub")

    db_records = ultah_model.get_all()

    sicyca_data = fetch_data_ultah()
    sicyca_list = sicyca_data.get("rows", []) if not sicyca_data.get("error") else []

    existing_names = {r["nama"].lower() for r in db_records}
    sicyca_filtered = [
        s for s in sicyca_list if s.get("nama", "").lower() not in existing_names
    ]

    # Get Google account status
    google_info = google_cal_service.get_token_by_user(user_id)

    return render_template(
        "manajemenUltah.html",
        records=db_records,
        sicyca_list=sicyca_filtered,
        today=sicyca_data.get("tanggal_hari_ini", ""),
        google_user=google_info,
    )


@app.route("/manajemenUltah/add", methods=["POST"])
@login_required
def ultah_add():
    """Tambah data ultah baru"""
    nama = request.form.get("nama", "").strip()
    nim = request.form.get("nim", "").strip()
    tanggal = request.form.get("tanggal")
    bulan = request.form.get("bulan")
    tahun_lahir = request.form.get("tahun_lahir")
    prodi = request.form.get("prodi", "").strip()
    simpan_foto = request.form.get("simpan_foto") == "on"

    if not nama or not tanggal or not bulan:
        flash("Nama, Tanggal, dan Bulan wajib diisi!", "error")
        return redirect(url_for("manajemen_ultah"))

    if nim and ultah_model.check_nim_exists(nim):
        flash(f"NIM {nim} sudah terdaftar!", "error")
        return redirect(url_for("manajemen_ultah"))

    foto_base64 = None
    if simpan_foto and nim:
        foto_bytes = fetch_photo_from_sicyca("mahasiswa", nim)
        if foto_bytes:
            foto_base64 = base64.b64encode(foto_bytes).decode("utf-8")

    data = {
        "nama": nama,
        "nim": nim if nim else None,
        "tanggal": int(tanggal),
        "bulan": int(bulan),
        "tahun_lahir": int(tahun_lahir) if tahun_lahir else None,
        "foto_base64": foto_base64,
        "prodi": prodi if prodi else get_prodi_from_nim(nim),  # Auto-detect dari NIM
        "is_from_sicyca": 0,
    }

    if ultah_model.create(data):
        flash("Data ultah berhasil ditambahkan!", "success")
    else:
        flash("Gagal menambahkan data ultah!", "error")

    return redirect(url_for("manajemen_ultah"))


@app.route("/manajemenUltah/edit/<int:record_id>", methods=["POST"])
@login_required
def ultah_edit(record_id):
    """Update data ultah"""
    nama = request.form.get("nama", "").strip()
    nim = request.form.get("nim", "").strip()
    tanggal = request.form.get("tanggal")
    bulan = request.form.get("bulan")
    tahun_lahir = request.form.get("tahun_lahir")
    prodi = request.form.get("prodi", "").strip()

    if not nama or not tanggal or not bulan:
        flash("Nama, Tanggal, dan Bulan wajib diisi!", "error")
        return redirect(url_for("manajemen_ultah"))

    if nim and ultah_model.check_nim_exists(nim, exclude_id=record_id):
        flash(f"NIM {nim} sudah terdaftar!", "error")
        return redirect(url_for("manajemen_ultah"))

    existing = ultah_model.get_by_id(record_id)
    foto_base64 = existing.get("foto_base64") if existing else None

    data = {
        "nama": nama,
        "nim": nim if nim else None,
        "tanggal": int(tanggal),
        "bulan": int(bulan),
        "tahun_lahir": int(tahun_lahir) if tahun_lahir else None,
        "foto_base64": foto_base64,
        "prodi": prodi if prodi else get_prodi_from_nim(nim),  # Auto-detect dari NIM
    }

    if ultah_model.update(record_id, data):
        flash("Data ultah berhasil diupdate!", "success")
    else:
        flash("Gagal mengupdate data ultah!", "error")

    return redirect(url_for("manajemen_ultah"))


@app.route("/manajemenUltah/delete/<int:record_id>", methods=["POST"])
@login_required
def ultah_delete(record_id):
    """Hapus data ultah"""
    # Cek opsi delete Google Calendar
    if request.form.get("delete_gcal") == "on":
        record = ultah_model.get_by_id(record_id)
        if record and record.get("google_calendar_event_id"):
            user_id = g.user.get("sub")
            google_cal_service.delete_event(user_id, record["google_calendar_event_id"])

    if ultah_model.delete(record_id):
        flash("Data ultah berhasil dihapus!", "success")
    else:
        flash("Gagal menghapus data ultah!", "error")

    return redirect(url_for("manajemen_ultah"))


@app.route("/manajemenUltah/save-sicyca", methods=["POST"])
@login_required
def ultah_save_sicyca():
    """Simpan data dari list SICYCA ke database"""
    nama = request.form.get("nama", "").strip()
    prodi = request.form.get("prodi", "").strip()
    tanggal_lahir = request.form.get("tanggal_lahir", "").strip()
    nim = request.form.get("nim", "").strip()
    simpan_foto = request.form.get("simpan_foto") == "on"

    if not nama:
        flash("Data tidak valid!", "error")
        return redirect(url_for("manajemen_ultah"))

    tanggal, bulan, tahun = parse_tanggal_sicyca(tanggal_lahir)

    if not tanggal or not bulan:
        flash("Format tanggal tidak valid!", "error")
        return redirect(url_for("manajemen_ultah"))

    if nim and ultah_model.check_nim_exists(nim):
        flash(f"NIM {nim} sudah terdaftar!", "error")
        return redirect(url_for("manajemen_ultah"))

    foto_base64 = None
    if simpan_foto and nim:
        foto_bytes = fetch_photo_from_sicyca("mahasiswa", nim)
        if foto_bytes:
            foto_base64 = base64.b64encode(foto_bytes).decode("utf-8")

    data = {
        "nama": nama,
        "nim": nim if nim else None,
        "tanggal": tanggal,
        "bulan": bulan,
        "tahun_lahir": tahun,
        "foto_base64": foto_base64,
        "prodi": prodi if prodi else get_prodi_from_nim(nim),  # Auto-detect dari NIM
        "is_from_sicyca": 1,
    }

    if ultah_model.create(data):
        flash(f"Data ultah {nama} berhasil disimpan!", "success")
    else:
        flash("Gagal menyimpan data ultah!", "error")

    return redirect(url_for("manajemen_ultah"))


@app.route("/manajemenUltah/lookup", methods=["GET"])
@login_required
def ultah_lookup_nim():
    """Lookup data mahasiswa by NIM"""
    nim = request.args.get("nim")
    if not nim:
        return Response(
            json.dumps({"success": False, "message": "NIM required"}),
            mimetype="application/json",
        )

    try:
        # Search via scraper
        user_id = g.user.get("sub")
        df = search_mahasiswa(nim, user_id=user_id)

        if not df.empty:
            # Ambil baris pertama
            item = df.iloc[0]
            # Convert keys to lowercase for safety
            data = {k.lower(): v for k, v in item.items()}

            result = {
                "success": True,
                "nama": data.get("nama", ""),
                "prodi": data.get("prodi", ""),
                "nim": data.get("nim", nim),
            }
            return Response(json.dumps(result), mimetype="application/json")
        else:
            return Response(
                json.dumps({"success": False, "message": "Data tidak ditemukan"}),
                mimetype="application/json",
            )
    except Exception as e:
        logging.error(f"Error lookup NIM: {e}")
        return Response(
            json.dumps({"success": False, "message": str(e)}),
            mimetype="application/json",
        )


@app.route("/manajemenUltah/sync-calendar/<int:record_id>", methods=["POST"])
@login_required
def ultah_sync_calendar(record_id):
    """Sync single data ultah ke Google Calendar"""
    user_id = g.user.get("sub")

    # Cek apakah sudah connect Google
    token_info = google_cal_service.get_token_by_user(user_id)
    if not token_info:
        flash("Silakan hubungkan akun Google terlebih dahulu.", "warning")
        return redirect(url_for("manajemen_ultah"))

    # 1. Parse Parameters from Unified Modal
    color_id = request.form.get("color_id")

    # Attendees (JSON list or comma separated)
    attendees_raw = request.form.get("attendees", "")
    attendees = []
    try:
        attendees = json.loads(attendees_raw)
        if not isinstance(attendees, list):
            attendees = []
    except:
        attendees = [e.strip() for e in attendees_raw.split(",") if e.strip()]

    # Reminders (JSON list of {method, minutes})
    reminders_raw = request.form.get("reminders_json", "")
    reminders = []
    if reminders_raw:
        try:
            reminders = json.loads(reminders_raw)
        except:
            logging.warn("Failed parsing reminders JSON")

    # Ambil record
    record = ultah_model.get_by_id(record_id)
    if not record:
        flash("Data tidak ditemukan!", "error")
        return redirect(url_for("manajemen_ultah"))

    # Hapus event lama jika ada
    if record.get("google_calendar_event_id"):
        google_cal_service.delete_event(user_id, record.get("google_calendar_event_id"))

    # Buat Event Baru dengan Overrides
    event_id = google_cal_service.create_birthday_event(
        user_id,
        record,
        overrides={"colorId": color_id, "attendees": attendees, "reminders": reminders},
    )

    if event_id:
        ultah_model.update_google_event_id(record_id, event_id)
        flash("Berhasil sync ke Google Calendar!", "success")
    else:
        flash("Gagal sync ke Google Calendar.", "error")

    return redirect(url_for("manajemen_ultah"))


# ========== GOOGLE OAUTH ROUTES ==========

# ========== UNIFIED GOOGLE OAUTH (Calendar + Drive) ==========


@app.route("/google/auth")
@login_required
def google_auth():
    """Unified Google OAuth — redirect ke Google login"""
    next_url = request.args.get("next", url_for("account_page"))
    session["google_oauth_next"] = next_url
    auth_url, state = google_cal_service.get_auth_url()
    session["google_oauth_state"] = state
    return redirect(auth_url)


@app.route("/google/callback")
@login_required
def google_callback():
    """Unified Google OAuth callback"""
    user_id = g.user.get("sub")

    try:
        credentials, user_data = google_cal_service.handle_callback(request.url)
        google_cal_service.save_token(user_id, credentials, user_data)
        flash(
            f"Berhasil terhubung dengan akun Google: {user_data.get('name')}", "success"
        )
    except Exception as e:
        logging.error(f"[GoogleOAuth] Error: {e}")
        flash("Gagal menghubungkan akun Google.", "error")

    next_url = session.pop("google_oauth_next", url_for("account_page"))
    return redirect(next_url)


@app.route("/google/disconnect", methods=["POST"])
@login_required
def google_disconnect():
    """Unified disconnect Google account"""
    user_id = g.user.get("sub")
    next_url = request.form.get("next", url_for("account_page"))

    if google_cal_service.delete_token(user_id):
        # Reset kolom google_calendar_event_id di database (clean DB)
        try:
            conn = get_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE ultah_records SET google_calendar_event_id = NULL"
                )
                conn.commit()
                cursor.close()
                conn.close()
            flash(
                "Akun Google berhasil diputuskan dan status sync di-reset.", "success"
            )
        except Exception as e:
            logging.error(f"Error reseting sync status: {e}")
            flash("Akun Google putus, tapi gagal reset status DB.", "warning")
    else:
        flash("Gagal memutuskan akun Google.", "error")

    return redirect(next_url)


@app.route("/manajemenUltah/settings", methods=["POST"])
@login_required
def ultah_save_settings():
    """Simpan pengaturan sinkronisasi Google Calendar"""
    user_id = g.user.get("sub")

    color_id = request.form.get("color_id")
    raw_attendees = request.form.get("default_attendees", "").strip()

    # Parse attendees to list
    if raw_attendees.startswith("["):
        try:
            default_attendees = json.loads(raw_attendees)
        except:
            default_attendees = []
    else:
        default_attendees = [x.strip() for x in raw_attendees.split(",") if x.strip()]

    settings = {"color_id": color_id, "default_attendees": default_attendees}

    if google_cal_service.save_settings(user_id, settings):
        flash("Pengaturan berhasil disimpan!", "success")
    else:
        flash("Gagal menyimpan pengaturan.", "error")

    return redirect(url_for("manajemen_ultah"))


# ========== BULK OPERATIONS ==========


@app.route("/manajemenUltah/bulk-delete", methods=["POST"])
@login_required
def ultah_bulk_delete():
    """Bulk delete records"""
    user_id = g.user.get("sub")
    record_ids = request.form.getlist("record_ids")

    if not record_ids:
        flash("Tidak ada data yang dipilih!", "warning")
        return redirect(url_for("manajemen_ultah"))

    deleted_count = 0
    for record_id in record_ids:
        try:
            record = ultah_model.get_by_id(int(record_id))
            if record:
                # Hapus event dari Google Calendar jika ada
                if record.get("google_calendar_event_id"):
                    google_cal_service.delete_event(
                        user_id, record["google_calendar_event_id"]
                    )

                if ultah_model.delete(int(record_id)):
                    deleted_count += 1
        except Exception as e:
            logging.error(f"[BulkDelete] Error: {e}")

    flash(f"{deleted_count} data berhasil dihapus!", "success")
    return redirect(url_for("manajemen_ultah"))


@app.route("/manajemenUltah/bulk-sync", methods=["POST"])
@login_required
def ultah_bulk_sync():
    """Bulk sync records ke Google Calendar"""
    user_id = g.user.get("sub")

    # Cek apakah sudah connect Google
    token_info = google_cal_service.get_token_by_user(user_id)
    if not token_info:
        flash("Silakan hubungkan akun Google terlebih dahulu.", "warning")
        return redirect(url_for("manajemen_ultah"))

    record_ids = request.form.getlist("record_ids")
    attendees_raw = request.form.get("attendees", "")
    attendees = []
    try:
        # Coba parse sebagai JSON (karena frontend kirim format ["a@b.com"])
        attendees = json.loads(attendees_raw)
        if not isinstance(attendees, list):
            attendees = []
    except:
        # Fallback jika bukan JSON (comma separated)
        attendees = [e.strip() for e in attendees_raw.split(",") if e.strip()]
    # --------------------------------------------------
    if not record_ids:
        flash("Tidak ada data yang dipilih!", "warning")
        return redirect(url_for("manajemen_ultah"))

    synced_count = 0
    for record_id in record_ids:
        try:
            record = ultah_model.get_by_id(int(record_id))
            if record:
                # Hapus event lama jika ada
                if record.get("google_calendar_event_id"):
                    google_cal_service.delete_event(
                        user_id, record["google_calendar_event_id"]
                    )

                # Create event baru
                event_id = google_cal_service.create_birthday_event(
                    user_id, record, overrides={"attendees": attendees}
                )

                if event_id:
                    conn = get_connection()
                    if conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE ultah_records SET google_calendar_event_id = %s WHERE id = %s",
                            (event_id, int(record_id)),
                        )
                        conn.commit()
                        cursor.close()
                        conn.close()
                    synced_count += 1
        except Exception as e:
            logging.error(f"[BulkSync] Error: {e}")

    flash(f"{synced_count} data berhasil disinkronkan ke Google Calendar!", "success")
    return redirect(url_for("manajemen_ultah"))


# SSE Endpoint untuk streaming count
@app.route("/stream/recap-count")
def stream_recap_count():
    """Server-Sent Events endpoint untuk streaming jumlah orang yang terecap"""
    room_code = request.args.get("room")

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
                uuid_count = sum(1 for item in current_room_data if item.get("uuid"))
                nim_count = sum(1 for item in current_room_data if item.get("nim"))

                payload = {"total": current_count, "uuid": uuid_count, "nim": nim_count}

                # Check for NEW data (increment only)
                if current_count > last_count:
                    if current_count > 0:
                        latest_item = current_room_data[-1]
                        payload["new_scan"] = {
                            "type": "NIM" if latest_item.get("nim") else "UUID",
                            "value": latest_item.get("nim") or latest_item.get("uuid"),
                        }

                # Check for DUPLICATE warning (Room Specific)
                # SSKM_LAST_DUPLICATE structure: { 'room_code': { 'type': ..., 'value': ..., 'timestamp': ... } }
                if room_code in SSKM_LAST_DUPLICATE:
                    last_evt = SSKM_LAST_DUPLICATE[room_code]
                    if last_evt.get("timestamp", 0) > last_duplicate_time:
                        payload["duplicate"] = {
                            "type": last_evt["type"],
                            "value": last_evt["value"],
                        }
                        last_duplicate_time = last_evt["timestamp"]

                last_count = current_count

                # Format SSE: data: <json>\n\n
                yield f"data: {json.dumps(payload)}\n\n"
                time.sleep(1)  # Update every 1 second for faster feedback
            except GeneratorExit:
                break

    return Response(generate(), mimetype="text/event-stream")


# Route untuk halaman recap
@app.route("/recap-hadir")
def recap_hadir():
    """Halaman real-time counter kehadiran SSKM"""
    return render_template("recapOrangSSKM.html")


@app.route("/testhtml")
def test_html():
    """Halaman real-time counter kehadiran SSKM"""
    return render_template("test.html")


# ======================================================
# ROUTES LOGBOOK MAGANG
# ======================================================


# 1. Halaman Awal: List Semua Logbook
@app.route("/logbook", methods=["GET"])
@login_required  # Proteksi route
@check_permission("logbook_magang")
def logbook_list():
    current_user = g.user.get("sub")  # Ambil User ID dari JWT

    # Ambil logbook KHUSUS punya user ini aja
    logbooks = get_logbooks_by_user(current_user)
    return render_template("logBook/list.html", logbooks=logbooks)


# 2. Halaman Setup Logbook Baru
@app.route("/logbook/setup", methods=["GET", "POST"])
@login_required
def logbook_setup():
    current_user = g.user.get("sub")

    if request.method == "POST":
        # Handle file TTD (opsional)
        ttd_path = None
        ttd_file = request.files.get("ttd_file")
        if ttd_file and ttd_file.filename:
            nim = request.form.get("nim", "unknown")
            ttd_path = save_signature_file(ttd_file, nim)

        # Simpan logbook baru dengan menyertakan ID usernya
        new_id = create_logbook(current_user, request.form, ttd_path=ttd_path)
        return redirect(url_for("logbook_detail", logbook_id=new_id))
    # Cek Google account status (unified via DB token)
    # Trigger refresh logic via build_drive_service if needed
    try:
        google_cal_service.build_drive_service(current_user)
    except:
        pass

    google_user = google_cal_service.get_token_by_user(current_user)
    is_google_connected = google_user is not None

    # Prepare API Params for Google Picker
    google_api_key = os.getenv("GOOGLE_API_KEY", "")
    google_app_id = os.getenv("GOOGLE_APP_ID", "")
    active_token = (
        google_user["token"]["token"]
        if google_user and "token" in google_user and "token" in google_user["token"]
        else ""
    )

    return render_template(
        "logBook/setup.html",
        logbook=None,
        is_google_connected=is_google_connected,
        google_user=google_user,
        google_api_key=google_api_key,
        google_app_id=google_app_id,
        active_token=active_token,
    )


# 3. Edit Setup Logbook (INI YANG TADI DUPLIKAT DAN SALAH ROUTE)
@app.route("/logbook/edit/<string:logbook_id>", methods=["GET", "POST"])
@login_required
@check_permission("logbook_magang")
def logbook_edit(logbook_id):
    current_user = g.user.get("sub")

    real_logbook_id = get_logbook_id_by_uuid(logbook_id)
    if not real_logbook_id:
        return "Logbook tidak ditemukan", 404

    # Fetch logbook dulu (untuk GET maupun POST)
    logbook = get_logbook_by_id_and_user(real_logbook_id, current_user)
    if not logbook:
        return "Akses Ditolak! Ini bukan logbook Anda.", 403

    if request.method == "POST":
        # Handle file TTD (opsional)
        ttd_path = None
        remove_ttd = request.form.get("remove_ttd") == "1"
        ttd_file = request.files.get("ttd_file")
        if ttd_file and ttd_file.filename:
            nim = request.form.get("nim", logbook["nim"] if logbook else "unknown")
            ttd_path = save_signature_file(ttd_file, nim)

        update_logbook(
            logbook["id"],
            request.form,
            current_user,
            ttd_path=ttd_path,
            remove_ttd=remove_ttd,
        )
        return redirect(url_for("logbook_detail", logbook_id=logbook_id))
    # Google account status (unified via DB token)
    # Trigger refresh logic via build_drive_service if needed
    try:
        google_cal_service.build_drive_service(current_user)
    except:
        pass

    google_user = google_cal_service.get_token_by_user(current_user)
    is_google_connected = google_user is not None

    # Prepare API Params for Google Picker
    google_api_key = os.getenv("GOOGLE_API_KEY", "")
    google_app_id = os.getenv("GOOGLE_APP_ID", "")
    active_token = (
        google_user["token"]["token"]
        if google_user and "token" in google_user and "token" in google_user["token"]
        else ""
    )

    return render_template(
        "logBook/setup.html",
        logbook=logbook,
        is_google_connected=is_google_connected,
        google_user=google_user,
        google_api_key=google_api_key,
        google_app_id=google_app_id,
        active_token=active_token,
    )


# 4. Hapus Setup Logbook
@app.route("/logbook/delete/<string:logbook_id>", methods=["POST"])
@login_required
@check_permission("logbook_magang")
def logbook_delete(logbook_id):
    current_user = g.user.get("sub")
    real_logbook_id = get_logbook_id_by_uuid(logbook_id)
    if not real_logbook_id:
        return redirect(url_for("logbook_list"))

    logbook = get_logbook_by_id_and_user(real_logbook_id, current_user)
    if logbook:
        delete_logbook(logbook["id"], current_user)
    return redirect(url_for("logbook_list"))


# 5. HALAMAN UTAMA LOGBOOK (Isi Kegiatan Harian)
@app.route("/logbook/<string:logbook_id>", methods=["GET"])
@login_required
@check_permission("logbook_magang")
def logbook_detail(logbook_id):
    current_user = g.user.get("sub")

    real_logbook_id = get_logbook_id_by_uuid(logbook_id)
    if not real_logbook_id:
        return "Logbook tidak ditemukan", 404

    # Cek apakah logbook ini beneran milik dia
    logbook = get_logbook_by_id_and_user(real_logbook_id, current_user)
    if not logbook:
        return "Akses Ditolak! Ini bukan logbook Anda.", 403

    entries = get_entries_by_logbook(logbook["id"])
    # Google account status
    google_user = google_cal_service.get_token_by_user(current_user)
    # Signature data per bulan
    signatures = get_signatures_by_logbook(logbook["id"])
    # Resume data per bulan
    resumes = get_resumes_by_logbook(logbook["id"])
    now = datetime.now()
    return render_template(
        "logBook/detail.html",
        logbook=logbook,
        entries=entries,
        google_user=google_user,
        signatures=signatures,
        resumes=resumes,
        current_year=now.year,
        current_month=now.month,
        current_day=now.day,
    )


# 6. Tambah Kegiatan Harian
@app.route("/logbook/<string:logbook_id>/add_entry", methods=["POST"])
@login_required
@check_permission("logbook_magang")
def logbook_add_entry(logbook_id):
    current_user = g.user.get("sub")

    real_logbook_id = get_logbook_id_by_uuid(logbook_id)
    if not real_logbook_id:
        return "Logbook tidak ditemukan", 404

    # Keamanan: Pastikan logbook milik dia sebelum nambah kegiatan
    logbook = get_logbook_by_id_and_user(real_logbook_id, current_user)
    if logbook:
        add_entry(
            logbook["id"],
            request.form.get("tanggal"),
            request.form.get("aktivitas"),
            request.form.get("deskripsi"),
            request.files.getlist("gambar"),
        )

    return redirect(url_for("logbook_detail", logbook_id=logbook_id))


# 6.5 Edit Kegiatan Harian
@app.route(
    "/logbook/<string:logbook_id>/edit_entry/<string:entry_id>", methods=["GET", "POST"]
)
@login_required
@check_permission("logbook_magang")
def logbook_edit_entry(logbook_id, entry_id):
    current_user = g.user.get("sub")

    real_logbook_id = get_logbook_id_by_uuid(logbook_id)
    real_entry_id = get_entry_id_by_uuid(entry_id)

    if not real_logbook_id or not real_entry_id:
        return "Data tidak ditemukan", 404

    # Keamanan: Pastikan logbook ini beneran milik dia sebelum ngedit
    logbook = get_logbook_by_id_and_user(real_logbook_id, current_user)
    if not logbook:
        return "Akses Ditolak!", 403

    # Jika cuma ngebuka halaman (GET)
    entry = get_entry_by_id(real_entry_id)
    if not entry:
        return "Data kegiatan tidak ditemukan", 404

    # Jika disubmit (POST)
    if request.method == "POST":
        update_entry(entry["id"], logbook["id"], request.form, request.files)
        return redirect(url_for("logbook_detail", logbook_id=logbook_id))

    return render_template("logBook/edit_entry.html", logbook=logbook, entry=entry)


# 7. Hapus Kegiatan Harian
@app.route(
    "/logbook/<string:logbook_id>/delete_entry/<string:entry_id>", methods=["POST"]
)
@login_required
@check_permission("logbook_magang")
def logbook_delete_entry(logbook_id, entry_id):
    current_user = g.user.get("sub")

    # KONVERSI UUID DARI URL JADI ID ASLI
    real_logbook_id = get_logbook_id_by_uuid(logbook_id)
    real_entry_id = get_entry_id_by_uuid(entry_id)

    # Kalau data ga ketemu, balikin ke detail
    if not real_logbook_id or not real_entry_id:
        return redirect(url_for("logbook_detail", logbook_id=logbook_id))

    # Keamanan: Pastikan logbook milik dia sebelum hapus kegiatan (Pakai Real ID)
    logbook = get_logbook_by_id_and_user(real_logbook_id, current_user)
    entry = get_entry_by_id(real_entry_id)

    if logbook and entry:
        delete_entry(entry["id"], logbook["id"])

    return redirect(url_for("logbook_detail", logbook_id=logbook_id))


# 8. Download Word
@app.route("/logbook/<string:logbook_id>/download", methods=["GET"])
@login_required
@check_permission("logbook_magang")
@limiter.limit("30 per minute")  # Limit khusus download, override global limit
def logbook_download(logbook_id):
    current_user = g.user.get("sub")

    real_logbook_id = get_logbook_id_by_uuid(logbook_id)
    if not real_logbook_id:
        return "Logbook tidak ditemukan", 404

    logbook = get_logbook_by_id_and_user(real_logbook_id, current_user)
    if logbook:
        return generate_word(logbook["id"], current_user)
    return "Akses Ditolak", 403


# 8b. Download PDF Per Bulan
@app.route("/logbook/<string:logbook_id>/download-pdf/<path:bulan>", methods=["GET"])
@login_required
@limiter.limit("30 per minute")  # Limit khusus download, override global limit
def logbook_download_pdf(logbook_id, bulan):
    current_user = g.user.get("sub")

    real_logbook_id = get_logbook_id_by_uuid(logbook_id)
    if not real_logbook_id:
        return "Logbook tidak ditemukan", 404

    logbook = get_logbook_by_id_and_user(real_logbook_id, current_user)
    if not logbook:
        return "Akses Ditolak", 403

    result = generate_pdf_monthly(logbook["id"], current_user, bulan)
    if result is None:
        return "Gagal generate PDF. Pastikan reportlab sudah terinstall.", 500
    return result


# 9. Approve Tanda Tangan (JSON API)
@app.route("/logbook/<string:logbook_id>/approve-signature", methods=["POST"])
@login_required
def logbook_approve_signature(logbook_id):
    current_user = g.user.get("sub")
    data = request.get_json()
    bulan = data.get("bulan")

    if not bulan:
        return jsonify({"success": False, "error": "Bulan tidak diberikan"}), 400

    real_logbook_id = get_logbook_id_by_uuid(logbook_id)
    if not real_logbook_id:
        return jsonify({"success": False, "error": "Logbook tidak ditemukan"}), 404

    logbook = get_logbook_by_id_and_user(real_logbook_id, current_user)
    if not logbook:
        return jsonify({"success": False, "error": "Akses ditolak"}), 403

    if approve_signature(logbook["id"], bulan, current_user):
        return jsonify({"success": True, "message": f"TTD bulan {bulan} disetujui!"})
    return jsonify({"success": False, "error": "Gagal menyetujui TTD"}), 400


# 10. Revoke Tanda Tangan (JSON API)
@app.route("/logbook/<string:logbook_id>/revoke-signature", methods=["POST"])
@login_required
def logbook_revoke_signature(logbook_id):
    current_user = g.user.get("sub")
    data = request.get_json()
    bulan = data.get("bulan")

    if not bulan:
        return jsonify({"success": False, "error": "Bulan tidak diberikan"}), 400

    real_logbook_id = get_logbook_id_by_uuid(logbook_id)
    if not real_logbook_id:
        return jsonify({"success": False, "error": "Logbook tidak ditemukan"}), 404

    logbook = get_logbook_by_id_and_user(real_logbook_id, current_user)
    if not logbook:
        return jsonify({"success": False, "error": "Akses ditolak"}), 403

    if revoke_signature(logbook["id"], bulan, current_user):
        return jsonify({"success": True, "message": f"TTD bulan {bulan} dicabut!"})
    return jsonify({"success": False, "error": "Gagal mencabut TTD"}), 400


# 11. Save Resume Kegiatan (JSON API)
@app.route("/logbook/<string:logbook_id>/save-resume", methods=["POST"])
@login_required
def logbook_save_resume(logbook_id):
    current_user = g.user.get("sub")
    data = request.get_json()
    bulan = data.get("bulan")
    content = data.get("content", "")

    if not bulan:
        return jsonify({"success": False, "error": "Bulan tidak diberikan"}), 400

    real_logbook_id = get_logbook_id_by_uuid(logbook_id)
    if not real_logbook_id:
        return jsonify({"success": False, "error": "Logbook tidak ditemukan"}), 404

    logbook = get_logbook_by_id_and_user(real_logbook_id, current_user)
    if not logbook:
        return jsonify({"success": False, "error": "Akses ditolak"}), 403

    if save_resume(logbook["id"], bulan, content, current_user):
        return jsonify(
            {"success": True, "message": f"Resume bulan {bulan} berhasil disimpan!"}
        )
    return jsonify({"success": False, "error": "Gagal menyimpan resume"}), 400


# 12. Delete Resume Kegiatan (JSON API)
@app.route("/logbook/<string:logbook_id>/delete-resume", methods=["POST"])
@login_required
def logbook_delete_resume(logbook_id):
    current_user = g.user.get("sub")
    data = request.get_json()
    bulan = data.get("bulan")

    if not bulan:
        return jsonify({"success": False, "error": "Bulan tidak diberikan"}), 400

    real_logbook_id = get_logbook_id_by_uuid(logbook_id)
    if not real_logbook_id:
        return jsonify({"success": False, "error": "Logbook tidak ditemukan"}), 404

    logbook = get_logbook_by_id_and_user(real_logbook_id, current_user)
    if not logbook:
        return jsonify({"success": False, "error": "Akses ditolak"}), 403

    if delete_resume(logbook["id"], bulan, current_user):
        return jsonify(
            {"success": True, "message": f"Resume bulan {bulan} berhasil dikosongkan!"}
        )
    return jsonify({"success": False, "error": "Gagal menghapus resume"}), 400


# ==========================================
# API KHUSUS GAMBAR LOGBOOK (JSON RESPONSES)
# ==========================================


@app.route("/logbook/image/delete/<int:image_id>", methods=["DELETE"])
@login_required
def delete_logbook_image_route(image_id):
    user_id = g.user.get("sub")

    if delete_single_image(image_id, user_id):
        return jsonify({"status": "success"}), 200
    else:
        return jsonify({"status": "error"}), 400


@app.route("/logbook/image/update/<int:image_id>", methods=["POST"])
@login_required
def update_logbook_image_route(image_id):
    data = request.get_json()
    user_id = g.user.get("sub")  # Ambil ID user dari JWT token

    success = update_image_metadata(
        image_id, user_id, data.get("nama"), data.get("deskripsi")
    )

    if success:
        return jsonify({"status": "success", "message": "Metadata updated"}), 200
    else:
        return jsonify(
            {"status": "error", "message": "Update failed or Unauthorized"}
        ), 403


@app.route("/logbook/image/replace/<int:image_id>", methods=["POST"])
@login_required
def replace_logbook_image_route(image_id):
    """Replace file fisik gambar yang sudah ada (untuk crop/rotate/resize)"""
    user_id = g.user.get("sub")

    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No file uploaded"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"status": "error", "message": "Empty filename"}), 400

    success, result = replace_image_file(image_id, user_id, file)

    if success:
        new_url = url_for("static", filename=f"uploads/logbook/{result}")
        return jsonify(
            {"status": "success", "new_url": new_url, "new_path": result}
        ), 200
    else:
        return jsonify({"status": "error", "message": result}), 403


# ======================================================
# LOGBOOK VIEWS (PUBLIC — Auth via NIM + UUID)
# ======================================================


@app.route("/logbook-views", methods=["GET"])
def logbook_views_login():
    """Halaman login logbook viewer (public, tanpa login)"""
    return render_template("logBook/views_login.html")


@app.route("/logbook-views", methods=["POST"])
def logbook_views_auth():
    """Verifikasi NIM + UUID lalu tampilkan logbook read-only"""
    nim = request.form.get("nim", "").strip()
    password = request.form.get("password", "").strip()

    if not nim or not password:
        return render_template(
            "logBook/views_login.html", error="NIM dan Kode Akses wajib diisi."
        )

    logbook = get_logbook_by_nim_and_uuid(nim, password)

    if not logbook:
        return render_template(
            "logBook/views_login.html",
            error="NIM atau Kode Akses salah. Silakan coba lagi.",
        )

    entries = get_entries_by_logbook(logbook["id"])
    signatures = get_signatures_by_logbook(logbook["id"])
    resumes = get_resumes_by_logbook(logbook["id"])

    now = datetime.now()
    return render_template(
        "logBook/logbook_view.html",
        logbook=logbook,
        entries=entries,
        signatures=signatures,
        resumes=resumes,
        current_year=now.year,
        current_month=now.month,
        current_day=now.day,
    )


# ======================================================
# API GOOGLE DRIVE (pake unified DB token)
# ======================================================


@app.route("/api/google/drive/docs")
@login_required
def google_drive_list_docs():
    """List Google Docs dari Google Drive user"""
    user_id = g.user.get("sub")

    service = google_cal_service.build_drive_service(user_id)
    if not service:
        return jsonify({"error": "Google account belum terhubung"}), 401

    try:
        results = (
            service.files()
            .list(
                q="mimeType='application/vnd.google-apps.document'",
                fields="files(id, name)",
                pageSize=50,
                orderBy="modifiedTime desc",
            )
            .execute()
        )

        return jsonify({"files": results.get("files", [])})
    except Exception as e:
        logging.error(f"[GoogleDrive] Error listing docs: {e}")
        return jsonify({"error": "Gagal mengambil daftar dokumen"}), 500


# ======================================================
# ROUTES SUPER ADMIN (1 HTML DENGAN TABS)
# ======================================================


@app.route("/admin/panel")
@login_required
def admin_panel():
    if g.user.get("role_id") != 1:
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
    perm_map = {(p["role_id"], p["tool_id"]): p["is_allowed"] for p in perms}
    cursor.close()
    conn.close()

    return render_template(
        "admin_panel.html",
        users=users,
        all_roles=all_roles,
        roles=roles_for_tools,
        tools=tools,
        perm_map=perm_map,
    )


@app.route("/admin/add-user", methods=["POST"])
@login_required
def add_user():
    if g.user.get("role_id") != 1:
        return "Akses Ditolak!", 403

    username = request.form.get("username")
    email = request.form.get("email")
    password = request.form.get("password")
    role_id = request.form.get("role_id")

    if not username or not password or not role_id:
        flash("Username, Password, dan Role wajib diisi!", "error")
        return redirect(url_for("admin_panel"))

    # Lempar datanya ke UserController
    success, message = create_user(username, email, password, role_id)

    if success:
        flash(message, "success")
    else:
        flash(message, "error")

    return redirect(url_for("admin_panel"))


@app.route("/admin/update-role", methods=["POST"])
@login_required
def update_role():
    if g.user.get("role_id") != 1:
        return "Ditolak", 403

    user_id = request.form.get("user_id")
    role_id = request.form.get("role_id")

    # Lempar datanya ke UserController
    if change_user_role(user_id, role_id):
        flash("Role user berhasil diubah!", "success")
    else:
        flash("Gagal mengubah role user.", "error")

    return redirect(url_for("admin_panel"))


@app.route("/admin/toggle-tool", methods=["POST"])
@login_required
def toggle_tool():
    # Proteksi extra: Pastikan cuma Super Admin yang bisa ubah
    if g.user.get("role_id") != 1:
        return jsonify({"error": "Akses Ditolak!"}), 403

    data = request.json
    role_id = data.get("role_id")
    tool_id = data.get("tool_id")
    is_allowed = data.get("is_allowed")

    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Pake fitur sakti MySQL UPSERT (Insert if not exist, Update if exist)
        query = """
            INSERT INTO role_permissions (role_id, tool_id, is_allowed)
            VALUES (%s, %s, %s)
            ON CONFLICT (role_id, tool_id) DO UPDATE SET is_allowed = EXCLUDED.is_allowed
        """
        cursor.execute(query, (role_id, tool_id, is_allowed))
        conn.commit()
        return jsonify({"success": True, "message": "Izin berhasil diubah!"})
    except Exception as e:
        logging.error(f"[Toggle Tool] Error: {e}")
        return jsonify({"success": False, "message": "Terjadi kesalahan server."}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/admin/update-user", methods=["POST"])
@login_required
def admin_update_user():
    if g.user.get("role_id") != 1:
        return "Ditolak", 403

    user_id = request.form.get("user_id")
    username = request.form.get("username")
    email = request.form.get("email")

    success, message = update_user_detail(user_id, username, email)
    flash(message, "success" if success else "error")
    return redirect(url_for("admin_panel"))


@app.route("/admin/delete-user/<int:user_id>")
@login_required
def admin_delete_user(user_id):
    if g.user.get("role_id") != 1:
        return "Ditolak", 403

    # Keamanan: Jangan biarkan admin menghapus dirinya sendiri
    if str(user_id) == str(g.user.get("sub")):
        flash("Anda tidak bisa menghapus akun Anda sendiri!", "error")
        return redirect(url_for("admin_panel"))

    if delete_user(user_id):
        flash("User berhasil dihapus!", "success")
    else:
        flash("Gagal menghapus user.", "error")
    return redirect(url_for("admin_panel"))


@app.route("/admin/reset-password/<int:user_id>")
@login_required
def admin_reset_password(user_id):
    if g.user.get("role_id") != 1:
        return "Ditolak", 403

    if reset_user_password(user_id):
        flash(f'Password berhasil direset ke "mhs123"!', "success")
    else:
        flash("Gagal mereset password.", "error")

    return redirect(url_for("admin_panel"))


@app.route("/webauthn/register/options", methods=["POST"])
@login_required
def webauthn_register_options():
    user_id = str(g.user.get("sub"))

    # Ambil username dari token (kalau ada)
    username = g.user.get("username")

    # JIKA KOSONG (karena JWT lama nggak nyimpen username), ambil dari Database
    if not username:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
        user_db = cursor.fetchone()
        cursor.close()
        conn.close()

        # Pastikan username gak boleh kosong
        username = user_db["username"] if user_db else f"user_{user_id}"

    # Bikin opsi tantangan buat alat fingerprint
    options = generate_registration_options(
        rp_id=RP_ID,
        rp_name=RP_NAME,
        user_id=user_id.encode("utf-8"),
        user_name=username,  # Sekarang dijamin terisi!
        user_display_name=username,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            user_verification=UserVerificationRequirement.REQUIRED,
            resident_key=ResidentKeyRequirement.REQUIRED,
        ),
    )

    # Simpan 'challenge' ke session sementara buat diverifikasi nanti
    session["webauthn_registration_challenge"] = options.challenge

    # Kirim format JSON ke frontend
    return Response(options_to_json(options), mimetype="application/json")


@app.route("/webauthn/register/verify", methods=["POST"])
@login_required
def webauthn_register_verify():
    challenge = session.get("webauthn_registration_challenge")
    if not challenge:
        return jsonify({"success": False, "msg": "Challenge tidak ditemukan"}), 400

    credential_data = request.json  # Data dari frontend

    try:
        verification = verify_registration_response(
            credential=credential_data,
            expected_challenge=challenge,
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
        )

        # FIX UTAMA: Ambil credential ID langsung dari string yang dikirim Browser!
        # Jangan pakai base64.b64encode punya Python biar string-nya 100% cocok pas login.
        cred_id_b64 = credential_data.get("id")

        # Public key tetap di-encode karena cuma dibaca sama Python
        pub_key_b64 = base64.b64encode(verification.credential_public_key).decode(
            "utf-8"
        )

        # Simpan ke Database
        user_id = g.user.get("sub")
        save_credential(user_id, cred_id_b64, pub_key_b64, verification.sign_count, "")

        session.pop("webauthn_registration_challenge", None)

        return jsonify({"success": True, "msg": "Sidik jari berhasil didaftarkan!"})

    except Exception as e:
        print(f"WebAuthn Verify Error: {e}")
        return jsonify({"success": False, "msg": str(e)}), 400


@app.route("/webauthn/login/options", methods=["POST"])
def webauthn_login_options():
    options = generate_authentication_options(
        rp_id=RP_ID, user_verification=UserVerificationRequirement.REQUIRED
    )
    session["webauthn_auth_challenge"] = options.challenge

    # FIX: Pake Response biar browser tau ini tipe datanya JSON!
    return Response(options_to_json(options), mimetype="application/json")


@app.route("/webauthn/login/verify", methods=["POST"])
@limiter.limit("5 per minute")  # Batasi cuma 5x percobaan per menit per IP
def webauthn_login_verify():
    challenge = session.get("webauthn_auth_challenge")
    if not challenge:
        return jsonify({"success": False, "msg": "Challenge tidak ditemukan"}), 400

    credential_data = request.json
    cred_id_b64 = credential_data.get("id")
    remember_me = credential_data.get("remember_me", False)

    user_data = get_user_by_credential(cred_id_b64)
    if not user_data:
        return jsonify({"success": False, "msg": "Perangkat ini belum terdaftar."}), 404

    try:
        verification = verify_authentication_response(
            credential=credential_data,
            expected_challenge=challenge,
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
            credential_public_key=base64.b64decode(user_data["public_key"]),
            credential_current_sign_count=user_data["sign_count"],
        )
        update_sign_count(cred_id_b64, verification.new_sign_count)

        # Proses pembuatan token JWT
        access_token = generate_access_token(user_data["id"], user_data["role_id"])
        refresh_token = generate_refresh_token()

        # Tentukan lifetime berdasarkan remember_me
        if remember_me:
            access_max_age = 3600 * 24 * 30  # 30 hari
            refresh_max_age = 3600 * 24 * 365  # 365 hari
            refresh_expires = timedelta(days=365)
        else:
            access_max_age = 1800  # 30 menit
            refresh_max_age = 3600 * 24 * 30  # 30 hari
            refresh_expires = timedelta(days=30)

        expires_at = datetime.now(SCHEDULER_TZ) + refresh_expires

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO user_sessions (user_id, refresh_token, expires_at, ip_address, user_agent, revoked, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """,
            (
                user_data["id"],
                refresh_token,
                expires_at,
                request.remote_addr,
                request.headers.get("User-Agent"),
                0,
            ),
        )
        conn.commit()
        cursor.close()
        conn.close()

        session["user_id"] = user_data["id"]
        session.modified = True

        resp = jsonify(
            {
                "success": True,
                "msg": "Login Biometrik berhasil!",
                "redirect": url_for("index"),
            }
        )

        if isinstance(access_token, bytes):
            access_token = access_token.decode("utf-8")

        resp.set_cookie(
            "access_token",
            access_token,
            httponly=True,
            secure=False,
            samesite="Lax",
            max_age=access_max_age,
        )
        resp.set_cookie(
            "refresh_token",
            refresh_token,
            httponly=True,
            secure=False,
            samesite="Lax",
            max_age=refresh_max_age,
        )

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
# Menonaktifkan auto-scrape semua jadwal jam 5 pagi agar server tidak berat
# scheduler.add_job(run_scraper_and_save, "cron", hour=5, minute=0, id="scrape-05")
# scheduler.start()
boot_scrape_if_needed()

logging.info(
    "\nScheduler jadwal telah dimulai. Akan berjalan setiap hari jam 05:00 pagi."
)
logging.info("Aplikasi web Flask siap di http://0.0.0.0:5000\n")
