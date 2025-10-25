# app.py

import os
import re
from datetime import datetime
import pandas as pd
from flask import Flask, send_from_directory, request, render_template, redirect, url_for, Response, jsonify, json, session, abort
from apscheduler.schedulers.background import BackgroundScheduler
from concurrent.futures import ThreadPoolExecutor
import logging
import pytz
import json
import base64  # Untuk encode image ke base64
from logging.handlers import RotatingFileHandler
import secrets
import time
from cachetools import TTLCache  # Install: pip install cachetools
from api.api import api_bp, init_api
from models.auth_api import auth_bp
from flask_cors import CORS

# Impor SEMUA fungsi scraper
from scrapper_requests import scrape_data
from middleware.auth_quard import login_required




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
# Inisialisasi scheduler SEKALI saat modul di-import
SCHEDULER_TZ = pytz.timezone("Asia/Jakarta")
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

executor = ThreadPoolExecutor(max_workers=3)
JSON_FILE = 'jadwal.json'
ICS_FILE = 'jadwal_kegiatan.ics'
JADWAL_STATUS = {"status": "ready", "message": "Siap."}
app.secret_key = os.getenv("SECRET_KEY")  # Untuk session

logging.info(f"Secret Key untuk session diatur: {app.secret_key is not None}")

app.config.update(
    SESSION_COOKIE_NAME='session',
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='None',  # ganti ke 'None' kalau frontend beda origin
    SESSION_COOKIE_SECURE=False,    # True kalau HTTPS
    PERMANENT_SESSION_LIFETIME=3600 * 24 * 7,
    SESSION_PERMANENT=True
)






month_translation = { 'Januari': 'January', 'Februari': 'February', 'Maret': 'March', 'April': 'April', 'Mei': 'May', 'Juni': 'June', 'Juli': 'July', 'Agustus': 'August', 'September': 'September', 'Oktober': 'October', 'November': 'November', 'Desember': 'December' }
majorID = { "39010": "D3 Sistem Informasi", "41010": "S1 Sistem Informasi", "41011": "S1 Sistem Informasi", "41020": "S1 Teknik Komputer", "42010": "S1 Desain Komunikasi Visual", "42020": "S1 Desain Produk", "43010": "S1 Manajemen", "43020": "S1 Akuntansi", "51016": "D4 Produksi Film dan Televisi" }

# Fungsi validasi (sudah ada, tidak ubah)
def _valid_role(x):
    return x in ("mahasiswa", "staff")



init_api(photo_cache, majorID, executor, JADWAL_STATUS, log_file, _valid_role)
app.register_blueprint(api_bp, url_prefix='/api')

# Jalankan scraper dan simpan hasilnya ke file JSON
def run_scraper_and_save():
    global JADWAL_STATUS
    JADWAL_STATUS = {"status": "loading", "message": f"Proses scraping dimulai: {datetime.now().strftime('%A, %d %B %Y %H:%M:%S')}"}
    logging.info("=== MENJALANKAN SCRAPING JADWAL ===")
    
    df = scrape_data()

    if not df.empty:
        # Format waktu lengkap untuk disimpan di metadata
        waktu_scraping = datetime.now().strftime("%A, %d %B %Y %H:%M:%S")

        # Simpan ke file JSON utama
        data_records = df.to_dict(orient='records')

        # Tambahkan metadata di akhir file JSON
        json_output = {
            "metadata": {
                "last_scraped": waktu_scraping,
                "total_jadwal": len(data_records)
            },
            "data": data_records
        }

        # Simpan file
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(json_output, f, indent=4, ensure_ascii=False)

        JADWAL_STATUS = {"status": "ready", "message": f"Data diperbarui: {waktu_scraping}"}
        logging.info(f"Jadwal berhasil disimpan ({len(data_records)} entri) pada {waktu_scraping}.")
    else:
        waktu_error = datetime.now().strftime("%A, %d %B %Y %H:%M:%S")
        JADWAL_STATUS = {"status": "error", "message": f"Scraping gagal pada: {waktu_error}"}
        logging.warning("Scraping jadwal tidak menghasilkan data.")

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
        
@app.before_request
def debug_cookies():
    print("[DEBUG COOKIE] Cookie header:", request.headers.get('Cookie'))


# Main route

@app.route('/login', methods=['GET'])
def login_page():
    return render_template('login.html')

@app.route('/logout')
def logout_page():
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/')
@login_required
def index():
    print("[INDEX DEBUG] Session keys:", list(session.keys()))
    try:
        # Baca JSON dengan struktur baru
        with open(JSON_FILE, encoding='utf-8') as f:
            df_json = json.load(f)

        metadata = df_json.get("metadata", {})
        df = pd.DataFrame(df_json.get("data", []))

        # Tampilkan tabel jadwal
        html_table = df.to_html(
            classes='table-auto w-full text-sm text-gray-300 border-collapse border border-gray-700',
            justify='left',
            index=False
        )

        # Ambil waktu terakhir scraping dari metadata
        last_scraped = metadata.get("last_scraped", "Belum pernah di-scrape")

        # Sisipkan info di atas tabel
        info_html = f"""
        <div class='flex justify-between items-center mb-4'>
            <h2 class='text-lg font-semibold text-white'>Daftar Jadwal Kuliah</h2>
            <p class='text-sm text-gray-400'>Terakhir diperbarui: {last_scraped}</p>
        </div>
        """

        return render_template('show_schedule.html', tabel=info_html + html_table)

    except (FileNotFoundError, ValueError): 
        msg = "<h3 class='text-gray-400'>JADWAL BELUM TERSEDIA.</h3><p>Jalankan scraper terlebih dahulu atau tunggu jadwal otomatis berikutnya.</p>"
        return render_template('show_schedule.html', tabel=msg)

    except Exception as e:
        return f"<pre>Error: {str(e)}</pre>", 500





@app.route('/refresh-jadwal')
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
def pencarian_komunitas_route():
    return render_template('pencarian_mhsstaff.html')


@app.route('/cari-mahasiswa')
def cari_mahasiswa_redirect():
    return redirect(url_for('pencarian_komunitas_route'))

@app.route('/log-program')
def log_program():
    log_content = "Membaca log..."
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            lines.reverse()
            log_content = "".join(lines)
    return render_template('log_page.html', log_content=log_content)


# Api




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
    
app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=True)
