# app.py

import os
from datetime import datetime
import pandas as pd
import re
from flask import Flask, send_from_directory, request, render_template_string
from apscheduler.schedulers.background import BackgroundScheduler

# Impor fungsi scraper dari file sebelah
from scrapper_requests import scrape_data,search_mahasiswa

app = Flask(__name__)

JSON_FILE = 'jadwal.json'   
ICS_FILE = 'jadwal_kegiatan.ics'
HOST='127.0.0.1'
PORT=5000
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
SEARCH_PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pencarian Mahasiswa Sicyca</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 font-sans">
    <div class="container mx-auto p-4 md:p-8">
        <div class="bg-white rounded-lg shadow-md p-6">
            <h1 class="text-2xl font-bold text-gray-800 mb-2">Pencarian Mahasiswa</h1>
            <p class="text-gray-600 mb-6">Masukkan NIM atau Nama untuk mencari data mahasiswa di Sicyca.</p>
            <a href="/" class="text-blue-500 hover:underline mb-4 inline-block">&laquo; Kembali ke Jadwal Kuliah</a>
            
            <form method="POST" action="/cari-mahasiswa" class="mb-8">
                <div class="flex flex-col sm:flex-row gap-2">
                    <input type="text" name="query" placeholder="Masukkan NIM atau Nama..." value="{{ query }}"
                           class="flex-grow w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" required>
                    <button type="submit"
                            class="bg-blue-600 text-white font-semibold px-6 py-2 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors duration-200">
                        Cari
                    </button>
                </div>
            </form>

            {% if results is not none %}
                <h2 class="text-xl font-bold text-gray-700 mb-4 border-b pb-2">Hasil Pencarian untuk "{{ query }}"</h2>
                <div class="overflow-x-auto">
                    {{ results | safe }}
                </div>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

@app.route('/cari-mahasiswa', methods=['GET', 'POST'])
def cari_mahasiswa_route():
    if request.method == 'POST':
        query = request.form.get('query', '').strip()
        if not query:
            return render_template_string(SEARCH_PAGE_TEMPLATE, query='', results=None)
            
        print(f"Menerima permintaan pencarian untuk: '{query}'")
        df_results = search_mahasiswa(query)
        
        if not df_results.empty:
            results_table = df_results.to_html(classes='w-full text-sm text-left text-gray-700 border-collapse', index=False, justify='left')
            # Ganti style default pandas dengan Tailwind
            results_table = results_table.replace('<table border="1" class="dataframe">', '<table class="w-full text-sm text-left text-gray-700 border-collapse">')
            results_table = results_table.replace('<thead>', '<thead class="text-xs text-white uppercase bg-blue-600">')
            results_table = results_table.replace('<tr>', '<tr class="bg-white border-b hover:bg-gray-50">')
            results_table = results_table.replace('<th>', '<th scope="col" class="px-6 py-3">')
            results_table = results_table.replace('<td>', '<td class="px-6 py-4">')
        else:
            results_table = "<p class='text-gray-500 mt-4'>Tidak ada hasil yang ditemukan.</p>"
            
        return render_template_string(SEARCH_PAGE_TEMPLATE, query=query, results=results_table)
    
    # Untuk GET request, tampilkan halaman kosong
    return render_template_string(SEARCH_PAGE_TEMPLATE, query='', results=None)
if __name__ == "__main__":
    if not os.path.exists(JSON_FILE):
        print(f"File {JSON_FILE} tidak ditemukan. Menjalankan scraper untuk pertama kali...")
        run_scraper_and_save()

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(run_scraper_and_save, 'cron', hour=9, minute=46)
    # ==================================================================
    
    scheduler.start()
    
    print("\nScheduler telah dimulai. Scraping akan berjalan setiap hari pada jam 3:00 pagi.")
    print(f"Aplikasi web Flask siap di http://{HOST}:5000\n")
    
    app.run(HOST, PORT, debug=True, use_reloader=True)