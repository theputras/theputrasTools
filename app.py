# app.py

import os
from datetime import datetime
import pandas as pd
from flask import Flask, send_from_directory
from apscheduler.schedulers.background import BackgroundScheduler

# Impor fungsi scraper dari file sebelah
from scrapper_requests import scrape_data

app = Flask(__name__)

CSV_FILE = 'jadwal.csv'
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
        df.to_csv(CSV_FILE, index=False)
        print(f"[{datetime.now()}] Jadwal berhasil disimpan ke {CSV_FILE}. Total: {len(df)} jadwal.")
    else:
        print(f"[{datetime.now()}] Scraping tidak menghasilkan data. File CSV tidak diubah.")
    print(f"[{datetime.now()}] === PROSES SCRAPING SELESAI ===")

def create_ics_from_csv(csv_path, ics_path):
    df = pd.read_csv(csv_path)
    events = df.to_dict('records')
    
    ics_content = "BEGIN:VCALENDAR\nVERSION:2.0\nCALSCALE:GREGORIAN\n"
    for event in events:
        start_time_str = str(event['start_time'])
        end_time_str = str(event['end_time'])

        # ==================================================================
        # 2. Lakukan penerjemahan pada string tanggal
        for idn_month, eng_month in month_translation.items():
            start_time_str = start_time_str.replace(idn_month, eng_month)
            end_time_str = end_time_str.replace(idn_month, eng_month)
        # ==================================================================

        # Sekarang strptime akan berhasil karena nama bulan sudah dalam Bahasa Inggris
        start_time = datetime.strptime(start_time_str, "%d %B %Y %H:%M")
        end_time = datetime.strptime(end_time_str, "%d %B %Y %H:%M")

        ics_content += "BEGIN:VEVENT\n"
        ics_content += f"SUMMARY:{event['summary']}\n"
        ics_content += f"DTSTART:{start_time.strftime('%Y%m%dT%H%M%S')}\n"
        ics_content += f"DTEND:{end_time.strftime('%Y%m%dT%H%M%S')}\n"
        ics_content += f"LOCATION:{event['location']}\n"
        ics_content += f"DESCRIPTION:{event['description']}\n"
        ics_content += f"STATUS:{event['status']}\n"
        ics_content += "END:VEVENT\n"
    ics_content += "END:VCALENDAR\n"
    
    with open(ics_path, 'w', encoding='utf-8') as file:
        file.write(ics_content)
    print(f"File {ics_path} berhasil diperbarui.")

# Route dan sisa kode lainnya tidak diubah
@app.route('/')
def index():
    try:
        df = pd.read_csv(CSV_FILE)
        return df.to_html(classes='table table-striped', justify='left', index=False)
    except FileNotFoundError:
        return "<h3>Jadwal belum tersedia.</h3><p>Coba refresh halaman ini beberapa saat lagi.</p>", 404
    except Exception as e:
        return f"<pre>Error: {str(e)}</pre>", 500

@app.route('/download_ics')
def download_ics():
    try:
        create_ics_from_csv(CSV_FILE, ICS_FILE)
        directory = os.path.abspath('.')
        return send_from_directory(directory=directory, path=ICS_FILE, as_attachment=True, download_name='jadwal_kuliah.ics')
    except FileNotFoundError:
        return "<h3>Data jadwal belum tersedia untuk dibuatkan kalender.</h3>", 404
    except Exception as e:
        return f"<pre>Error: {str(e)}</pre>", 500

if __name__ == "__main__":
    if not os.path.exists(CSV_FILE):
        print("File jadwal.csv tidak ditemukan. Menjalankan scraper untuk pertama kali...")
        run_scraper_and_save()

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(run_scraper_and_save, 'interval', hours=24)
    scheduler.start()
    
    print("\nScheduler telah dimulai. Scraping akan berjalan ulang setiap 24 jam.")
    print("Aplikasi web Flask siap di http://0.0.0.0:5000\n")
    
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)