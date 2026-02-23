from flask import request, Response, jsonify, Blueprint, current_app, send_from_directory, url_for, stream_with_context, session, g, redirect
import json, yt_dlp, base64 , logging, os, uuid, urllib.parse, time, subprocess, re, random, string, html, re

from middleware.auth_quard import login_required
from yt_dlp.utils import sanitize_filename
from models.gate import GateSession, GateUser
from datetime import datetime
import google.oauth2.credentials
from googleapiclient.discovery import build
# Impor SEMUA fungsi scraper
from scrapper_requests import   search_mahasiswa, search_staff, fetch_photo_from_sicyca, fetch_data_ultah, scrape_krs, scrape_krs_detail, fetch_masa_studi, get_authenticated_session, fetch_sks, get_csrf_token_gate, fetch_profil_mhs, fetch_sskm_data
from controller.GateController import get_session_status
# from app import photo_cache, majorID, executor, JADWAL_STATUS, log_file, _valid_role
api_bp = Blueprint('api', __name__)
from controller.manajemenultahController import ultah_model # Import model ultah
from models.googleOuth import google_cal_service # Import inside function to avoid circular import if necessary
from connection import get_connection

# variabel global untuk diinject
photo_cache = None
majorID = None
executor = None
get_jadwal_status_func = None
log_file = None
_valid_role = None
SSKM_ROOMS = None  # Storage for SSKM attendance data (Dictionary: room_code -> list)


# Fungsi untuk inisialisasi variabel global
def init_api(cache, major, execu, status_getter, logfile, valid_role_func, sskm_rooms_storage=None):
    global photo_cache, majorID, executor, get_jadwal_status_func, log_file, _valid_role, SSKM_ROOMS
    photo_cache = cache
    majorID = major
    executor = execu
    get_jadwal_status_func = status_getter
    log_file = logfile
    _valid_role = valid_role_func
    SSKM_ROOMS = sskm_rooms_storage if sskm_rooms_storage is not None else {}
    
    
# Fungsi untuk membersihkan kode warna ANSI (seperti \u001b[0;32m)
def strip_ansi(text):
    if not text: return ""
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_escape.sub('', text)
# Dictionary global untuk menyimpan progress download
download_progress = {}
# Fungsi Hook untuk menangkap progress dari yt-dlp internal
def my_hook(d, task_id):
    if task_id in download_progress and download_progress[task_id].get('cancelled', False):
            logging.info(f"[HOOK] Membunuh task {task_id} karena dibatalkan user.")
            raise yt_dlp.utils.DownloadError("Dibatalkan oleh User")
    if d['status'] == 'downloading':
        # Ambil data raw
# 1. Ambil Data Raw
        raw_p = d.get('_percent_str', '0%')
        raw_s = d.get('_speed_str', 'N/A')
        raw_size = d.get('_total_bytes_str', 'N/A')
        raw_eta = d.get('_eta_str', 'N/A')

        # 2. Bersihkan (Strip ANSI)
        clean_p = strip_ansi(raw_p).replace('%', '').strip()
        clean_s = strip_ansi(raw_s).strip()
        clean_size = strip_ansi(raw_size).strip()
        clean_eta = strip_ansi(raw_eta).strip()

        # Coba konversi ke float
        try:
            progress_val = float(clean_p)
        except ValueError:
            progress_val = 0.0
        logging.debug(f"[DEBUG HOOK] Raw: {raw_p} -> Clean: {progress_val}% | Speed: {clean_s}")
        
       # 5. Simpan ke Global Dict
        download_progress[task_id] = {
            "progress": progress_val,
            "speed": clean_s,
            "size": clean_size,
            "eta": clean_eta,
            "status": "Downloading"
        }
    elif d['status'] == 'finished':
        download_progress[task_id] = {
            "progress": 100,
            "status": "Converting",
            "text": "Sedang memproses konversi..."
        }
        
# Hook khusus untuk memantau FFmpeg/Konversi
def my_postprocessor_hook(d, task_id):
    if task_id not in download_progress:
        return

    if d['status'] == 'started':
        download_progress[task_id]['status'] = 'Converting'
        download_progress[task_id]['text'] = 'Sedang mengonversi video (FFmpeg)...'
    
    elif d['status'] == 'finished':
        download_progress[task_id]['status'] = 'Converting'
        download_progress[task_id]['text'] = 'Finalisasi file...'
# mengecek status koneksi Sicyca
# mengecek status koneksi Sicyca
@api_bp.route('/status_koneksi')
def api_status():
    # 1. Ambil user_id dari session flask
    user_id = session.get('user_id')
    
    if not user_id:
        # User flask belum login -> Kirim status 'error' agar frontend jadi Merah
        return jsonify({
            "status": "error", 
            "message": "Anda belum login."
        })

    # 2. Cek apakah session Sicyca valid (Real Check)
    # Menggunakan get_authenticated_session untuk memastikan koneksi ke Gate/Sicyca hidup
    sicyca_session = get_authenticated_session(user_id)
    
    # 3. Kondisi SUKSES (Frontend Hijau)
    if sicyca_session:
        return jsonify({
            "status": "ready",  # WAJIB: 'ready' (sesuai x-if="sicycaStatus === 'ready'")
            "message": "Terhubung ke Sicyca."
        })
    
    # 4. Kondisi GAGAL (Frontend Merah)
    else:
        return jsonify({
            "status": "error",  # WAJIB: 'error' (sesuai x-if="sicycaStatus === 'error'")
            "message": "Gagal terhubung ke server Sicyca (Session Invalid)."
        })

# Untuk mencari mahasiswa atau staff
@api_bp.route('/search', methods=['POST'])
@login_required
def api_search():
    data = request.get_json()   
    query = data.get('query', '').strip()
    if not query:
        return "<p class='text-gray-400 p-4'>Query tidak boleh kosong.</p>"

    future_mahasiswa = executor.submit(search_mahasiswa, query)
    future_staff = executor.submit(search_staff, query)
    df_mahasiswa = future_mahasiswa.result()
    df_staff = future_staff.result()

    combined_results = []
    if not df_mahasiswa.empty:
        for _, row in df_mahasiswa.iterrows():
            nim = row.get('NIM', '')
            if majorID:
                prodi_name = majorID.get(nim[2:7], 'Prodi Tidak Dikenal') if nim and len(nim) >= 7 else 'Prodi Tidak Dikenal'
            else:
                prodi_name = 'Sistem Belum Siap'
            combined_results.append({
                'Tipe': 'Mahasiswa',
                'Nama': html.escape(str(row.get('Nama', ''))),
                'IDMhs': html.escape(str(nim)),
                'Status': html.escape(str(row.get('Status', ''))),
                'Prodi': html.escape(str(prodi_name)),
                'Detail': html.escape(str(row.get('Dosen Wali', '')))
            })
    if not df_staff.empty:
        for _, row in df_staff.iterrows():
            combined_results.append({
                'Tipe': 'Staff/Dosen',
                'Nama': html.escape(str(row.get('Nama', ''))),
                'IDStaff': html.escape(str(row.get('NIK', ''))),
                'Bagian': html.escape(str(row.get('Bagian', ''))),
                'Detail': html.escape(str(row.get('Email', '')))
            })

    html_output = ""
    if combined_results:
        for item in combined_results:
            detail_html = ""
            if item['Tipe'] == 'Mahasiswa':
                detail_html = f"""
           <dt class="font-medium text-gray-400">NIM</dt>
<dd class="col-span-2 text-white flex items-center" id="nim-{item['IDMhs']}">
    <span>{item['IDMhs']}</span>
    <!-- Tombol Salin di sebelah NIM -->
<button class="copy-id-btn p-1 text-gray-400 hover:text-white transition" 
    data-name="{item['IDMhs']}" title="Salin NIM">
    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path>
    </svg>
</button>


</dd>

<dt class="font-medium text-gray-400">Status</dt><dd class="col-span-2 text-white">{item['Status']}</dd>
<dt class="font-medium text-gray-400">Prodi</dt><dd class="col-span-2 text-white">{item['Prodi']}</dd>
<dt class="font-medium text-gray-400">Dosen Wali</dt><dd class="col-span-2 text-white">{item['Detail']}</dd>

<!-- Tombol di bawah Dosen Wali -->
<dd class="col-span-3 mt-2">
    <button class="photo-btn px-3 py-1 text-sm bg-blue-600 hover:bg-blue-500 rounded text-white" data-role="mahasiswa" data-id="{item['IDMhs']}">Lihat Foto</button>
</dd>

                """
            else:
                detail_html = f"""
                <dt class="font-medium text-gray-400">NIK</dt>
                <dd class="col-span-2 text-white flex items-center" id="nik-{item['IDStaff']}">
                    <span>{item['IDStaff']}</span>
                    <button class="copy-id-btn p-1 text-gray-400 hover:text-white transition" 
                        data-name="{item['IDStaff']}" title="Salin NIK">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path>
                        </svg>
                    </button>
                </dd>

                <dt class="font-medium text-gray-400">Bagian</dt><dd class="col-span-2 text-white">{item['Bagian']}</dd>
                <dt class="font-medium text-gray-400">Email</dt><dd class="col-span-2 text-white">{item['Detail']}</dd>
                
                <dd class="col-span-3 mt-2">
                    <button class="photo-btn px-3 py-1 text-sm bg-blue-600 hover:bg-blue-500 rounded text-white" data-role="staff" data-id="{item['IDStaff']}">Lihat Foto</button>
                </dd>
                """

            html_output += f"""
            <div x-data="{{ isOpen: false }}" class="border-b border-gray-700 last:border-b-0">
    <div class="w-full text-left p-4 ">
        <div class="flex justify-between items-center">
            <div class="flex items-center space-x-2">
               <button class="copy-name-btn flex items-center p-1 text-white hover:text-gray-400 transition" 
    data-name="{item['Nama']}" title="Salin Nama">
    <span class="font-semibold text-white mr-2 hover:text-gray-400">{item['Nama']}</span>
    <!-- Ikon Salin -->
    <svg class="w-4 h-4 hover:text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path>
    </svg>
</button>


                <span class="text-xs text-gray-300 ml-2 px-2 py-1 bg-gray-600 rounded-full">{item['Tipe']}</span>
            </div>

            <!-- SVG yang bisa dipencet untuk membuka dan menutup deskripsi -->
            <div class="hover:bg-gray-700 focus:outline-none rounded-full p-2">
            <svg @click="isOpen = !isOpen" class="w-5 h-5 transform transition-transform duration-300 cursor-pointer" 
                 :class="{{'rotate-180': isOpen}}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
            </svg>
            </div>
        </div>
    </div>

    <!-- Bagian detail yang terbuka atau tertutup -->
    <div x-show="isOpen" x-transition class="p-4 bg-gray-900 border-t border-gray-700 text-sm">
        <dl class="grid grid grid-cols-1 sm:grid-cols-3 gap-2 text-sm">{detail_html}</dl>
    </div>
</div>

            """
        
        # **JS: Overlay untuk Tombol (Delegation untuk Alpine)**
        # html_output += """
       
        # """

    else:
        html_output = "<p class='text-gray-400 p-4'>Tidak ada data yang ditemukan.</p>"

    return html_output  # bukan jsonify

# Endpoint yt-dlp untuk mendapatkan link download YouTube
@api_bp.route('/get-youtube-info', methods=['POST'])
@login_required
def get_youtube_info():
    data = request.get_json()
    url = data.get('url')
    
    if not url or ('youtube.com' not in url and 'youtu.be' not in url):
        return jsonify({"error": "URL YouTube tidak valid"}), 400

    logging.info(f"Menerima permintaan yt-dlp (info) untuk: {url}")

    ydl_opts = {
        'quiet': True, 
        'noplaylist': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            title = info.get('title', 'video_tanpa_judul')
            thumbnail = info.get('thumbnail')
            
            # 1. Ambil semua resolusi video-only (1080p, 720p, dll)
            video_formats = [
                f for f in info.get('formats', []) 
                if f.get('vcodec') != 'none' and f.get('acodec') == 'none' and f.get('ext') in ['mp4', 'webm']
            ]
            # Ambil resolusi unik, urutkan dari besar ke kecil
            resolutions = sorted(
                list(set([f.get('height') for f in video_formats if f.get('height')])), 
                reverse=True
            )
            # Format labelnya (e.g., "1080p", "720p")
            video_qualities = [f"{r}p" for r in resolutions if r]
            
            # 2. Ambil video + audio (biasanya maks 720p)
            combined_formats = [
                f for f in info.get('formats', []) 
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('ext') in ['mp4', 'webm']
            ]
            combined_qualities = sorted(
                list(set([f.get('height') for f in combined_formats if f.get('height')])),
                reverse=True
            )
            # Gabungin semua kualitas video
            all_video_qualities = sorted(list(set(video_qualities + [f"{r}p" for r in combined_qualities])), reverse=True)
            # Kalo nggak ada, kasih default
            if not all_video_qualities:
                all_video_qualities = ['best']


            # 3. Ambil kualitas audio
            audio_formats = [
                f for f in info.get('formats', []) 
                if f.get('vcodec') == 'none' and f.get('acodec') != 'none' and f.get('ext') in ['m4a', 'webm']
            ]
            audio_bitrates = sorted(
                list(set([f.get('abr') for f in audio_formats if f.get('abr')])),
                reverse=True
            )
            # Format labelnya (e.g., "Best (128k)", "Medium (49k)")
            audio_qualities = []
            if audio_bitrates:
                audio_qualities.append({'id': 'best', 'label': f"Best (≈{int(audio_bitrates[0])}k)"})
                if len(audio_bitrates) > 1:
                    audio_qualities.append({'id': 'medium', 'label': f"Medium (≈{int(audio_bitrates[-1])}k)"})
            else:
                audio_qualities.append({'id': 'best', 'label': 'Best Audio'})

            
            logging.info(f"yt-dlp: Info diambil untuk '{title}'")
            
            return jsonify({
                "success": True,
                "title": title, 
                "thumbnail": thumbnail,
                "video_qualities": all_video_qualities, # e.g., ["1080p", "720p", "480p"]
                "audio_qualities": audio_qualities  # e.g., [{"id": "best", "label": "Best (126k)"}]
            })

    except yt_dlp.utils.DownloadError as e:
        return jsonify({"error": f"Gagal mengambil info video. Mungkin video ini private atau dihapus."}), 500
    except Exception as e:
        logging.error(f"[yt-dlp info] Error: {e}")
        return jsonify({"error": "Terjadi kesalahan internal saat mengambil info video."}), 500
        
# Endpoint yt-dlp untuk request konversi
@api_bp.route('/request-conversion', methods=['POST'])
@login_required
def request_conversion():
    data = request.get_json()
    url = data.get('url')
    ext_req = data.get('ext')
    quality = data.get('quality')
    # TAMBAHAN: Terima task_id dari frontend
    task_id = data.get('task_id')

    if not url or not ext_req or not quality:
        return jsonify({"error": "URL, format, dan kualitas wajib diisi"}), 400
    if not task_id:
            # Fallback kalau frontend lupa kirim (tapi progress ga bakal jalan)
            task_id = str(uuid.uuid4())
    
        # Inisialisasi status di global dict
    download_progress[task_id] = {"progress": 0, "status": "Starting"}
    temp_dir = current_app.config.get('TEMP_DOWNLOAD_DIR', '/app/temp_downloads')
    unique_id = str(uuid.uuid4())

    # TEMPLATE untuk yt-dlp
    template_path = os.path.join(temp_dir, unique_id + ".%(ext)s")

    # PATH final setelah konversi
    final_filename = f"{unique_id}.{ext_req}"
    final_path = os.path.join(temp_dir, final_filename)

    logging.info(f"Memulai konversi ke {ext_req} ({quality}) untuk {url}...")

    # SETUP yt-dlp
    ydl_opts = {
        'quiet': True,
        'noplaylist': True,
        'no_warnings': True,
        'no_color': True,
        'outtmpl': template_path,
        'progress_hooks': [lambda d: my_hook(d, task_id)],
        'postprocessor_hooks': [lambda d: my_postprocessor_hook(d, task_id)], 
        'postprocessors': [], # (Biarkan yang bawah tetap kosong/default)
        'postprocessors': [],
        'http_headers': {
            'User-Agent': 'Mozilla/5.0'
        }
    }

    # QUALITY selector
    quality_selector = ""
    if quality.endswith("p"):
        quality_selector = f"[height={quality.replace('p','')}]"

    # AUDIO formats
    if ext_req in ['mp3','wav','webm_audio']:
        ydl_opts['format'] = "bestaudio/best"
        if ext_req != 'webm_audio':
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': ext_req,
                'preferredquality': '192'
            }]

    # VIDEO formats
    if ext_req in ['mp4','mkv','mpeg','webm_video']:
        if ext_req == 'webm_video':
            ext_req = 'webm'
        ydl_opts['format'] = f"bestvideo{quality_selector}+bestaudio/best"
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': ext_req
        }]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        # CARI file hasil konversi
        temp_output = None
        for ext in ['mp4','mkv','webm','mpeg','mp3','wav']:
            candidate = os.path.join(temp_dir, f"{unique_id}.{ext}")
            if os.path.exists(candidate):
                temp_output = candidate
                break

        if not temp_output:
            raise Exception("FFmpeg gagal menghasilkan output.")

        # RENAME file hasil
        os.rename(temp_output, final_path)

        # Buat nama file buat user
        title = info.get('title', 'video')
        video_id = info.get('id', 'NA')
        sanitized_title = sanitize_filename(title)
        download_as_filename = f"{sanitized_title} [{video_id}].{ext_req}"
        # BERSIHKAN progress dictionary setelah selesai
        if task_id in download_progress:
            # 1. Kasih tau SSE kalau proses sudah FINISHED secara eksplisit
            # download_progress[task_id]['status'] = 'Finished'
            # download_progress[task_id]['progress'] = 100
            # download_progress[task_id]['text'] = 'Selesai! Mengirim file...'
            
            # 2. Tidur sebentar (1 detik) biar SSE sempat kirim data 'Finished' ini ke browser
            # time.sleep(1)
            # 3. Baru hapus datanya
            del download_progress[task_id]
        return jsonify({
            "success": True,
            "download_url": url_for('api.download_converted_file', filename=final_filename, download_as=download_as_filename),
            "download_as": download_as_filename
        })

    except Exception as e:
        if task_id in download_progress:
             download_progress[task_id] = {"status": "Error", "message": "Konversi gagal"}
             # Jangan langsung dihapus biar frontend bisa baca errornya sebentar
        logging.error(f"Konversi gagal: {e}")
        return jsonify({"error": "Konversi gagal. Silakan coba lagi."}), 500

# Endpoint untuk membatalkan task yg sedang berjalan
@api_bp.route('/cancel-task', methods=['POST'])
def cancel_task():
    # force=True agar bisa baca text/plain dari sendBeacon
    data = request.get_json(force=True, silent=True) 
    if not data:
        return "No data", 400
        
    task_id = data.get('task_id')
    if task_id and task_id in download_progress:
        # Set flag cancelled jadi True
        download_progress[task_id]['cancelled'] = True
        download_progress[task_id]['status'] = 'Cancelled'
        logging.info(f"Menerima sinyal kill untuk task: {task_id}")
        return jsonify({"status": "cancelled"})
    
    return jsonify({"status": "not_found"}), 404

# Route untuk mengirim progress ke frontend via SSE
@api_bp.route('/progress/<task_id>', methods=['GET'])
def progress(task_id):
    # Generator function
    def generate():
        while True:
            # Cek apakah task_id ada di memori
            if task_id in download_progress:
                data = download_progress[task_id]
                # Kirim data sebagai SSE
                yield f"data: {json.dumps(data)}\n\n"
                
                # Jika status error, stop stream
                if data.get('status') == 'Error':
                    break
            else:
                # Jika task_id hilang (berarti sudah selesai atau belum mulai), kirim keep-alive atau selesai
                # Kita asumsikan kalau hilang tiba-tiba saat stream jalan berarti selesai/dihapus endpoint utama
                yield f"data: {json.dumps({'progress': 100, 'status': 'Finished'})}\n\n"
                break
            
            time.sleep(0.5) # Update setiap 0.5 detik

    # UPDATE DISINI: Tambahkan headers anti-buffering
    response = Response(stream_with_context(generate()), content_type='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no' # Penting buat Nginx/Proxy
    return response
# Endpoint untuk download file hasil konversi
@api_bp.route('/download-file/<path:filename>') # <-- HARUS 'path:'
@login_required
def download_converted_file(filename):
    # ... (Isi fungsinya udah bener dari kemarin)
    # ... (Cek path traversal, kirim file, dll)
    temp_dir = current_app.config.get('TEMP_DOWNLOAD_DIR', '/app/temp_downloads')
    file_path = os.path.join(temp_dir, filename)
    norm_temp_dir = os.path.normpath(temp_dir)
    norm_file_path = os.path.normpath(file_path)

    if not norm_file_path.startswith(norm_temp_dir):
        return "Akses ditolak", 403
    if not os.path.exists(file_path):
        return "File tidak ditemukan", 404
    download_as = request.args.get('download_as')
    try:
                return send_from_directory(
            temp_dir,
            filename,
            as_attachment=True,
            download_name=download_as or filename
        )
    finally:
        pass # Biarin cleanup job
            
# Untuk melihat log terus menerus
@api_bp.route('/log')
@login_required
def api_log():
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            lines.reverse()
            return Response("".join(lines), mimetype='text/plain')
    return Response("Log file tidak ditemukan.", mimetype='text/plain', status=404)


# Mengecek apakah jadwal ready atau error
@api_bp.route('/jadwal-status')
def api_jadwal_status():
    # Panggil fungsinya untuk dapat data terbaru realtime
    if get_jadwal_status_func:
        return jsonify(get_jadwal_status_func())
    return jsonify({"status": "unknown", "message": "Status belum diinisialisasi"})

# Mendapatkan foto mahasiswa atau staff dalam base64
@api_bp.route('/photo/<role>/<id_>', methods=['GET'])
def get_photo(role, id_):
    if not _valid_role(role):
        return jsonify({'error': 'Role tidak valid'}), 400
    
    if not id_.isdigit():
        return jsonify({'error': 'ID harus angka'}), 400
    
    # Cek cache dulu
    cache_key = f"{role}_{id_}"
    if cache_key in photo_cache:
        logging.info(f"Foto {role}/{id_} dari cache.")
        return jsonify({'success': True, 'image_b64': photo_cache[cache_key]})
    
    # Fetch dari Sicyca
    logging.info(f"Fetching foto untuk tombol: {role}/{id_}")  # Ubah log ke "tombol" untuk clarity
    image_content = fetch_photo_from_sicyca(role, id_)
    
    if image_content is None:
        logging.warning(f"Fetch gagal untuk {role}/{id_}.")
        return jsonify({'success': False, 'message': 'Foto tidak tersedia'})
    
    # Encode ke base64
    image_b64 = base64.b64encode(image_content).decode('utf-8')
    
    # Simpan ke cache
    photo_cache[cache_key] = image_b64
    
    logging.info(f"Foto {role}/{id_} berhasil di-encode ({len(image_b64)} chars).")
    return jsonify({'success': True, 'image_b64': image_b64})
    
# Di api/api.py
@api_bp.route("/fetch-data-ultah", methods=['GET']) # <-- 1. Ganti ke sintaks Flask
def fetch_data_ultah_route():
    try:
        # 2. Ambil query param pake cara Flask
        force_val = request.args.get('force', 'false').lower()
        force_refresh_flag = force_val in ['true', '1', 'yes']
        
        # 3. Panggil fungsi intinya
        data_ultah = fetch_data_ultah(force_refresh=force_refresh_flag)
        
        # 4. Kembalikan sebagai JSON
        return jsonify(data_ultah)
        
    except Exception as e:
        # 5. Tambahin error handling biar aman
        status_code = 500
        detail_message = str(e)
        
        if hasattr(e, 'status_code'):
            status_code = e.status_code
        if hasattr(e, 'detail'):
            detail_message = e.detail
            
        logging.error(f"Error di endpoint /fetch-data-ultah: {detail_message}")
        
        return jsonify({
            "error": True, 
            "message": detail_message,
            "jumlah": 0, # Kasih nilai default biar HTML nggak error
            "rows": []
        }), status_code

# (opsional) tetap sediakan alias lama
@api_bp.route("/data_ultah", methods=['GET']) # <-- Ganti ini juga
def data_ultah_alias():
    return fetch_data_ultah_route() # Panggil fungsi di atas biar logikanya sama
    
@api_bp.route('/krs-data', methods=['GET'])
@login_required
def api_krs_data():
    """
    Endpoint untuk mengambil data KRS mahasiswa yang sedang login.
    """
    logging.info("API: Menerima request untuk data KRS")
    try:
        # Panggil fungsi scraper (DataFrame)
        df_krs = scrape_krs()

        if df_krs.empty:
            logging.warning("API: Data KRS kosong atau gagal diambil.")
            return jsonify({
                "success": False,
                "message": "Data KRS tidak ditemukan atau sesi Sicyca habis.",
                "data": []
            })
        masa_studi_text = fetch_masa_studi()

        # Convert DataFrame ke List of Dictionaries (JSON friendly)
        # orient='records' bikin jadi [{col1:val1, col2:val2}, ...]
        krs_list = df_krs.to_dict(orient='records')
        
        logging.info(f"API: Berhasil mengambil {len(krs_list)} data KRS.")
        return jsonify({
            "success": True,
            "data_krs": krs_list,
            "masa_studi": masa_studi_text
        })
        
    except Exception as e:
        logging.error(f"API Error (KRS): {e}")
        return jsonify({
            "success": False, 
            "message": "Terjadi kesalahan server saat mengambil data KRS.",
            "data": []
        }), 500

@api_bp.route('/krs-detail', methods=['POST'])
@login_required
def api_krs_detail():
    """
    Endpoint dinamis untuk mengambil detail KRS.
    Frontend mengirim payload JSON:
    {
        "type": "kehadiran",  # nilai / matakuliah / materikuliah / kehadiranprak
        "mk": "12345",
        "kls": "P1",
        "grup": "A",          # Opsional (untuk praktek)
        "nik": "123"          # Opsional (untuk materi)
    }
    """
    data = request.get_json()
    req_type = data.get('type')
    
    if not req_type:
        return jsonify({"success": False, "message": "Parameter 'type' wajib diisi."}), 400

    # Mapping parameter frontend ke parameter Sicyca URL (?t=...)
    # Sesuai JS: t=kehadiran, t=kehadiranprak, t=nilai, t=matakuliah, t=materikuliah
    
    params = {
        "t": req_type
    }
    
    # Masukkan parameter lain jika ada
    if data.get('mk'): params['mk'] = data.get('mk')
    if data.get('kls'): params['kls'] = data.get('kls')
    if data.get('grup'): params['grup'] = data.get('grup')
    if data.get('nik'): params['nik'] = data.get('nik') # Untuk materi kuliah

    # Panggil Scraper
    result = scrape_krs_detail(params)
    
    
    status_code = 200 if result.get("success") else 500
    return jsonify(result), status_code


@api_bp.route('/jadwal-list', methods=['GET'])
def api_jadwal_list():
    """
    Endpoint baru untuk mengambil data jadwal.json mentah.
    """
    try:
        with open('jadwal.json', 'r', encoding='utf-8') as f:
            data_json = json.load(f)
        
        # Kirim datanya (metadata + list jadwal)
        return jsonify(data_json)
        
    except FileNotFoundError:
        logging.warning("API: jadwal.json tidak ditemukan.")
        return jsonify({
            "error": True, 
            "message": "File jadwal belum dibuat.",
            "data": []
        }), 404
    except Exception as e:
        logging.error(f"Error di /api/jadwal-list: {e}")
        return jsonify({
            "error": True, 
            "message": str(e),
            "data": []
        }), 500

@api_bp.route('/sks-data', methods=['GET'])
@login_required
def api_sks_data():
    """
    Endpoint untuk mengambil data SKS (Tempuh, Ambil, Sisa).
    """
    try:
        # Panggil fungsi scraper
        raw_result = fetch_sks()
        
        # Jika return dict kosong, berarti gagal (session/token)
        if not raw_result:
            return jsonify({
                "success": False,
                "message": "Gagal mengambil data SKS atau sesi habis."
            }), 500

        # raw_result formatnya dari scraper: { "data": { "sks_tempuh": X, ... } }
        # Kita ekstrak isinya biar rapi di frontend
        sks_data = raw_result.get('data', {})

        return jsonify({
            "success": True,
            "data": sks_data 
        })

    except Exception as e:
        logging.error(f"[API] Error SKS: {e}")
        return jsonify({
            "success": False, 
            "message": "Terjadi kesalahan server saat mengambil data SKS."
        }), 500

@api_bp.route('/sync-cookies', methods=['GET'])
@login_required
def sync_cookies():
    """
    Mengambil cookies Gate/SSO yang tersimpan di database untuk user ini.
    Frontend akan menggunakan data ini untuk 'menanam' cookies di browser.
    """
    try:
        # 1. Ambil user_id dari token JWT (diset oleh @login_required)
        user_id = g.user.get('sub')
        if not user_id:
            return jsonify({"success": False, "message": "User ID tidak ditemukan"}), 401

        # 2. Load cookies dari Database menggunakan Model
        gate_session_model = GateSession()
        cookie_jar = gate_session_model.load_cookies(user_id)

        cookies_list = []
        
        # 3. Jika ada cookies di DB, konversi ke format JSON list
        if cookie_jar:
            for cookie in cookie_jar:
                # Kita ambil atribut cookie standar
                cookies_list.append({
                    "name": cookie.name,       # gate_dinamika_session, SSO_TOKEN, dll
                    "value": cookie.value,
                    "domain": ".dinamika.ac.id", # Paksa domain global agar terbaca di subdomain
                    "path": "/",
                    "max_age": 7200,           # Set umur cookie (2 jam)
                    "samesite": "Lax"
                })
            
            logging.info(f"[Sync Cookies] Mengirim {len(cookies_list)} cookies untuk User ID {user_id}")
        else:
            logging.info(f"[Sync Cookies] Tidak ada session aktif di DB untuk User ID {user_id}")
        return jsonify({
            "success": True,
            "cookies": cookies_list
        })

    except Exception as e:
        logging.error(f"[Sync Cookies] Error: {e}")
        return jsonify({
            "success": False,
            "message": f"Server Error: {str(e)}",
            "cookies": []
        }), 500

@api_bp.route('/public/ultah', methods=['GET'])
def public_api_ultah():
    """
    Public API untuk mengambil data ulang tahun (Tanpa Login).
    Return JSON: Nama, Nim, Tanggal Lahir, Usia, Prodi
    """
    try:
        # Ambil semua data via model
        records = ultah_model.get_all()
        
        data = []
        for r in records:
            item = {
                'nama': r.get('nama'),
                'nim': r.get('nim'),
                'tanggal_lahir': r.get('tanggal_display'), # Format: "DD Bulan YYYY"
                'usia': r.get('usia'),
                'prodi': r.get('prodi'),
                'foto': r.get('foto_base64')
            }
            data.append(item)
            
        return jsonify(data)
        
    except Exception as e:
        logging.error(f"[API Public Ultah] Error: {e}")
        return jsonify({'error': str(e)}), 500
        
@api_bp.route('/get-my-credentials', methods=['GET'])
@login_required
def get_my_credentials():
    """
    Endpoint untuk mengambil password user (dekripsi) agar bisa di-copy di frontend.
    """
    try:
        user_id = g.user.get('sub')
        gate_model = GateUser() # Init model
        
        # Ambil credentials dari database
        _, username, decrypted_password = gate_model.get_credentials_by_user_id(user_id)
        
        if not decrypted_password:
             return jsonify({"success": False, "message": "Password belum di-set"})
        csrf_token = get_csrf_token_gate()
        
        # Mask password: tampilkan 3 karakter pertama + ***
        masked_pw = decrypted_password[:3] + '***' if len(decrypted_password) > 3 else '***'
        return jsonify({
            "success": True, 
            "userid": username,
            "password": masked_pw,
            "gate_token": csrf_token
        })
    except Exception as e:
        logging.error(f"[API] Error get-my-credentials: {e}")
        return jsonify({"success": False, "message": "Terjadi kesalahan saat mengambil kredensial."}), 500
    
@api_bp.route('/my-photo')
@login_required
def get_my_profile_photo():
    """
    API endpoint untuk mengambil foto profil user yang sedang login
    menggunakan endpoint khusus.
    """
    try:
        # 1. Ambil User ID dan NIM dari Token/Session
        user_id = g.user.get('sub')
        gate_model = GateUser()
        _, nim, _ = gate_model.get_credentials_by_user_id(user_id)
        
        if not nim:
            return jsonify({'success': False, 'message': 'NIM tidak ditemukan'}), 404

        # 2. Cek Cache (Opsional, biar gak nembak terus)
        cache_key = f"my_photo_{nim}"
        if photo_cache and cache_key in photo_cache:
            logging.info(f"Foto profil {nim} diambil dari cache.")
            return jsonify({'success': True, 'image_b64': photo_cache[cache_key]})

        # 3. Panggil Scraper Fungsi Baru
        image_content = fetch_profil_mhs(nim, user_id=user_id)
        
        if image_content:
            return Response(image_content, mimetype='image/jpeg')
        else:
            # Fallback ke default jika gagal
            return redirect(url_for('static', filename='no_photo.jpg'))

    except Exception as e:
        logging.error(f"Error /my-photo: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
    
@api_bp.route('/detail_sskm', methods=['GET'])
def get_detail_sskm():
    """
    Mengambil data mentah dari fetch_sskm_data dan mengembalikannya sebagai JSON.
    Tidak ada pemrosesan atau manipulasi data di sini.
    """
    # 1. Panggil fungsi scrapper
    raw_data = fetch_sskm_data()
    
    # 2. Return langsung hasilnya sebagai JSON
    return jsonify(raw_data)
@api_bp.route('/detail_nilai', methods=['GET'])
def get_detail_nilai():
    """
    Mengambil data mentah dari fetch_nilai_data dan mengembalikannya sebagai JSON.
    Tidak ada pemrosesan atau manipulasi data di sini.
    """
    # 1. Panggil fungsi scrapper
    raw_data = scrape_krs_detail()
    
    # 2. Return langsung hasilnya sebagai JSON
    return jsonify(raw_data)

# ===== SSKM ENDPOINTS =====
@api_bp.route('/sskm/room/create', methods=['POST'])
def create_room():
    """Create a new SSKM Room and return the code"""
    global SSKM_ROOMS
    try:
        # Generate 10-char random uppercase alphanumeric code
        room_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
        
        # Ensure Uniqueness (low collision probability, but good practice)
        while room_code in SSKM_ROOMS:
            room_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
            
        SSKM_ROOMS[room_code] = []
        logging.info(f"New SSKM Room Created: {room_code}")
        return jsonify({'success': True, 'room_code': room_code})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/sskm/room/join', methods=['POST'])
def join_room():
    """Check if a room exists"""
    global SSKM_ROOMS
    try:
        data = request.get_json()
        room_code = data.get('room_code')
        
        if not room_code:
            return jsonify({'success': False, 'message': 'Room code required'}), 400
            
        if room_code in SSKM_ROOMS:
            return jsonify({'success': True, 'room_code': room_code})
        else:
            return jsonify({'success': False, 'message': 'Room tidak ditemukan'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/sskm/room/data', methods=['GET'])
def get_room_data():
    """Get all data for a specific room"""
    global SSKM_ROOMS
    try:
        room_code = request.args.get('room_code')
        if not room_code:
            return jsonify({'success': False, 'error': 'Room code required'}), 400
            
        if room_code not in SSKM_ROOMS:
             return jsonify({'success': False, 'error': 'Room not found'}), 404
             
        data = SSKM_ROOMS[room_code]
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/sskm/sync', methods=['POST'])
def sync_sskm_data():
    """Menerima data SSKM dari client dan simpan ke memory Room spesifik"""
    global SSKM_ROOMS
    try:
        data = request.get_json()
        room_code = data.get('room_code')
        
        if not room_code or room_code not in SSKM_ROOMS:
             return jsonify({'success': False, 'error': 'Room code invalid or missing'}), 400

        if data and 'rfidData' in data:
            # Clear and update list in-place to maintain reference if possible, 
            # but since it's a dict now, we modify the list inside the dict.
            SSKM_ROOMS[room_code] = data['rfidData']
            logging.info(f"SSKM data synced for Room {room_code}: {len(SSKM_ROOMS[room_code])} records")
            return jsonify({'success': True, 'count': len(SSKM_ROOMS[room_code])})
        return jsonify({'success': False, 'error': 'Invalid data'}), 400
    except Exception as e:
        logging.error(f"Error syncing SSKM data: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Global variable for duplicate event broadcasting
# Structure: { 'room_code': { 'type': ..., 'value': ..., 'timestamp': ... } }
SSKM_LAST_DUPLICATE = {}

@api_bp.route('/sskm/duplicate', methods=['POST'])
def sskm_duplicate_warning():
    """Endpoint untuk broadcast warning duplikat ke public screen (Room specific)"""
    global SSKM_LAST_DUPLICATE
    try:
        data = request.get_json()
        room_code = data.get('room_code')
        
        if not room_code:
             return jsonify({'success': False, 'error': 'Room code missing'}), 400

        if data and 'type' in data and 'value' in data:
            # Update global event for SSE to pick up for this room
            SSKM_LAST_DUPLICATE[room_code] = {
                "type": data['type'],
                "value": data['value'],
                "timestamp": time.time()
            }
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Invalid data'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/sskm/add', methods=['POST'])
def add_sskm_data():
    """Menambahkan satu data SSKM (NIM/UUID) dan handle duplikasi (Room specific)"""
    global SSKM_ROOMS, SSKM_LAST_DUPLICATE
    try:
        data = request.get_json()
        room_code = data.get('room_code')

        if not room_code:
            return jsonify({'success': False, 'error': 'Room code missing'}), 400
        
        if room_code not in SSKM_ROOMS:
             return jsonify({'success': False, 'error': 'Room not found'}), 404

        if not data or 'value' not in data:
            return jsonify({'success': False, 'error': 'Value wajib ada'}), 400
            
        inputType = data.get('type', 'NIM') # Default NIM
        value = str(data['value']).strip()
        
        # Cek Duplikasi di Room ini
        room_data = SSKM_ROOMS[room_code]
        is_duplicate = False
        for item in room_data:
            # Cek key 'nim' atau 'uuid' tergantung inputType
            if inputType == 'NIM' and str(item.get('nim')) == value:
                is_duplicate = True
                break
            elif inputType == 'UUID' and str(item.get('uuid')) == value:
                is_duplicate = True
                break
                
        if is_duplicate:
            # Update global duplicate event untuk SSE Room ini
            SSKM_LAST_DUPLICATE[room_code] = {
                "type": inputType,
                "value": value,
                "timestamp": time.time()
            }
            logging.info(f"Duplicate scan detected in Room {room_code}: {inputType} {value}")
            return jsonify({'success': True, 'status': 'duplicate'})
        else:
            # Tambah data baru ke Room ini
            new_record = {
                "nim": value if inputType == 'NIM' else None,
                "uuid": value if inputType == 'UUID' else None,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            SSKM_ROOMS[room_code].append(new_record)
            logging.info(f"New SSKM record added to Room {room_code}: {new_record}")
            return jsonify({'success': True, 'status': 'added'})

    except Exception as e:
        logging.error(f"Error adding SSKM data: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ======================================================
# GOOGLE DRIVE INTEGRATION
# ======================================================
@api_bp.route('/google/drive/docs', methods=['GET'])
@login_required
def get_google_docs():
    """Endpoint API untuk mengambil list Google Docs milik user (Unified Auth)"""
    

    user_id = g.user.get('sub')
    service = google_cal_service.build_drive_service(user_id)
    
    if not service:
        return jsonify({'error': 'Google account belum terhubung'}), 401
        
    try:
        # Ambil query pencarian dan folder ID dari frontend
        search_query = request.args.get('q', '')
        folder_id = request.args.get('folderId', 'root')
        
        # Base query: Tidak di sampah
        q_clause = "trashed=false"
        
        if search_query:
            # Mode Pencarian: Search global (abaikan folder)
            safe_query = search_query.replace("'", "\\'") 
            q_clause += f" and name contains '{safe_query}'"
        else:
            # Mode Navigasi: List isi folder tertentu
            # Default 'root' kalau tidak ada folderId
            q_clause += f" and '{folder_id}' in parents"
            
        # Query nyari file
        results = service.files().list(
            q=q_clause,
            pageSize=100,
            fields="nextPageToken, files(id, name, modifiedTime, mimeType, iconLink, thumbnailLink)", # Tambah thumbnailLink
            orderBy="folder,modifiedTime desc" # Folder di atas, lalu urut waktu
        ).execute()
        
        files = results.get('files', [])
        return jsonify({'files': files}), 200
        
    except Exception as e:
        logging.error(f"[Google Drive API] Error fetch docs: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/google/drive/parse/<file_id>', methods=['GET'])
@login_required
def parse_google_doc(file_id):
    """Parse Google Doc content to extract logbook metadata"""

    
    user_id = g.user.get('sub')
    
    # Use the new build_docs_service logic
    service = google_cal_service.build_docs_service(user_id)
    if not service:
        return jsonify({'error': 'Failed to build Docs service'}), 500

    # Validate File Type (Must be Google Doc)
    drive_service = google_cal_service.build_drive_service(user_id)
    if drive_service:
        try:
            file_meta = drive_service.files().get(fileId=file_id, fields='mimeType').execute()
            if file_meta.get('mimeType') != 'application/vnd.google-apps.document':
                 return jsonify({'error': 'File yang dipilih bukan Google Doc. Mohon simpan file sebagai Google Doc terlebih dahulu via Drive.'}), 400
        except Exception as e:
            logging.warn(f"[Google Meta Check] Failed: {e}")


    try:
        # Fetch document
        document = service.documents().get(documentId=file_id).execute()
        
        # Helper to extract text
        def read_structural_elements(elements):
            text = ''
            for value in elements:
                if 'paragraph' in value:
                    elements = value.get('paragraph').get('elements')
                    for elem in elements:
                        text += elem.get('textRun', {}).get('content', '')
                elif 'table' in value:
                    table = value.get('table')
                    for row in table.get('tableRows'):
                        for cell in row.get('tableCells'):
                            text += read_structural_elements(cell.get('content'))
                elif 'tableOfContents' in value:
                     text += read_structural_elements(value.get('tableOfContents').get('content'))
            return text

        doc_content = document.get('body').get('content')
        full_text = read_structural_elements(doc_content)
        
        # Extract data using Regex
        data = {}
        
        patterns = {
            'nama': r'Nama\s*:\s*(.*)',
            'nim': r'Nim\s*:\s*(.*)',
            'fakultas': r'Fakultas\s*:\s*(.*)',
            'prodi': r'Prodi\s*:\s*(.*)',
            'nama_mitra': r'Nama Mitra\s*:\s*(.*)',
            'posisi_magang': r'Posisi Magang\s*:\s*(.*)',
            'nama_mentor': r'Nama Mentor\s*:\s*(.*)',
            'wa_mentor': r'Whatsapp Mentor\s*:\s*(.*)',
            'email_mentor': r'Email Mentor\s*:\s*(.*)',
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                data[key] = match.group(1).strip()
                
        # Handle Date Range
        # Format: "10-02-2026 sampai 10-07-2026"
        waktu_match = re.search(r'Waktu Pelaksanaan\s*:\s*(.*)', full_text, re.IGNORECASE)
        if waktu_match:
            date_str = waktu_match.group(1).strip()
            # Try splitting by 'sampai' or '-' or 'to'
            dates = re.split(r'\s+sampai\s+|\s+-\s+|\s+to\s+', date_str)
            
            def convert_date(d_str):
                try:
                    # Input is typically DD-MM-YYYY
                    # Return YYYY-MM-DD
                    from datetime import datetime
                    dt = datetime.strptime(d_str.strip(), '%d-%m-%Y')
                    return dt.strftime('%Y-%m-%d')
                except:
                    return d_str # Return original if parse fails

            if len(dates) >= 2:
                data['waktu_mulai'] = convert_date(dates[0])
                data['waktu_selesai'] = convert_date(dates[1])
        
        return jsonify({'success': True, 'data': data}), 200

    except Exception as e:
        logging.error(f"[Google Docs Parse] Error: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/google/drive/sync-activities/<int:logbook_id>', methods=['POST'])
@login_required
def sync_custom_activities(logbook_id):
    """Sync activities from Logbook Entries (DB) TO Google Doc — Per Month Tables"""

    data_in = request.json
    file_id = data_in.get('file_id')
    
    if not file_id:
         return jsonify({'error': 'File ID required'}), 400

    user_id = g.user.get('sub')
    service = google_cal_service.build_docs_service(user_id)
    if not service:
        return jsonify({'error': 'Failed to build Docs service'}), 500
        
    # Validate File Type (Must be Google Doc)
    drive_service = google_cal_service.build_drive_service(user_id)
    if drive_service:
        try:
            file_meta = drive_service.files().get(fileId=file_id, fields='mimeType').execute()
            if file_meta.get('mimeType') != 'application/vnd.google-apps.document':
                 return jsonify({'error': 'File yang dipilih bukan Google Doc. Mohon simpan file sebagai Google Doc terlebih dahulu via Drive.'}), 400
        except Exception as e:
            logging.warn(f"[Google Meta Check] Failed: {e}")

    try:
        # 1. Fetch Logbook metadata (for nama_mentor)
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM logbooks WHERE id = %s", (logbook_id,))
        logbook = cursor.fetchone()
        
        # 2. Fetch Entries from DB
        cursor.execute("SELECT * FROM logbook_entries WHERE logbook_id = %s ORDER BY tanggal ASC, id ASC", (logbook_id,))
        entries = cursor.fetchall()
        cursor.close()
        conn.close()

        if not entries:
            return jsonify({'error': 'Belum ada data kegiatan di website untuk disinkronkan.'}), 400

        nama_mentor = logbook.get('nama_mentor', 'Nama Mentor') if logbook else 'Nama Mentor'

        # 3. Group entries by month
        months_id = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 
                     'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']
        
        grouped_entries = {}
        for entry in entries:
            tgl = entry['tanggal']
            if tgl:
                if isinstance(tgl, str):
                    tgl = datetime.strptime(tgl, '%Y-%m-%d')
                month_key = f"{months_id[tgl.month]} {tgl.year}"
            else:
                month_key = "Belum Diketahui"
            
            if month_key not in grouped_entries:
                grouped_entries[month_key] = []
            grouped_entries[month_key].append(entry)

        # 4. Fetch Doc Structure — find first "Aktivitas Bulan" header
        document = service.documents().get(documentId=file_id).execute()
        doc_content = document.get('body').get('content')
        
        def get_text_simple(elements):
            text = ""
            for v in elements:
                if 'paragraph' in v:
                    for el in v.get('paragraph').get('elements'):
                        text += el.get('textRun', {}).get('content', '')
            return text

        # Find the start index of the first "Aktivitas Bulan" paragraph
        section_start_index = -1
        for element in doc_content:
            if 'paragraph' in element:
                txt = get_text_simple([element])
                if "Aktivitas Bulan" in txt:
                    section_start_index = element.get('startIndex')
                    break

        if section_start_index == -1:
            return jsonify({'error': 'Header "Aktivitas Bulan..." tidak ditemukan di Google Doc.'}), 404

        # 5. Find end of document body
        doc_body_end = doc_content[-1].get('endIndex', section_start_index + 1)
        
        # 6. Delete everything from section_start_index to end of doc body
        # We must keep at least index (end-1) because doc always ends with \n
        delete_end = doc_body_end - 1  # Don't delete the final newline
        
        delete_requests = []
        if delete_end > section_start_index:
            delete_requests.append({
                'deleteContentRange': {
                    'range': {
                        'startIndex': section_start_index,
                        'endIndex': delete_end
                    }
                }
            })
        
        if delete_requests:
            service.documents().batchUpdate(documentId=file_id, body={'requests': delete_requests}).execute()

        # 7. Now insert fresh content for each month at section_start_index
        # We build all text and structures from bottom to top (reverse order)
        # because we insert at the same index each time.
        # 
        # Strategy: Build text content first, then insert tables separately.
        # Actually, the Google Docs API has an 'insertTable' request!
        # 
        # Approach: Insert everything as text first (headers + signatures),
        # then insert tables. But tables need specific indices.
        #
        # Simplest approach: Build content month by month in FORWARD order,
        # inserting at the cursor position which advances each time.
        # We must re-fetch the doc after each month to get correct indices.
        #
        # BETTER approach: Insert all content in one batch using text + table requests,
        # but this requires careful index calculation.
        #
        # PRACTICAL approach: Process each month group sequentially.

        def clean_html(raw_html):
            if not raw_html: return '-'
            txt = re.sub(r'<li>', '\n• ', str(raw_html))
            txt = re.sub(r'<br\s*/?>', '\n', txt)
            txt = re.sub(r'</p>', '\n', txt)
            txt = re.sub(r'<[^>]+>', '', txt)
            txt = re.sub(r'\n\s*\n', '\n', txt)
            return txt.strip()

        month_keys = list(grouped_entries.keys())
        
        for month_idx, month_key in enumerate(month_keys):
            month_entries = grouped_entries[month_key]
            
            # Re-fetch doc to get current indices
            document = service.documents().get(documentId=file_id).execute()
            doc_content = document.get('body').get('content')
            
            # Find insertion point (end of doc body - 1, before final newline)
            insert_index = doc_content[-1].get('endIndex', 1) - 1
            
            # A. Insert header text: "Aktivitas Bulan {month_key}\n"
            header_text = f"Aktivitas Bulan {month_key}\n"
            
            batch1_requests = [
                {
                    'insertText': {
                        'location': {'index': insert_index},
                        'text': header_text
                    }
                },
                # Style the header as NORMAL_TEXT (not heading — match screenshot format)
                {
                    'updateParagraphStyle': {
                        'range': {
                            'startIndex': insert_index,
                            'endIndex': insert_index + len(header_text)
                        },
                        'paragraphStyle': {
                            'namedStyleType': 'NORMAL_TEXT',
                            'spaceAbove': {'magnitude': 12, 'unit': 'PT'},
                            'spaceBelow': {'magnitude': 6, 'unit': 'PT'}
                        },
                        'fields': 'namedStyleType,spaceAbove,spaceBelow'
                    }
                },
                # Make header text red, bold, slightly larger
                {
                    'updateTextStyle': {
                        'range': {
                            'startIndex': insert_index,
                            'endIndex': insert_index + len(header_text) - 1
                        },
                        'textStyle': {
                            'foregroundColor': {
                                'color': {
                                    'rgbColor': {'red': 0.8, 'green': 0.0, 'blue': 0.0}
                                }
                            },
                            'bold': True,
                            'underline': False,
                            'fontSize': {'magnitude': 13, 'unit': 'PT'}
                        },
                        'fields': 'foregroundColor,bold,underline,fontSize'
                    }
                }
            ]
            
            service.documents().batchUpdate(documentId=file_id, body={'requests': batch1_requests}).execute()
            
            # B. Re-fetch and insert table
            document = service.documents().get(documentId=file_id).execute()
            doc_content = document.get('body').get('content')
            table_insert_index = doc_content[-1].get('endIndex', 1) - 1
            
            num_rows = len(month_entries) + 1  # +1 for header row
            num_cols = 3  # No, Aktivitas, Deskripsi Kegiatan
            
            table_requests = [
                {
                    'insertTable': {
                        'rows': num_rows,
                        'columns': num_cols,
                        'location': {'index': table_insert_index}
                    }
                }
            ]
            
            service.documents().batchUpdate(documentId=file_id, body={'requests': table_requests}).execute()
            
            # C. Re-fetch doc to get table cell indices
            document = service.documents().get(documentId=file_id).execute()
            doc_content = document.get('body').get('content')
            
            # Find the table we just inserted (it should be near table_insert_index)
            new_table = None
            new_table_start = -1
            new_table_end = -1
            for element in doc_content:
                if 'table' in element and element.get('startIndex', 0) >= table_insert_index:
                    new_table = element.get('table')
                    new_table_start = element.get('startIndex')
                    new_table_end = element.get('endIndex')
                    break
            
            if not new_table:
                logging.error(f"[Google Doc Sync] Could not find inserted table for {month_key}")
                continue
            
            # D. Fill table cells with text
            def get_insert_idx(cell):
                content = cell.get('content', [])
                if content:
                    return content[0].get('startIndex')
                return cell.get('startIndex') + 1
            
            text_requests = []
            table_rows = new_table.get('tableRows')
            
            # Header row (row 0)
            if len(table_rows) > 0:
                header_cells = table_rows[0].get('tableCells')
                header_texts = ['No', 'Aktivitas', 'Deskripsi Kegiatan']
                for col_idx, h_text in enumerate(header_texts):
                    if col_idx < len(header_cells):
                        idx = get_insert_idx(header_cells[col_idx])
                        text_requests.append({
                            'insertText': {
                                'location': {'index': idx},
                                'text': h_text
                            }
                        })
            
            # Data rows
            for i, entry in enumerate(month_entries):
                row_idx = i + 1
                if row_idx >= len(table_rows):
                    break
                
                row = table_rows[row_idx]
                cells = row.get('tableCells')
                
                # Col 0: No
                if len(cells) > 0:
                    text_requests.append({
                        'insertText': {
                            'location': {'index': get_insert_idx(cells[0])},
                            'text': str(i + 1)
                        }
                    })
                
                # Col 1: Aktivitas (with date dd/mm)
                if len(cells) > 1:
                    try:
                        tgl = entry['tanggal']
                        if isinstance(tgl, str):
                            tgl = datetime.strptime(tgl, '%Y-%m-%d')
                        tgl_str = tgl.strftime('%d/%m')
                    except:
                        tgl_str = str(entry['tanggal'])
                    
                    aktiv_text = f"[{tgl_str}] {entry['aktivitas']}"
                    text_requests.append({
                        'insertText': {
                            'location': {'index': get_insert_idx(cells[1])},
                            'text': aktiv_text
                        }
                    })
                
                # Col 2: Deskripsi
                if len(cells) > 2:
                    desc = clean_html(entry['deskripsi'])
                    text_requests.append({
                        'insertText': {
                            'location': {'index': get_insert_idx(cells[2])},
                            'text': desc
                        }
                    })
            
            # Sort by index descending to avoid shifting issues
            text_requests.sort(key=lambda req: req['insertText']['location']['index'], reverse=True)
            
            if text_requests:
                service.documents().batchUpdate(documentId=file_id, body={'requests': text_requests}).execute()
            
            # E. Style all table cells: center-align, bold header, set font
            # Re-fetch to get updated indices
            document = service.documents().get(documentId=file_id).execute()
            doc_content = document.get('body').get('content')
            
            # Find table again for styling
            for element in doc_content:
                if 'table' in element and element.get('startIndex', 0) >= table_insert_index:
                    styled_table = element.get('table')
                    if styled_table:
                        style_requests = []
                        all_rows = styled_table.get('tableRows', [])
                        
                        for row_idx, row in enumerate(all_rows):
                            for cell in row.get('tableCells', []):
                                cell_content = cell.get('content', [])
                                if cell_content:
                                    c_start = cell_content[0].get('startIndex', 0)
                                    c_end = cell_content[-1].get('endIndex', c_start + 1)
                                    
                                    # Center-align all cells
                                    style_requests.append({
                                        'updateParagraphStyle': {
                                            'range': {'startIndex': c_start, 'endIndex': c_end},
                                            'paragraphStyle': {'alignment': 'CENTER'},
                                            'fields': 'alignment'
                                        }
                                    })
                                    
                                    # Set base text style (black, 11pt, no underline)
                                    style_requests.append({
                                        'updateTextStyle': {
                                            'range': {'startIndex': c_start, 'endIndex': c_end - 1},
                                            'textStyle': {
                                                'fontSize': {'magnitude': 11, 'unit': 'PT'},
                                                'foregroundColor': {
                                                    'color': {
                                                        'rgbColor': {'red': 0.0, 'green': 0.0, 'blue': 0.0}
                                                    }
                                                },
                                                'underline': False
                                            },
                                            'fields': 'fontSize,foregroundColor,underline'
                                        }
                                    })
                                    
                                    # Bold header row (row 0) only
                                    if row_idx == 0:
                                        style_requests.append({
                                            'updateTextStyle': {
                                                'range': {'startIndex': c_start, 'endIndex': c_end - 1},
                                                'textStyle': {'bold': True},
                                                'fields': 'bold'
                                            }
                                        })
                        
                        if style_requests:
                            service.documents().batchUpdate(documentId=file_id, body={'requests': style_requests}).execute()
                    break
            
            # F. Insert signature block after table
            document = service.documents().get(documentId=file_id).execute()
            doc_content = document.get('body').get('content')
            sig_insert_index = doc_content[-1].get('endIndex', 1) - 1
            
            # Match screenshot format:
            # "Disetujui Oleh" (bold, right-aligned)
            # [empty space for signature]
            # "Tanda Tangan Mentor" (bold, right-aligned)
            # "{nama_mentor}" (bold + RED, right-aligned)
            sig_text = f"Disetujui Oleh\n\nTanda Tangan Mentor\n\n\n\n{nama_mentor}\n\n"
            
            sig_requests = [
                {
                    'insertText': {
                        'location': {'index': sig_insert_index},
                        'text': sig_text
                    }
                },
                # Set all signature text to NORMAL_TEXT + right-aligned
                {
                    'updateParagraphStyle': {
                        'range': {
                            'startIndex': sig_insert_index,
                            'endIndex': sig_insert_index + len(sig_text)
                        },
                        'paragraphStyle': {
                            'namedStyleType': 'NORMAL_TEXT',
                            'alignment': 'END'
                        },
                        'fields': 'namedStyleType,alignment'
                    }
                },
                # Ensure all signature text is black first
                {
                    'updateTextStyle': {
                        'range': {
                            'startIndex': sig_insert_index,
                            'endIndex': sig_insert_index + len(sig_text)
                        },
                        'textStyle': {
                            'foregroundColor': {
                                'color': {
                                    'rgbColor': {'red': 0.0, 'green': 0.0, 'blue': 0.0}
                                }
                            },
                            'fontSize': {'magnitude': 11, 'unit': 'PT'},
                            'bold': False
                        },
                        'fields': 'foregroundColor,fontSize,bold'
                    }
                },
                # Bold "Disetujui Oleh"
                {
                    'updateTextStyle': {
                        'range': {
                            'startIndex': sig_insert_index,
                            'endIndex': sig_insert_index + len('Disetujui Oleh')
                        },
                        'textStyle': {'bold': True},
                        'fields': 'bold'
                    }
                },
            ]
            
            # Bold "Tanda Tangan Mentor"
            ttm_text = 'Tanda Tangan Mentor'
            ttm_offset = sig_text.find(ttm_text)
            if ttm_offset >= 0:
                sig_requests.append({
                    'updateTextStyle': {
                        'range': {
                            'startIndex': sig_insert_index + ttm_offset,
                            'endIndex': sig_insert_index + ttm_offset + len(ttm_text)
                        },
                        'textStyle': {'bold': True},
                        'fields': 'bold'
                    }
                })
            
            # Bold + RED for mentor name
            mentor_offset = sig_text.find(nama_mentor)
            if mentor_offset >= 0:
                sig_requests.append({
                    'updateTextStyle': {
                        'range': {
                            'startIndex': sig_insert_index + mentor_offset,
                            'endIndex': sig_insert_index + mentor_offset + len(nama_mentor)
                        },
                        'textStyle': {
                            'bold': True,
                            'foregroundColor': {
                                'color': {
                                    'rgbColor': {'red': 0.8, 'green': 0.0, 'blue': 0.0}
                                }
                            }
                        },
                        'fields': 'bold,foregroundColor'
                    }
                })
            
            service.documents().batchUpdate(documentId=file_id, body={'requests': sig_requests}).execute()

        return jsonify({'success': True, 'message': f'Berhasil mengekspor {len(entries)} kegiatan ({len(month_keys)} bulan) ke Google Doc.'})

    except Exception as e:
        logging.error(f"[Google Doc Sync] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500