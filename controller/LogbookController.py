import os
import io
from werkzeug.utils import secure_filename
from PIL import Image
from docx import Document
import time
import re
import html
from docx.shared import Inches
from flask import send_file
from connection import get_connection
from docx.enum.text import WD_ALIGN_PARAGRAPH # Tambahkan ini di bagian atas file import lu
import bleach

# UPLOAD_FOLDER = os.path.join('static', 'uploads', 'logbook')
# os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_TAGS = [
    'p', 'ul', 'ol', 'li', 'strong', 'em', 'u', 'h1', 'h2', 'h3', 'br'
]
def compress_and_save_image(image_file, nim, entry_id):
    if not image_file or image_file.filename == '':
        return None
        
    original_filename = secure_filename(image_file.filename)
    
    # Kita cuma butuh ekstensinya aja (misal: ".jpg" atau ".png")
    _, ext = os.path.splitext(original_filename)
    
    # Format baru sesuai request lu: {nim}Image_{entry_id}_{timestamp}{ext}
    # Contoh hasil: 23410100003Image_45_1708150000.jpg
    timestamp = int(time.time() * 1000)
    filename = f"{nim}img_{entry_id}_{timestamp}{ext}"
    
    # Bikin struktur folder dinamis
    nim_folder = os.path.join('static', 'uploads', 'logbook', str(nim), 'imgs')
    os.makedirs(nim_folder, exist_ok=True)
    
    filepath = os.path.join(nim_folder, filename)
    
    img = Image.open(image_file)
    if img.mode in ("RGBA", "P"): 
        img = img.convert("RGB")
    img.thumbnail((800, 800))
    img.save(filepath, optimize=True, quality=60)
    
    # Return path relatif untuk disimpan ke DB
    return f"{nim}/imgs/{filename}"
def clean_html_for_word(html_text):
    """Fungsi sakti merubah HTML Tiptap jadi teks rapi buat Word"""
    if not html_text: return ""
    
    # Ubah list item <li> jadi format bullet
    text = re.sub(r'<li>', r'- ', html_text)
    # Ganti tag akhir paragraf/list jadi baris baru (enter)
    text = re.sub(r'</p>|<br>|</li>|</ul>|</ol>', r'\n', text)
    # Hapus semua tag HTML yang tersisa
    text = re.sub(r'<[^>]+>', '', text)
    # Decode simbol (kayak &amp; jadi &)
    text = html.unescape(text)
    
    # Hapus enter berlebih
    return re.sub(r'\n{3,}', '\n\n', text).strip()
# --- CRUD SETUP LOGBOOK ---
def get_logbooks_by_user(user_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    # Filter berdasarkan user_id
    cursor.execute("SELECT * FROM logbooks WHERE user_id = %s ORDER BY id DESC", (user_id,))
    logbooks = cursor.fetchall()
    conn.close()
    return logbooks

def get_logbook_by_id_and_user(id, user_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM logbooks WHERE id = %s AND user_id = %s", (id, user_id))
    logbook = cursor.fetchone()
    conn.close()
    return logbook

def create_logbook(user_id, data):
    conn = get_connection()
    cursor = conn.cursor()
    query = """
    INSERT INTO logbooks (user_id, fakultas, prodi, nama, nim, nama_mitra, waktu_mulai, waktu_selesai, posisi_magang, nama_mentor, wa_mentor, email_mentor)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    val = (user_id, data['fakultas'], data['prodi'], data['nama'], data['nim'], data['nama_mitra'], data['waktu_mulai'], data['waktu_selesai'], data['posisi_magang'], data['nama_mentor'], data['wa_mentor'], data['email_mentor'])
    cursor.execute(query, val)
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return new_id

def update_logbook(id, data, user_id):
    conn = get_connection()
    cursor = conn.cursor()
    # Tambahin filter AND user_id = %s biar aman
    query = """
    UPDATE logbooks SET 
    fakultas=%s, prodi=%s, nama=%s, nim=%s, nama_mitra=%s, 
    waktu_mulai=%s, waktu_selesai=%s, posisi_magang=%s, 
    nama_mentor=%s, wa_mentor=%s, email_mentor=%s 
    WHERE id = %s AND user_id = %s
    """
    val = (
        data['fakultas'], data['prodi'], data['nama'], data['nim'], 
        data['nama_mitra'], data['waktu_mulai'], data['waktu_selesai'], 
        data['posisi_magang'], data['nama_mentor'], data['wa_mentor'], 
        data['email_mentor'], id, user_id
    )
    cursor.execute(query, val)
    conn.commit()
    conn.close()

def delete_logbook(id, user_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    # 1. Pastikan logbooknya ada dan milik user tersebut, sekaligus ambil nim-nya
    cursor.execute("SELECT nim FROM logbooks WHERE id = %s AND user_id = %s", (id, user_id))
    logbook = cursor.fetchone()
    
    if logbook:
        nim = logbook['nim']
        
        # 2. Ambil semua entri yang punya gambar di logbook ini
        cursor.execute("SELECT gambar FROM logbook_entries WHERE logbook_id = %s", (id,))
        entries = cursor.fetchall()
        
        # 3. Hapus file gambarnya satu per satu secara fisik
        for entry in entries:
            if entry['gambar']:
                file_path = os.path.join('static', 'uploads', 'logbook', entry['gambar'])
                if os.path.exists(file_path):
                    os.remove(file_path)
                    
        # 4. Hapus logbook dari database 
        # (Data di logbook_entries otomatis terhapus kalau lu pakai relasi ON DELETE CASCADE di SQL-nya)
        cursor.execute("DELETE FROM logbooks WHERE id = %s AND user_id = %s", (id, user_id))
        conn.commit()
        
        # 5. BERSIH-BERSIH FOLDER (Hanya dihapus JIKA KOSONG)
        try:
            img_dir = os.path.join('static', 'uploads', 'logbook', str(nim), 'imgs')
            base_dir = os.path.join('static', 'uploads', 'logbook', str(nim))
            
            # os.rmdir hanya akan menghapus folder jika isinya benar-benar kosong
            if os.path.exists(img_dir) and not os.listdir(img_dir):
                os.rmdir(img_dir)
            if os.path.exists(base_dir) and not os.listdir(base_dir):
                os.rmdir(base_dir)
        except OSError:
            # Abaikan jika error (berarti foldernya masih ada isinya dari logbook lain)
            pass

    conn.close()

# --- CRUD ENTRIES (KEGIATAN HARIAN) ---
def get_entries_by_logbook(logbook_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    # 1. Ambil semua entri logbook
    cursor.execute("SELECT * FROM logbook_entries WHERE logbook_id = %s ORDER BY tanggal ASC", (logbook_id,))
    entries = cursor.fetchall()
    
    # 2. Iterasi untuk setiap entri guna mengambil gambar dan memformat tanggal
    for entry in entries:
        # Format tanggal display dd-mm-yyyy
        if entry['tanggal']:
            entry['tanggal_display'] = entry['tanggal'].strftime('%d-%m-%Y')
        else:
            entry['tanggal_display'] = '-'
            
        # Ambil semua gambar yang terkait dengan entri ini dari tabel logbook_images
        cursor.execute("SELECT path FROM logbook_images WHERE entry_id = %s", (entry['id'],))
        entry['images'] = cursor.fetchall() # Berisi list of dict, misal: [{'path': '...'}, {'path': '...'}]
        
    conn.close()
    return entries

def add_entry(logbook_id, form_data, files):
    aktivitas = form_data.get('aktivitas')
    deskripsi_raw = form_data.get('deskripsi')

    # SANITASI: Bersihkan HTML dari karakter berbahaya sebelum masuk DB
    deskripsi_clean = bleach.clean(deskripsi_raw, tags=ALLOWED_TAGS, strip=True)
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT nim FROM logbooks WHERE id = %s", (logbook_id,))
    nim = cursor.fetchone()['nim']
    
    # Simpan data aktivitas dulu
    cursor.execute(
        "INSERT INTO logbook_entries (logbook_id, tanggal, aktivitas, deskripsi) VALUES (%s, %s, %s, %s)",
        (logbook_id, form_data.get('tanggal'), aktivitas, deskripsi_clean)
    )
    entry_id = cursor.lastrowid
    
    # Ambil list gambar dari request.files.getlist()
    images = files.getlist('gambar')
    for img in images:
        if img and img.filename != '':
            path = compress_and_save_image(img, nim) # Fungsi kompres yg lama tetep kepake
            cursor.execute("INSERT INTO logbook_images (entry_id, path) VALUES (%s, %s)", (entry_id, path))
            
    conn.commit()
    conn.close()

def delete_entry(entry_id, logbook_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Ambil semua path gambar
    cursor.execute("SELECT id FROM logbook_entries WHERE id = %s AND logbook_id = %s", (entry_id, logbook_id))
    if not cursor.fetchone():
        conn.close()
        return False # Tolak jika hacker mencoba manipulasi URL
    images = cursor.fetchall()
    
    for img in images:
        file_path = os.path.join('static', 'uploads', 'logbook', img['path'])
        if os.path.exists(file_path):
            os.remove(file_path)
            
    cursor.execute("DELETE FROM logbook_entries WHERE id = %s", (entry_id,))
    conn.commit()
    conn.close()
    
def get_entry_by_id(entry_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Ambil data teks entri
    cursor.execute("SELECT * FROM logbook_entries WHERE id = %s", (entry_id,))
    entry = cursor.fetchone()
    
    if entry:
        # Format tanggal biar rapi di form edit
        if entry['tanggal']:
            entry['tanggal_display'] = entry['tanggal'].strftime('%d-%m-%Y')
            
        # Ambil list gambar dari tabel logbook_images
        cursor.execute("SELECT path FROM logbook_images WHERE entry_id = %s", (entry_id,))
        entry['images'] = cursor.fetchall()
        
    conn.close()
    return entry

def update_entry(entry_id, form_data, files):
    aktivitas = form_data.get('aktivitas')
    deskripsi_raw = form_data.get('deskripsi')

    # SANITASI: Bersihkan HTML dari karakter berbahaya sebelum masuk DB
    deskripsi_clean = bleach.clean(deskripsi_raw, tags=ALLOWED_TAGS, strip=True)
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Ambil data NIM
    cursor.execute("""
        SELECT l.nim, e.id as entry_id 
        FROM logbook_entries e 
        JOIN logbooks l ON e.logbook_id = l.id 
        WHERE e.id = %s
    """, (entry_id,))
    row = cursor.fetchone()
    nim = row['nim'] if row else 'unknown_nim'

    # 1. Update data teks terlebih dahulu
    cursor.execute(
        "UPDATE logbook_entries SET tanggal=%s, aktivitas=%s, deskripsi=%s WHERE id=%s",
        (form_data.get('tanggal'), aktivitas, deskripsi_clean, entry_id)
    )

    # --- LOGIKA MULTIPLE GAMBAR YANG BENAR ---
    # Ambil array path gambar yang TIDAK DIHAPUS oleh user di form HTML
    retained_paths = form_data.getlist('existing_images') 
    new_images = files.getlist('gambar')

    # Ambil semua gambar lama dari database
    cursor.execute("SELECT path FROM logbook_images WHERE entry_id = %s", (entry_id,))
    old_images = cursor.fetchall()

    # A. Bandingkan dan hapus gambar yang disilang (X) oleh user
    for old_img in old_images:
        if old_img['path'] not in retained_paths:
            # Hapus file fisik dari HDD
            old_path = os.path.join('static', 'uploads', 'logbook', old_img['path'])
            if os.path.exists(old_path):
                os.remove(old_path)
            # Hapus dari tabel
            cursor.execute("DELETE FROM logbook_images WHERE entry_id = %s AND path = %s", (entry_id, old_img['path']))

    # B. Tambahkan gambar baru hasil crop (jika ada)
    for img in new_images:
            if img and img.filename != '':
                # Tambahkan entry_id di sini
                new_path = compress_and_save_image(img, nim, entry_id)
                cursor.execute(
                    "INSERT INTO logbook_images (entry_id, path) VALUES (%s, %s)",
                    (entry_id, new_path)
                )

    conn.commit()
    conn.close()

# --- GENERATE WORD ---
# Tambahin parameter user_id biar pas diconvert dicek dulu ownershipnya
def generate_word(logbook_id, user_id): 
    logbook = get_logbook_by_id_and_user(logbook_id, user_id) 
    entries = get_entries_by_logbook(logbook_id)

    if not logbook:
        return None 

    doc = Document()
    
    # 1. Judul Utama
    doc.add_heading('Log Book Bulanan Dinamika Industrial Internship', 0)

    # 2. Tabel Identitas (Tanpa Border)
    if logbook:
        # ... (Kode identitas tetap sama seperti sebelumnya) ...
        # [Bagian ini dilewati untuk mempersingkat jawaban]
        start = logbook['waktu_mulai']
        end = logbook['waktu_selesai']
        start_str = start.strftime('%d-%m-%Y') if hasattr(start, 'strftime') else str(start)
        end_str = end.strftime('%d-%m-%Y') if hasattr(end, 'strftime') else str(end)
        identitas = [
            ("Fakultas", ":", logbook.get('fakultas', '-')),
            ("Prodi", ":", logbook.get('prodi', '-')),
            ("Nama", ":", logbook.get('nama', '-')),
            ("Nim", ":", logbook.get('nim', '-')),
            ("Nama Mitra", ":", logbook.get('nama_mitra', '-')),
            ("Waktu Pelaksanaan", ":", f"{start_str} sampai {end_str}"),
            ("Posisi Magang", ":", logbook.get('posisi_magang', '-')),
            ("Nama Mentor", ":", logbook.get('nama_mentor', '-')),
            ("Whatsapp Mentor", ":", logbook.get('wa_mentor', '-')),
            ("Email Mentor", ":", logbook.get('email_mentor', '-'))
        ]
        id_table = doc.add_table(rows=0, cols=3)
        for label, sep, val in identitas:
            row_cells = id_table.add_row().cells
            row_cells[0].text = label
            row_cells[1].text = sep
            row_cells[2].text = str(val)
            row_cells[0].width = Inches(1.5)
            row_cells[1].width = Inches(0.2)
            row_cells[2].width = Inches(4.3)

    # 3. Pengelompokan Kegiatan Berdasarkan Bulan
    months_id = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']
    grouped_entries = {}
    for entry in entries:
        tgl = entry['tanggal']
        month_key = f"{months_id[tgl.month]} {tgl.year}" if tgl else "Belum Diketahui"
        month_only = months_id[tgl.month] if tgl else ""
        if month_key not in grouped_entries:
            grouped_entries[month_key] = {'month_only': month_only, 'data': []}
        grouped_entries[month_key]['data'].append(entry)

    # --- TAMBAHAN: Buka koneksi database untuk ambil gambar ---
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # 4. Render Logbook Per Bulan
    for month_key, group in grouped_entries.items():
        doc.add_paragraph() 
        doc.add_heading(f'Aktivitas Bulan {month_key}', level=2)
        
        table = doc.add_table(rows=1, cols=3)
        table.style = 'Table Grid'
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = 'No'
        hdr_cells[1].text = 'Aktivitas'
        hdr_cells[2].text = 'Deskripsi Kegiatan'
        
        hdr_cells[0].width = Inches(0.5)
        hdr_cells[1].width = Inches(2.0)
        hdr_cells[2].width = Inches(4.0)

        # Isi Tabel
        for idx, entry in enumerate(group['data'], start=1):
            row_cells = table.add_row().cells
            row_cells[0].text = str(idx)
            
            tgl_str = entry['tanggal'].strftime('%d-%m-%Y') if entry['tanggal'] else '-'
            row_cells[1].text = f"{tgl_str}\n{entry['aktivitas']}"
            
            p = row_cells[2].paragraphs[0]
            clean_deskripsi = clean_html_for_word(entry['deskripsi'])
            p.add_run(clean_deskripsi + "\n")
            
            # --- MODIFIKASI: AMBIL MULTIPLE GAMBAR DARI DATABASE ---
            cursor.execute("SELECT path FROM logbook_images WHERE entry_id = %s", (entry['id'],))
            db_images = cursor.fetchall()

            for img in db_images:
                img_path = os.path.join('static', 'uploads', 'logbook', img['path'])
                if os.path.exists(img_path):
                    # Menambahkan gambar ke dalam sel kolom "Deskripsi Kegiatan"
                    doc_p = row_cells[2].add_paragraph()
                    doc_p.add_run().add_picture(img_path, width=Inches(2.5))
            
        doc.add_paragraph() 
        
        # 5. Tambahkan Format Resume & Tanda Tangan
        month_name = group['month_only']
        if month_name:
            doc.add_heading(f'Resume Kegiatan Bulan {month_name}:', level=3)
            doc.add_paragraph("...\n\n") 
        
        sig_p = doc.add_paragraph()
        sig_p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        sig_p.add_run("Disetujui Oleh\n")
        sig_p.add_run("Tanda Tangan Mentor\n\n\n\n")
        sig_p.add_run(f"{logbook.get('nama_mentor', 'Nama Mentor')}").bold = True

    # Tutup koneksi setelah selesai looping
    cursor.close()
    conn.close()

    # Save to Stream
    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    current_time = int(time.time())
    
    return send_file(
        file_stream, 
        as_attachment=True, 
        download_name=f"Logbook_{logbook['nim']}_{current_time}.docx",
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )