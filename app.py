# app.py

import os
import re
from datetime import datetime
import pandas as pd
from flask import Flask, send_from_directory, request, render_template_string, redirect, url_for
from apscheduler.schedulers.background import BackgroundScheduler
from concurrent.futures import ThreadPoolExecutor

# Impor SEMUA fungsi scraper
from scrapper_requests import scrape_data, search_mahasiswa, search_staff

app = Flask(__name__)

# Membuat executor untuk menjalankan tugas di background
executor = ThreadPoolExecutor(max_workers=3)

JSON_FILE = 'jadwal.json'
ICS_FILE = 'jadwal_kegiatan.ics'

month_translation = { 'Januari': 'January', 'Februari': 'February', 'Maret': 'March', 'April': 'April', 'Mei': 'May', 'Juni': 'June', 'Juli': 'July', 'Agustus': 'August', 'September': 'September', 'Oktober': 'October', 'November': 'November', 'Desember': 'December' }

def run_scraper_and_save():
    print(f"[{datetime.now()}] === MENJALANKAN SCRAPING JADWAL ===")
    df = scrape_data()
    if not df.empty:
        df.to_json(JSON_FILE, orient='records', indent=4, force_ascii=False)
        print(f"[{datetime.now()}] Jadwal berhasil disimpan ke {JSON_FILE}. Total: {len(df)} jadwal.")
    else:
        print(f"[{datetime.now()}] Scraping jadwal tidak menghasilkan data.")
    print(f"[{datetime.now()}] === SCRAPING JADWAL SELESAI ===")

def create_ics_from_json(json_path, ics_path):
    df = pd.read_json(json_path, orient='records')
    events = df.to_dict('records')
    ics_content = "BEGIN:VCALENDAR\nVERSION:2.0\nCALSCALE:GREGORIAN\n"
    for event in events:
        date_str, time_range_str = event['Hari, Tanggal'], event['Jam']
        start_time_val, end_time_val = time_range_str.split('-')
        start_date_time_str = re.sub(r"^\w+, ", "", date_str) + ' ' + start_time_val
        end_date_time_str = re.sub(r"^\w+, ", "", date_str) + ' ' + end_time_val
        for idn, eng in month_translation.items():
            start_date_time_str = start_date_time_str.replace(idn, eng)
            end_date_time_str = end_date_time_str.replace(idn, eng)
        start_time = datetime.strptime(start_date_time_str, "%d %B %Y %H:%M")
        end_time = datetime.strptime(end_date_time_str, "%d %B %Y %H:%M")
        ics_content += (f"BEGIN:VEVENT\nSUMMARY:{event['Nama Matakuliah']}\n"
                        f"DTSTART:{start_time.strftime('%Y%m%dT%H%M%S')}\n"
                        f"DTEND:{end_time.strftime('%Y%m%dT%H%M%S')}\n"
                        f"LOCATION:{event['Ruangan']}\n"
                        f"DESCRIPTION:Keterangan: {event.get('Keterangan', '')}\n"
                        f"STATUS:{event['Status Kuliah']}\nEND:VEVENT\n")
    ics_content += "END:VCALENDAR\n"
    with open(ics_path, 'w', encoding='utf-8') as f: f.write(ics_content)
    print(f"File {ics_path} berhasil diperbarui.")

@app.route('/')
def index():
    try:
        df = pd.read_json(JSON_FILE, orient='records')
        html_table = df.to_html(classes='table table-striped', justify='left', index=False)
        header = """<div style="margin-bottom: 1rem;"><a href="/pencarian-komunitas" style="color: #3B82F6; text-decoration: underline;">&raquo; Buka Halaman Pencarian Komunitas</a></div>"""
        return header + html_table
    except (FileNotFoundError, ValueError):
        return "<h3>JADWAL BELUM TERSEDIA.</h3><p>Jalankan scraper terlebih dahulu atau tunggu jadwal otomatis berikutnya.</p>", 404
    except Exception as e:
        return f"<pre>Error: {str(e)}</pre>", 500

@app.route('/download_ics')
def download_ics():
    try:
        create_ics_from_json(JSON_FILE, ICS_FILE)
        return send_from_directory(os.path.abspath('.'), path=ICS_FILE, as_attachment=True, download_name='jadwal_kuliah.ics')
    except (FileNotFoundError, ValueError):
        return "<h3>Data jadwal belum tersedia.</h3>", 404
    except Exception as e:
        return f"<pre>Error: {str(e)}</pre>", 500

# Template HTML tidak berubah, karena perbaikan animasi ada di dalam route
COMMUNITY_SEARCH_TEMPLATE = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pencarian Komunitas Sicyca</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
</head>
<body class="bg-gray-100 font-sans">
    <div class="container mx-auto p-4 md:p-8">
        <div class="bg-white rounded-lg shadow-md p-6">
            <h1 class="text-2xl font-bold text-gray-800 mb-2">Pencarian Komunitas</h1>
            <p class="text-gray-600 mb-6">Masukkan Nama, NIM, atau NIK untuk mencari data di Sicyca.</p>
            <a href="/" class="text-blue-500 hover:underline mb-4 inline-block">&laquo; Kembali ke Jadwal Kuliah</a>
            
            <form method="POST" action="/pencarian-komunitas" class="mb-8">
                <div class="flex flex-col sm:flex-row gap-2">
                    <input type="text" name="query" placeholder="Masukkan Nama, NIM Mahasiswa, atau NIK Staff..." value="{{ query }}"
                           class="flex-grow w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" required>
                    <button type="submit"
                            class="bg-blue-600 text-white font-semibold px-6 py-2 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors duration-200">
                        Cari
                    </button>
                </div>
            </form>

            {% if results is not none %}
                <h2 class="text-xl font-bold text-gray-700 mb-4 border-b pb-2">Hasil Pencarian untuk "{{ query }}"</h2>
                <div class="overflow-x-auto hidden md:block">
                    {{ results_table | safe }}
                </div>
                <div class="border rounded-md md:hidden">
                    {{ results_list | safe }}
                </div>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

@app.route('/pencarian-komunitas', methods=['GET', 'POST'])
def pencarian_komunitas_route():
    if request.method == 'POST':
        query = request.form.get('query', '').strip()
        if not query:
            return render_template_string(COMMUNITY_SEARCH_TEMPLATE, query='', results_table=None, results_list=None)

        future_mahasiswa = executor.submit(search_mahasiswa, query)
        future_staff = executor.submit(search_staff, query)

        df_mahasiswa = future_mahasiswa.result()
        df_staff = future_staff.result()

        # --- Gabungkan hasil pencarian ---
        combined_results = []
        if not df_mahasiswa.empty:
            for _, row in df_mahasiswa.iterrows():
                combined_results.append({ 'Tipe': 'Mahasiswa', 'Nama': row.get('Nama'), 'ID': row.get('NIM'), 'Status / Bagian': row.get('Status'), 'Detail': row.get('Dosen Wali')})
        
        if not df_staff.empty:
            for _, row in df_staff.iterrows():
                combined_results.append({'Tipe': 'Staff/Dosen', 'Nama': row.get('Nama'), 'ID': row.get('NIK'), 'Status / Bagian': row.get('Bagian'), 'Detail': row.get('Email')})

        results_table_html, results_list_html = None, None
        if combined_results:
            df_combined = pd.DataFrame(combined_results)
            if 'No' in df_combined.columns:
                df_combined = df_combined.drop(columns=['No'])
            results_table_html = df_combined.to_html(classes='w-full text-sm text-left', index=False, justify='left').replace('<table border="1" class="dataframe">', '<table>').replace('<thead>', '<thead class="text-xs text-white uppercase bg-blue-600">').replace('<tr>', '<tr class="bg-white border-b hover:bg-gray-50">').replace('<th>', '<th scope="col" class="px-6 py-3">').replace('<td>', '<td class="px-6 py-4">')
            
            mobile_list = ""
            for item in combined_results:
                detail_html = ""
                if item['Tipe'] == 'Mahasiswa':
                    detail_html = f"""
                        <dt class="font-medium text-gray-500">ID (NIM)</dt><dd class="col-span-2">{item.get('ID', '')}</dd>
                        <dt class="font-medium text-gray-500">Status</dt><dd class="col-span-2">{item.get('Status / Bagian', '')}</dd>
                        <dt class="font-medium text-gray-500">Dosen Wali</dt><dd class="col-span-2">{item.get('Detail', '')}</dd>
                    """
                else:
                    detail_html = f"""
                        <dt class="font-medium text-gray-500">ID (NIK)</dt><dd class="col-span-2">{item.get('ID', '')}</dd>
                        <dt class="font-medium text-gray-500">Bagian</dt><dd class="col-span-2">{item.get('Status / Bagian', '')}</dd>
                        <dt class="font-medium text-gray-500">Email</dt><dd class="col-span-2">{item.get('Detail', '')}</dd>
                    """
                
                # ==================================================================
                # === PERBAIKAN ANIMASI DROPDOWN ADA DI SINI ===
                # ==================================================================
                mobile_list += f"""
                <div x-data="{{ 'isOpen': false }}" class="border-b last:border-b-0">
                    <button @click="isOpen = !isOpen" class="w-full text-left p-4 hover:bg-gray-50 focus:outline-none">
                        <div class="flex justify-between items-center">
                            <div>
                                <span class="font-semibold text-gray-800">{item.get('Nama', '')}</span>
                                <span class="text-xs text-gray-500 ml-2 px-2 py-1 bg-gray-200 rounded-full">{item.get('Tipe', '')}</span>
                            </div>
                            <svg class="w-5 h-5 transform transition-transform duration-300 ease-in-out text-gray-500" :class="{{ '{{' }} 'rotate-180': isOpen {{ '}}' }}" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path></svg>
                        </div>
                    </button>
                    <div x-show="isOpen" 
                         x-transition:enter="transition ease-out duration-200"
                         x-transition:enter-start="opacity-0 -translate-y-2"
                         x-transition:enter-end="opacity-100 translate-y-0"
                         x-transition:leave="transition ease-in duration-150"
                         x-transition:leave-start="opacity-100 translate-y-0"
                         x-transition:leave-end="opacity-0 -translate-y-2"
                         class="p-4 bg-gray-50 border-t text-sm">
                        <dl class="grid grid-cols-3 gap-2 text-sm">{detail_html}</dl>
                    </div>
                </div>
                """
            results_list_html = mobile_list
        else:
            no_results_msg = "<p class='text-gray-500 p-4'>Tidak ada data yang ditemukan.</p>"
            results_table_html = no_results_msg
            results_list_html = no_results_msg
            
        return render_template_string(COMMUNITY_SEARCH_TEMPLATE, query=query, results_table=results_table_html, results_list=results_list_html)
    
    # Untuk GET request
    return render_template_string(COMMUNITY_SEARCH_TEMPLATE, query='', results_table=None, results_list=None)


@app.route('/cari-mahasiswa')
def cari_mahasiswa_redirect():
    return redirect(url_for('pencarian_komunitas_route'))

if __name__ == "__main__":
    if not os.path.exists(JSON_FILE):
        print(f"File {JSON_FILE} tidak ditemukan. Menjalankan scraper jadwal...")
        run_scraper_and_save()

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(run_scraper_and_save, 'cron', hour=5, minute=0)
    scheduler.start()
    
    print("\nScheduler jadwal telah dimulai. Akan berjalan setiap hari jam 05:00 pagi.")
    print("Aplikasi web Flask siap di http://0.0.0.0:5000\n")
    
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

