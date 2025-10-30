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
from flask import Blueprint


# Impor SEMUA fungsi scraper
from scrapper_requests import   search_mahasiswa, search_staff, get_session_status, fetch_photo_from_sicyca  
# from app import photo_cache, majorID, executor, JADWAL_STATUS, log_file, _valid_role
api_bp = Blueprint('api', __name__)


# variabel global untuk diinject
photo_cache = None
majorID = None
executor = None
JADWAL_STATUS = None
log_file = None
_valid_role = None

def init_api(cache, major, execu, status, logfile, valid_role_func):
    global photo_cache, majorID, executor, JADWAL_STATUS, log_file, _valid_role
    photo_cache = cache
    majorID = major
    executor = execu
    JADWAL_STATUS = status
    log_file = logfile
    _valid_role = valid_role_func


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