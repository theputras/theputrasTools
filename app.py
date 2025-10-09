# app.py

import os
from datetime import datetime
import pandas as pd
import re
from flask import Flask, send_from_directory
from apscheduler.schedulers.background import BackgroundScheduler

# Impor fungsi scraper dari file sebelah
from scrapper_requests import scrape_data

app = Flask(__name__)

JSON_FILE = 'jadwal.json'
ICS_FILE = 'jadwal_kegiatan.ics'

# ==================================================================
# === PERBAIKAN DIMULAI DI SINI ===
# ==================================================================
# Kamus untuk menerjemahkan nama bulan
month_translation = {
    'Januari': 'January',
    'Februari': 'February',
    'Maret': 'March',
    'April': 'April',
    'Mei': 'May',
    'Juni': 'June',
    'Juli': 'July',
    'Agustus': 'August',
    'September': 'September',
    'Oktober': 'October',
    'November': 'November',
    'Desember': 'December'
}
# ==================================================================

def run_scraper_and_save():
    # Fungsi ini tidak diubah
    print(f"[{datetime.now()}] === MENJALANKAN PROSES SCRAPING ===")
    df = scrape_data()
    if not df.empty:
        df.to_json(JSON_FILE, orient='records', indent=4, force_ascii=False)
        print(f"[{datetime.now()}] Jadwal berhasil disimpan ke {JSON_FILE}. Total: {len(df)} jadwal.")
    else:
        print(f"[{datetime.now()}] Scraping tidak menghasilkan data. File CSV tidak diubah.")
    print(f"[{datetime.now()}] === PROSES SCRAPING SELESAI ===")

def create_ics_from_csv(json_path, ics_path):
    # --- PERUBAHAN 3: Membaca dari file JSON ---
    df = pd.read_json(json_path, orient='records')
    events = df.to_dict('records')
    
    ics_content = "BEGIN:VCALENDAR\nVERSION:2.0\nCALSCALE:GREGORIAN\n"
    for event in events:
        # 1. Baca kolom-kolom mentah dari file JSON
        date_str = event['Hari, Tanggal']  # contoh: "Selasa, 23 September 2025"
        time_range_str = event['Jam']       # contoh: "07:30-10:00"
        
        # 2. Memisahkan jam mulai dan selesai
        start_time_val, end_time_val = time_range_str.split('-')

        # 3. Menggabungkan tanggal dan waktu, lalu menghapus nama hari
        start_date_time_str = re.sub(r"^\w+, ", "", date_str) + ' ' + start_time_val
        end_date_time_str = re.sub(r"^\w+, ", "", date_str) + ' ' + end_time_val

        # 4. Menerjemahkan nama bulan ke Bahasa Inggris
        for idn_month, eng_month in month_translation.items():
            start_date_time_str = start_date_time_str.replace(idn_month, eng_month)
            end_date_time_str = end_date_time_str.replace(idn_month, eng_month)
        
        start_time = datetime.strptime(start_date_time_str, "%d %B %Y %H:%M")
        end_time = datetime.strptime(end_date_time_str, "%d %B %Y %H:%M")

        # 5. Memetakan kolom mentah ke field kalender
        summary = event['Nama Matakuliah']
        location = event['Ruangan']
        description = f"Keterangan: {event.get('Keterangan', '')}"
        status = event['Status Kuliah']

        ics_content += "BEGIN:VEVENT\n"
        ics_content += f"SUMMARY:{summary}\n"
        ics_content += f"DTSTART:{start_time.strftime('%Y%m%dT%H%M%S')}\n"
        ics_content += f"DTEND:{end_time.strftime('%Y%m%dT%H%M%S')}\n"
        ics_content += f"LOCATION:{location}\n"
        ics_content += f"DESCRIPTION:{description}\n"
        ics_content += f"STATUS:{status}\n"
        ics_content += "END:VEVENT\n"
        # ==================================================================
    ics_content += "END:VCALENDAR\n"
    
    with open(ics_path, 'w', encoding='utf-8') as file:
        file.write(ics_content)
    print(f"File {ics_path} berhasil diperbarui.")

# Route dan sisa kode lainnya tidak diubah
@app.route('/')
def index():
    try:
        df = pd.read_json(JSON_FILE, orient='records')
        return df.to_html(classes='table table-striped', justify='left', index=False)
    except FileNotFoundError:
        return "<h3>Jadwal belum tersedia.</h3><p>Coba refresh halaman ini beberapa saat lagi.</p>", 404
    except Exception as e:
        return f"<pre>Error: {str(e)}</pre>", 500

@app.route('/download_ics')
def download_ics():
    try:
        create_ics_from_csv(JSON_FILE, ICS_FILE)
        directory = os.path.abspath('.')
        return send_from_directory(directory=directory, path=ICS_FILE, as_attachment=True, download_name='jadwal_kuliah.ics')
    except FileNotFoundError:
        return "<h3>Data jadwal belum tersedia untuk dibuatkan kalender.</h3>", 404
    except Exception as e:
        return f"<pre>Error: {str(e)}</pre>", 500

if __name__ == "__main__":
    if not os.path.exists(JSON_FILE):
        print(f"File {JSON_FILE} tidak ditemukan. Menjalankan scraper untuk pertama kali...")
        run_scraper_and_save()

    scheduler = BackgroundScheduler(daemon=True)
    
    # ==================================================================
    # === PERUBAHAN ADA DI SINI ===
    # ==================================================================
    # Mengubah trigger dari 'interval' menjadi 'cron' untuk waktu yang spesifik
    # 'hour=0' berarti jam 00 atau 12 pagi.
    scheduler.add_job(run_scraper_and_save, 'cron', hour=3, minute=0)
    # ==================================================================
    
    scheduler.start()
    
    print("\nScheduler telah dimulai. Scraping akan berjalan setiap hari pada jam 12:00 pagi.")
    print("Aplikasi web Flask siap di http://0.0.0.0:5000\n")
    
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)