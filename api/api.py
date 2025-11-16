from flask import request, Response, jsonify, Blueprint, current_app, send_from_directory, url_for
import json, yt_dlp, base64 , logging, os, uuid, urllib.parse
from middleware.auth_quard import login_required
from yt_dlp.utils import sanitize_filename


# Impor SEMUA fungsi scraper
from scrapper_requests import   search_mahasiswa, search_staff, get_session_status, fetch_photo_from_sicyca, fetch_data_ultah
# from app import photo_cache, majorID, executor, JADWAL_STATUS, log_file, _valid_role
api_bp = Blueprint('api', __name__)


# variabel global untuk diinject
photo_cache = None
majorID = None
executor = None
JADWAL_STATUS = None
log_file = None
_valid_role = None

# Fungsi untuk inisialisasi variabel global
def init_api(cache, major, execu, status, logfile, valid_role_func):
    global photo_cache, majorID, executor, JADWAL_STATUS, log_file, _valid_role
    photo_cache = cache
    majorID = major
    executor = execu
    JADWAL_STATUS = status
    log_file = logfile
    _valid_role = valid_role_func

# mengecek status koneksi Sicyca
@api_bp.route('/status_koneksi')
def api_status():
    if get_session_status():
        return jsonify({"status": "ready", "message": "Koneksi Sicyca aman."})
    else:
        return jsonify({"status": "error", "message": "Koneksi Sicyca gagal. Cookie mungkin tidak valid. Coba lakukan pencarian untuk login ulang."})

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
            prodi_name = majorID.get(nim[2:7], 'Prodi Tidak Dikenal') if nim and len(nim) >= 7 else 'Prodi Tidak Dikenal'
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
    ext_req = data.get('ext') # mp3, mkv, mp4, ...
    quality = data.get('quality') # e.g., "1080p", "720p", "best"
    
    if not url or not ext_req or not quality:
        return jsonify({"error": "URL, format, dan kualitas wajib diisi"}), 400
    
    temp_dir = current_app.config.get('TEMP_DOWNLOAD_DIR', '/app/temp_downloads')
    
    # 1. BIKIN NAMA FILE SESUAI PERMINTAAN LU
    # Ini nama file SEMENTARA di server
    unique_id = str(uuid.uuid4())
    temp_server_filename = f"{unique_id}.{ext_req}"
    temp_server_path = os.path.join(temp_dir, temp_server_filename)

    logging.info(f"Memulai konversi ke {ext_req} ({quality}) untuk {url}...")
    
    # 2. Siapkan Opsi yt-dlp
    ydl_opts = {
        'outtmpl': temp_server_path, 
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'postprocessors': [],
        'keepvideo': False, 
        'http_headers': {  # <-- TAMBAHKAN BLOK INI
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
        } 
    }

    # 3. Setting konversi berdasarkan permintaan
    
    # Format Kualitas (e.g., "1080p" -> "[height=1080]")
    quality_selector = ""
    if quality.endswith('p'):
        height = quality[:-1] # "1080p" -> "1080"
        quality_selector = f"[height={height}]"
    
    # Format yang diminta
    if ext_req in ['mp3', 'wav', 'webm_audio']: # webm_audio = webm audio-only
        if ext_req == 'webm_audio': ext_req = 'webm'
        
        # 'bestaudio' atau 'bestaudio[abr<=128]' dll
        audio_quality_selector = "bestaudio"
        if quality == 'medium':
            audio_quality_selector = "bestaudio[abr<=128]" # Contoh
        
        ydl_opts['format'] = audio_quality_selector
        if ext_req in ['mp3', 'wav']:
            ydl_opts['postprocessors'].append({
                'key': 'FFmpegExtractAudio',
                'preferredcodec': ext_req,
            })
    
    elif ext_req in ['mkv', 'mp4', 'mpeg', 'webm_video']: # webm_video = webm video
        if ext_req == 'webm_video': ext_req = 'webm'
        
        # Ini adalah format string yang nge-merge (kayak log CMD lu)
        ydl_opts['format'] = f"bestvideo{quality_selector}+bestaudio/best{quality_selector}"
        
        ydl_opts['postprocessors'].append({
            'key': 'FFmpegVideoConvertor',
            'preferedformat': ext_req,
        })
    else:
        return jsonify({"error": "Format tidak didukung"}), 400

    # 4. JALANKAN PROSES DOWNLOAD + KONVERSI (INI YANG LAMA!)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Kita 'download=False' dulu cuma buat ngambil 'title' dan 'id'
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'video_tanpa_judul')
            video_id = info.get('id', 'NA')
            sanitized_title = sanitize_filename(title)
            
            # 5. BIKIN NAMA FILE ASLI (SESUAI PERMINTAAN)
            download_as_filename = f"{sanitized_title} [{video_id}].{ext_req}"

            # 6. SEKARANG BARU KITA DOWNLOAD
            logging.info(f"Downloading and converting to {temp_server_filename}...")
            ydl.download([url])
            
            if not os.path.exists(temp_server_path):
                raise Exception(f"File hasil konversi {temp_server_filename} tidak ditemukan.")

            logging.info(f"Konversi selesai: {temp_server_filename}. Siap dikirim sebagai {download_as_filename}")
            
            # 7. Kirim JSON
            return jsonify({
                "success": True,
                "download_url": url_for('api.download_converted_file', filename=temp_server_filename),
                "download_as": download_as_filename
            })
            
    except Exception as e:
        logging.error(f"yt-dlp GAGAL (mungkin timeout atau CPU limit): {str(e)}")
        if os.path.exists(temp_server_path):
            os.remove(temp_server_path)
        return jsonify({"error": f"Konversi Gagal. Ini proses berat. ({str(e)})"}), 500

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
    try:
        return send_from_directory(temp_dir, filename, as_attachment=True)
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
    return jsonify(JADWAL_STATUS)

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