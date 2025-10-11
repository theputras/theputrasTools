# app.py

import os
import re
from datetime import datetime
import pandas as pd
from flask import Flask, send_from_directory, request, render_template_string, redirect, url_for, Response, jsonify, json   
from apscheduler.schedulers.background import BackgroundScheduler
from concurrent.futures import ThreadPoolExecutor
import logging
from logging.handlers import RotatingFileHandler

# Impor SEMUA fungsi scraper
from scrapper_requests import scrape_data, search_mahasiswa, search_staff, get_session_status

app = Flask(__name__)

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


executor = ThreadPoolExecutor(max_workers=3)
JSON_FILE = 'jadwal.json'
ICS_FILE = 'jadwal_kegiatan.ics'
JADWAL_STATUS = {"status": "ready", "message": "Siap."}

month_translation = { 'Januari': 'January', 'Februari': 'February', 'Maret': 'March', 'April': 'April', 'Mei': 'May', 'Juni': 'June', 'Juli': 'July', 'Agustus': 'August', 'September': 'September', 'Oktober': 'October', 'November': 'November', 'Desember': 'December' }
majorID = { "39010": "D3 Sistem Informasi", "41010": "S1 Sistem Informasi", "41011": "S1 Sistem Informasi", "41020": "S1 Teknik Komputer", "42010": "S1 Desain Komunikasi Visual", "42020": "S1 Desain Produk", "43010": "S1 Manajemen", "43020": "S1 Akuntansi", "51016": "D4 Produksi Film dan Televisi" }

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
    # ... (sisa fungsi tidak berubah) ...
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
    logging.info(f"File {ics_path} berhasil diperbarui.")

@app.route('/')
def index():
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

        return INDEX_JADWAL.replace("<!-- TEMPAT_TABEL -->", info_html + html_table)

    except (FileNotFoundError, ValueError): 
        msg = "<h3 class='text-gray-400'>JADWAL BELUM TERSEDIA.</h3><p>Jalankan scraper terlebih dahulu atau tunggu jadwal otomatis berikutnya.</p>"
        return INDEX_JADWAL.replace("<!-- TEMPAT_TABEL -->", msg)

    except Exception as e:
        return f"<pre>Error: {str(e)}</pre>", 500



INDEX_JADWAL = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Status Jadwal & Sicyca</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
</head>
<body class="bg-gray-900 text-gray-300 font-sans">
    <div class="container mx-auto p-6">
        
        <!-- HEADER STATUS -->
        <div class="bg-gray-800 rounded-lg shadow-md p-6 flex flex-wrap items-center gap-4 justify-start"
             x-data="{ jadwalStatus: 'loading', jadwalMsg: '', sicycaStatus: 'loading', sicycaMsg: '', lastUpdate: '' }"
             x-init="
                fetch('/api/jadwal-status')
                    .then(res => res.json())
                    .then(data => { 
                        jadwalStatus = data.status; 
                        jadwalMsg = data.message; 
                        lastUpdate = data.message; 
                    });
                fetch('/api/status')
                    .then(res => res.json())
                    .then(data => { sicycaStatus = data.status; sicycaMsg = data.message; });
                setInterval(() => {
                    fetch('/api/jadwal-status')
                        .then(res => res.json())
                        .then(data => { 
                            jadwalStatus = data.status; 
                            jadwalMsg = data.message; 
                            lastUpdate = data.message; 
                        });
                }, 5000);
             ">
             
            <a href="/pencarian-komunitas" class="text-blue-400 hover:text-blue-300 font-semibold underline">
                &raquo; Pencarian Komunitas
            </a>

            <a href="/refresh-jadwal" class="bg-green-600 hover:bg-green-700 text-white font-semibold px-4 py-2 rounded-md text-sm">
                &#x21bb; Refresh Jadwal
            </a>

            <a href="/log-program" class="text-gray-400 hover:text-gray-300 underline text-sm">
                Lihat Log
            </a>

            <!-- STATUS JADWAL -->
            <template x-if="jadwalStatus === 'loading'">
                <span class="flex items-center text-xs font-semibold bg-yellow-500/20 text-yellow-400 px-3 py-1 rounded-full">
                    <svg class="animate-spin h-3 w-3 mr-2 text-yellow-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                    </svg>
                    Scraping...
                </span>
            </template>

            <template x-if="jadwalStatus === 'ready'">
                <span class="flex items-center text-xs font-semibold bg-green-500/20 text-green-400 px-3 py-1 rounded-full" :title="jadwalMsg">
                    <span class="h-2 w-2 mr-2 rounded-full bg-green-500"></span>
                    Jadwal Ready
                </span>
            </template>

            <template x-if="jadwalStatus === 'error'">
                <span class="flex items-center text-xs font-semibold bg-red-500/20 text-red-400 px-3 py-1 rounded-full" :title="jadwalMsg">
                    <span class="h-2 w-2 mr-2 rounded-full bg-red-500 animate-pulse"></span>
                    Scraping Error
                </span>
            </template>

            <!-- STATUS SICYCA -->
            <template x-if="sicycaStatus === 'loading'">
                <span class="flex items-center text-xs font-semibold bg-yellow-500/20 text-yellow-400 px-3 py-1 rounded-full">
                    <svg class="animate-spin h-3 w-3 mr-2 text-yellow-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                    </svg>
                    Mengecek koneksi...
                </span>
            </template>

            <template x-if="sicycaStatus === 'ready'">
                <span class="flex items-center text-xs font-semibold bg-green-500/20 text-green-400 px-3 py-1 rounded-full" :title="sicycaMsg">
                    <span class="h-2 w-2 mr-2 rounded-full bg-green-500"></span>
                    Sicyca Ready
                </span>
            </template>

            <template x-if="sicycaStatus === 'error'">
                <span class="flex items-center text-xs font-semibold bg-red-500/20 text-red-400 px-3 py-1 rounded-full" :title="sicycaMsg">
                    <span class="h-2 w-2 mr-2 rounded-full bg-red-500 animate-pulse"></span>
                    Connection Error
                </span>
            </template>
        </div>

        <!-- AREA TABEL -->
        <div class="bg-gray-800 rounded-lg shadow-md p-6 mt-6 overflow-x-auto" x-data="{ lastUpdate: '' }">

            <!-- TEMPAT_TABEL -->
        </div>
    </div>
</body>
</html>
"""

@app.route('/refresh-jadwal')
def refresh_jadwal_route():
    # Jalankan scraper di background agar tidak memblokir
    executor.submit(run_scraper_and_save)
    # Langsung redirect, JavaScript akan menangani update UI
    return redirect(url_for('index'))

@app.route('/kalendar')
def kalendar_ics():
    # ... (sisa fungsi tidak berubah) ...
    try:
        create_ics_from_json(JSON_FILE, ICS_FILE)
        return send_from_directory(os.path.abspath('.'), path=ICS_FILE, as_attachment=True, download_name='jadwal_kuliah.ics')
    except (FileNotFoundError, ValueError):
        return "<h3>Data jadwal belum tersedia.</h3>", 404
    except Exception as e:
        return f"<pre>Error: {str(e)}</pre>", 500

# (Template dan route pencarian komunitas tidak berubah)
COMMUNITY_SEARCH_TEMPLATE = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pencarian Komunitas Sicyca</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
</head>
<body class="bg-gray-900 text-gray-300 font-sans">
    <div class="container mx-auto p-4 md:p-8">
        <div class="bg-gray-800 rounded-lg shadow-md p-6" 
             x-data="{ isLoading: false, results: null, query: '', sicycaStatus: 'loading', statusMessage: '' }"
             x-init="
                fetch('/api/status')
                .then(res => res.json())
                .then(data => {
                    sicycaStatus = data.status;
                    statusMessage = data.message;
                })
             ">
            <div class="flex justify-between items-start mb-2">
                <h1 class="text-2xl font-bold text-white">Pencarian Komunitas</h1>
                
                <template x-if="sicycaStatus === 'loading'">
                    <span class="flex items-center text-xs font-semibold bg-yellow-500/20 text-yellow-400 px-3 py-1 rounded-full">
                        <svg class="animate-spin h-3 w-3 mr-2 text-yellow-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                        Mengecek koneksi...
                    </span>
                </template>
                <template x-if="sicycaStatus === 'ready'">
                    <span class="flex items-center text-xs font-semibold bg-green-500/20 text-green-400 px-3 py-1 rounded-full" :title="statusMessage">
                        <span class="h-2 w-2 mr-2 rounded-full bg-green-500"></span>
                        Sicyca Ready
                    </span>
                </template>
                <template x-if="sicycaStatus === 'error'">
                    <span class="flex items-center text-xs font-semibold bg-red-500/20 text-red-400 px-3 py-1 rounded-full" :title="statusMessage">
                        <span class="h-2 w-2 mr-2 rounded-full bg-red-500 animate-pulse"></span>
                        Connection Error
                    </span>
                </template>
            </div>
            
            <p class="text-gray-400 mb-6">Masukkan NIM, NIK, atau Nama untuk mencari data di Sicyca.</p>
            <a href="/" class="text-blue-400 hover:text-blue-300 mb-4 inline-block">&laquo; Kembali ke Jadwal Kuliah</a>
            
            <form @submit.prevent="
                isLoading = true; results = null;
                fetch('/api/search', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query: query }) })
                .then(response => response.json()).then(data => { results = data; isLoading = false; });
            " class="mb-8">
                <div class="flex flex-col sm:flex-row gap-2">
                    <input type="text" x-model="query" name="query" placeholder="Masukkan pencarian Anda..."
                           class="flex-grow w-full px-4 py-2 bg-gray-700 border border-gray-600 text-white rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" required>
                    <button type="submit"
                            class="bg-blue-600 text-white font-semibold px-6 py-2 rounded-md hover:bg-blue-700 disabled:bg-blue-400 disabled:cursor-wait"
                            :disabled="isLoading">
                        <span x-show="!isLoading">Cari</span>
                        <span x-show="isLoading">Mencari...</span>
                    </button>
                </div>
            </form>

            <div x-show="isLoading" class="text-center p-4"><p class="text-gray-400">Loading...</p></div>
            <div x-show="results !== null && !isLoading">
                <h2 class="text-xl font-bold text-white mb-4 border-b border-gray-700 pb-2">Hasil Pencarian</h2>
                <div class="border border-gray-700 rounded-md" x-html="results"></div>
            </div>
        </div>
    </div>
</body>
</html>
"""
LOG_PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Log Program</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 text-gray-300 font-sans">
    <div class="container mx-auto p-4 md:p-8">
        <h1 class="text-2xl font-bold text-white mb-4">Log Program</h1>
        <div class="flex gap-4 mb-4">
            <a href="/" class="text-blue-400 hover:text-blue-300">&laquo; Kembali ke Halaman Utama</a>
            <button onclick="window.location.reload();" class="px-4 py-1 bg-gray-700 text-white rounded-md text-sm hover:bg-gray-600">Refresh Manual</button>
        </div>
        <pre id="log-content" class="bg-black text-white p-4 rounded-md text-xs whitespace-pre-wrap break-words w-full overflow-x-auto h-[70vh]">{{ log_content }}</pre>
    </div>
    <script>
        const logContainer = document.getElementById('log-content');
        let isScrolledToTop = true; // Awalnya, kita anggap pengguna di atas

        // Cek posisi scroll setiap kali pengguna scroll
        logContainer.addEventListener('scroll', () => {
            isScrolledToTop = logContainer.scrollTop === 0;
        });

        async function fetchLog() {
            try {
                const response = await fetch('/api/log');
                if (!response.ok) return;
                const newLogContent = await response.text();

                if (logContainer.textContent !== newLogContent) {
                    logContainer.textContent = newLogContent;
                    // Jika pengguna sedang di paling atas, pertahankan di atas
                    if (isScrolledToTop) {
                        logContainer.scrollTop = 0;
                    }
                }
            } catch (error) {
                console.error('Error fetching log:', error);
            }
        }

        // Jalankan fungsi fetchLog setiap 2.5 detik
        setInterval(fetchLog, 2500);
    </script>
</body>
</html>
"""
@app.route('/pencarian-komunitas', methods=['GET'])
def pencarian_komunitas_route():
    return render_template_string(COMMUNITY_SEARCH_TEMPLATE)


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
    return render_template_string(LOG_PAGE_TEMPLATE, log_content=log_content)


# Api

# Mengecek sicyca 
@app.route('/api/status')
def api_status():
    if get_session_status():
        return jsonify({"status": "ready", "message": "Koneksi Sicyca aman."})
    else:
        return jsonify({"status": "error", "message": "Koneksi Sicyca gagal. Cookie mungkin tidak valid. Coba lakukan pencarian untuk login ulang."})

# Untuk mencari mahasiswa atau staff
@app.route('/api/search', methods=['POST'])
def api_search():
    data = request.get_json()
    query = data.get('query', '').strip()
    if not query:
        return jsonify({"html": "<p class='text-gray-400 p-4'>Query tidak boleh kosong.</p>"})

    future_mahasiswa = executor.submit(search_mahasiswa, query)
    future_staff = executor.submit(search_staff, query)
    df_mahasiswa = future_mahasiswa.result()
    df_staff = future_staff.result()

    combined_results = []
    if not df_mahasiswa.empty:
        for _, row in df_mahasiswa.iterrows():
            nim = row.get('NIM', '')
            prodi_name = majorID.get(nim[2:7], 'Prodi Tidak Dikenal') if nim and len(nim) >= 7 else 'Prodi Tidak Dikenal'
            combined_results.append({ 'Tipe': 'Mahasiswa', 'Nama': row.get('Nama'), 'ID': nim, 'Status': f"{row.get('Status')}", 'Prodi' : prodi_name, 'Detail': row.get('Dosen Wali') })
    
    if not df_staff.empty:
        for _, row in df_staff.iterrows():
            combined_results.append({'Tipe': 'Staff/Dosen', 'Nama': row.get('Nama'), 'ID': row.get('NIK'), 'Bagian': row.get('Bagian'), 'Detail': row.get('Email')})
    
    # --- Backend sekarang membuat string HTML ---
    html_output = ""
    if combined_results:
        for item in combined_results:
            detail_html = ""
            if item['Tipe'] == 'Mahasiswa':
                detail_html = f"""
                    <dt class="font-medium text-gray-400">NIM</dt><dd class="col-span-2 text-white">{item.get('ID', '')}</dd>
                    <dt class="font-medium text-gray-400">Prodi</dt><dd class="col-span-2 text-white">{item.get('Prodi', '')}</dd>
                    <dt class="font-medium text-gray-400">Status</dt><dd class="col-span-2 text-white">{item.get('Status', '')}</dd>
                    <dt class="font-medium text-gray-400">Dosen Wali</dt><dd class="col-span-2 text-white">{item.get('Detail', '')}</dd>
                """
            else:
                detail_html = f"""
                    <dt class="font-medium text-gray-400">NIK</dt><dd class="col-span-2 text-white">{item.get('ID', '')}</dd>
                    <dt class="font-medium text-gray-400">Bagian</dt><dd class="col-span-2 text-white">{item.get('Bagian', '')}</dd>
                    <dt class="font-medium text-gray-400">Email</dt><dd class="col-span-2 text-white">{item.get('Detail', '')}</dd>
                """
            html_output += f"""
            <div x-data="{{ 'isOpen': false }}" class="border-b border-gray-700 last:border-b-0">
                <button @click="isOpen = !isOpen" class="w-full text-left p-4 hover:bg-gray-700 focus:outline-none">
                    <div class="flex justify-between items-center">
                        <div>
                            <span class="font-semibold text-white">{item.get('Nama', '')}</span>
                            <span class="text-xs text-gray-300 ml-2 px-2 py-1 bg-gray-600 rounded-full">{item.get('Tipe', '')}</span>
                        </div>
                        <svg class="w-5 h-5 transform transition-transform duration-300" :class="{{'{{'}} 'rotate-180': isOpen {{'}}'}}" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path></svg>
                    </div>
                </button>
                <div x-show="isOpen" x-transition class="p-4 bg-gray-900 border-t border-gray-700 text-sm">
                    <dl class="grid grid-cols-3 gap-2 text-sm">{detail_html}</dl>
                </div>
            </div>
            """
    else:
        html_output = "<p class='text-gray-400 p-4'>Tidak ada data yang ditemukan.</p>"
    
    return jsonify({"html": html_output})

# Untuk melihat log terus menerus
@app.route('/api/log')
def api_log():
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            lines.reverse()
            return Response("".join(lines), mimetype='text/plain')
    return Response("Log file tidak ditemukan.", mimetype='text/plain', status=404)

# Mengecek apakah jadwal ready atau error

@app.route('/api/jadwal-status')
def api_jadwal_status():
    return jsonify(JADWAL_STATUS)
    
if __name__ == "__main__":
    should_run_scraper = False
    if not os.path.exists(JSON_FILE):
        logging.info(f"File {JSON_FILE} tidak ditemukan. Menjalankan scraper jadwal awal...")
        should_run_scraper = True
    else:
        try:
            # Coba baca file untuk memvalidasi formatnya
            pd.read_json(JSON_FILE)
            logging.info(f"File {JSON_FILE} ditemukan dan formatnya valid.")
        except ValueError: # pandas akan error jika JSON rusak/format salah
            logging.warning(f"File {JSON_FILE} rusak atau format salah. Menjalankan scraper untuk membuat file baru...")
            should_run_scraper = True

    if should_run_scraper:
        run_scraper_and_save()

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(run_scraper_and_save, 'cron', hour=5, minute=0)
    scheduler.start()
    
    logging.info("\nScheduler jadwal telah dimulai. Akan berjalan setiap hari jam 05:00 pagi.")
    logging.info("Aplikasi web Flask siap di http://0.0.0.0:5000\n")
    
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=True)