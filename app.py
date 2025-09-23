from flask import Flask, send_from_directory
import pandas as pd
import os
import re
from datetime import datetime
from scrapper_requests import scrape_data

app = Flask(__name__)

# Simpan file iCalendar
def create_ics(events, filename="jadwal_kegiatan.ics"):
    ics_content = "BEGIN:VCALENDAR\nVERSION:2.0\nCALSCALE:GREGORIAN\n"
    
    for event in events:
        start_time = datetime.strptime(event['start_time'], "%d %b %Y %H:%M")
        end_time = datetime.strptime(event['end_time'], "%d %b %Y %H:%M")

        ics_content += f"BEGIN:VEVENT\n"
        ics_content += f"SUMMARY:{event['summary']}\n"
        ics_content += f"DTSTART:{start_time.strftime('%Y%m%dT%H%M%S')}\n"
        ics_content += f"DTEND:{end_time.strftime('%Y%m%dT%H%M%S')}\n"
        ics_content += f"LOCATION:{event['location']}\n"
        ics_content += f"DESCRIPTION:{event['description']}\n"
        ics_content += f"STATUS:{event['status']}\n"
        ics_content += f"END:VEVENT\n"
    
    ics_content += "END:VCALENDAR\n"
    
    with open(filename, 'w', encoding='utf-8') as file:
        file.write(ics_content)

# Route utama untuk menampilkan data
@app.route('/')
def index():
    try:
        df = scrape_data()
        print(df.head())  # Debug: Lihat data scraping yang diambil
        return df.to_html()
    except Exception as e:
        return f"<pre>{str(e)}</pre>", 500


# Route untuk mendownload file ICS
@app.route('/download_ics')
def download_ics():
    try:
        # Ambil data dari fungsi scrape_data()
        events = scrape_data()

        # Buat file ICS
        create_ics(events, "jadwal_kegiatan.ics")
        
        # Dapatkan path file di direktori yang sama dengan script
        directory = os.path.abspath('.')  # Path ke direktori saat ini
        
        # Kembalikan file ICS untuk didownload
        return send_from_directory(directory=directory, filename='jadwal_kegiatan.ics', as_attachment=True)
    
    except Exception as e:
        print(f"Error creating ICS: {e}")
        return f"<pre>{str(e)}</pre>", 500

def create_ics(events, filename="jadwal_kegiatan.ics"):
    ics_content = "BEGIN:VCALENDAR\nVERSION:2.0\nCALSCALE:GREGORIAN\n"
    
    for event in events:
        # Hapus nama hari dari tanggal (contoh: 'Selasa, 23 September 2025 07:30' -> '23 September 2025 07:30')
        start_time_str = re.sub(r"^\w+, ", "", event['start_time'])  # Menghapus nama hari (misal 'Selasa, ')
        end_time_str = re.sub(r"^\w+, ", "", event['end_time'])  # Menghapus nama hari (misal 'Selasa, ')

        # Format yang sesuai dengan data: '23 September 2025 07:30'
        start_time = datetime.strptime(start_time_str, "%d %B %Y %H:%M")  # Menggunakan '%B' untuk nama bulan penuh
        end_time = datetime.strptime(end_time_str, "%d %B %Y %H:%M")  # Menggunakan '%B' untuk nama bulan penuh

        ics_content += f"BEGIN:VEVENT\n"
        ics_content += f"SUMMARY:{event['summary']}\n"
        ics_content += f"DTSTART:{start_time.strftime('%Y%m%dT%H%M%S')}\n"
        ics_content += f"DTEND:{end_time.strftime('%Y%m%dT%H%M%S')}\n"
        ics_content += f"LOCATION:{event['location']}\n"
        ics_content += f"DESCRIPTION:{event['description']}\n"
        ics_content += f"STATUS:{event['status']}\n"
        ics_content += f"END:VEVENT\n"
    
    ics_content += "END:VCALENDAR\n"
    
    # Simpan file .ics
    with open(filename, 'w', encoding='utf-8') as file:
        file.write(ics_content)
    print(f"File {filename} telah dibuat.")


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)

