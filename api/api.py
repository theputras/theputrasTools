from flask import request, Response, jsonify, Blueprint, current_app, send_from_directory, url_for, stream_with_context, session
import json, yt_dlp, base64 , logging, os, uuid, urllib.parse, time, subprocess, re
from middleware.auth_quard import login_required
from yt_dlp.utils import sanitize_filename


# Impor SEMUA fungsi scraper
from scrapper_requests import   search_mahasiswa, search_staff, fetch_photo_from_sicyca, fetch_data_ultah, scrape_krs, scrape_krs_detail, fetch_masa_studi
from controller.GateController import get_session_status
# from app import photo_cache, majorID, executor, JADWAL_STATUS, log_file, _valid_role
api_bp = Blueprint('api', __name__)


# variabel global untuk diinject
photo_cache = None
majorID = None
executor = None
get_jadwal_status_func = None
log_file = None
_valid_role = None

# Fungsi untuk inisialisasi variabel global
def init_api(cache, major, execu, status_getter, logfile, valid_role_func):
    global photo_cache, majorID, executor, get_jadwal_status_func, log_file, _valid_role
    photo_cache = cache
    majorID = major
    executor = execu
    get_jadwal_status_func = status_getter
    log_file = logfile
    _valid_role = valid_role_func
    
    
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
@api_bp.route('/status_koneksi')
def api_status():
    # 1. Ambil user_id dari session flask yang sedang login
    user_id = session.get('user_id')
    
    # 2. Panggil fungsi dengan parameter user_id
    # Hasilnya sekarang berupa dict: {'active': True/False, 'message': '...'}
    status_result = get_session_status(user_id)
    
    # 3. Cek key 'active' dari dictionary result
    if status_result.get('active'):
        return jsonify({"status": "ready", "message": "Koneksi Sicyca aman."})
    else:
        return jsonify({
            "status": "error", 
            "message": "Koneksi Sicyca gagal atau User belum login. Coba refresh halaman atau login ulang."
        })

# Untuk mencari mahasiswa atau staff
@api_bp.route('/search', methods=['POST'])
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
                'Nama': row.get('Nama'),
                'IDMhs': nim,
                'Status': row.get('Status'),
                'Prodi': prodi_name,
                'Detail': row.get('Dosen Wali')
            })
    if not df_staff.empty:
        for _, row in df_staff.iterrows():
            combined_results.append({
                'Tipe': 'Staff/Dosen',
                'Nama': row.get('Nama'),
                'IDStaff': row.get('NIK'),
                'Bagian': row.get('Bagian'),
                'Detail': row.get('Email')
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
                <dt class="font-medium text-gray-400">NIK</dt><dd class="col-span-2 text-white">{item['IDStaff']}</dd>
                <dt class="font-medium text-gray-400">Bagian</dt><dd class="col-span-2 text-white">{item['Bagian']}</dd>
                <dt class="font-medium text-gray-400">Email</dt><dd class="col-span-2 text-white">{item['Detail']}</dd>
                <!-- Tombol di bawah Email -->
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
        <dl class="grid grid-cols-3 gap-2 text-sm">{detail_html}</dl>
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
        return jsonify({"error": f"Terjadi kesalahan internal: {str(e)}"}), 500
        
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
             download_progress[task_id] = {"status": "Error", "message": str(e)}
             # Jangan langsung dihapus biar frontend bisa baca errornya sebentar
        logging.error(f"Konversi gagal: {str(e)}")
        return jsonify({"error": str(e)}), 500

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
            "message": f"Terjadi kesalahan server: {str(e)}",
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