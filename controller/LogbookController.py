import os
import io
from werkzeug.utils import secure_filename
from PIL import Image
from docx import Document
from docx.shared import Inches
from flask import send_file
from connection import get_connection
from docx.enum.text import WD_ALIGN_PARAGRAPH # Tambahkan ini di bagian atas file import lu

# UPLOAD_FOLDER = os.path.join('static', 'uploads', 'logbook')
# os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def compress_and_save_image(image_file, nim):
    if not image_file or image_file.filename == '':
        return None
        
    filename = secure_filename(image_file.filename)
    
    # Bikin struktur folder dinamis: static/uploads/logbook/{nim}/imgs
    nim_folder = os.path.join('static', 'uploads', 'logbook', str(nim), 'imgs')
    os.makedirs(nim_folder, exist_ok=True)
    
    filepath = os.path.join(nim_folder, filename)
    
    img = Image.open(image_file)
    if img.mode in ("RGBA", "P"): 
        img = img.convert("RGB")
    img.thumbnail((800, 800))
    img.save(filepath, optimize=True, quality=60)
    
    # Return path relatif untuk disimpan ke DB (misal: 23410100003/imgs/bukti.jpg)
    return f"{nim}/imgs/{filename}"

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
    cursor.execute("SELECT * FROM logbook_entries WHERE logbook_id = %s ORDER BY tanggal ASC", (logbook_id,))
    entries = cursor.fetchall()
    conn.close()
    for entry in entries:
        if entry['tanggal']:
            # strftime akan mengubah format YYYY-MM-DD ke DD-MM-YYYY
            entry['tanggal_display'] = entry['tanggal'].strftime('%d-%m-%Y')
        else:
            entry['tanggal_display'] = '-'
    return entries

def add_entry(logbook_id, data, files):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Ambil data nim dari logbook_id
    cursor.execute("SELECT nim FROM logbooks WHERE id = %s", (logbook_id,))
    logbook = cursor.fetchone()
    nim = logbook['nim'] if logbook else 'unknown_nim'
    
    # Proses kompresi dan save gambar (lempar nim ke fungsi)
    filename = compress_and_save_image(files.get('gambar'), nim)
    
    cursor.execute(
        "INSERT INTO logbook_entries (logbook_id, tanggal, aktivitas, deskripsi, gambar) VALUES (%s, %s, %s, %s, %s)",
        (logbook_id, data['tanggal'], data['aktivitas'], data['deskripsi'], filename)
    )
    conn.commit()
    conn.close()

def delete_entry(entry_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT gambar FROM logbook_entries WHERE id = %s", (entry_id,))
    entry = cursor.fetchone()
    
    if entry and entry['gambar']:
        file_path = os.path.join('static', 'uploads', 'logbook', entry['gambar'])
        if os.path.exists(file_path):
            os.remove(file_path)

    cursor.execute("DELETE FROM logbook_entries WHERE id = %s", (entry_id,))
    conn.commit()
    conn.close()
    
def get_entry_by_id(entry_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM logbook_entries WHERE id = %s", (entry_id,))
    entry = cursor.fetchone()
    conn.close()
    return entry

def update_entry(entry_id, data, files):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    image_file = files.get('gambar')
    
    # Ambil sinyal hapus dari input hidden HTML
    hapus_lama = data.get('hapus_gambar_lama') == '1'
    
    # Kalau ada gambar baru ATAU user minta hapus gambar lama
    if (image_file and image_file.filename != '') or hapus_lama:
        
        # 1. Cari data gambar lama & nim untuk dihapus fisiknya
        cursor.execute("SELECT l.nim, e.gambar FROM logbook_entries e JOIN logbooks l ON e.logbook_id = l.id WHERE e.id = %s", (entry_id,))
        row = cursor.fetchone()
        nim = row['nim'] if row else 'unknown_nim'
        
        # Hapus file fisik lama
        if row and row['gambar']:
            old_path = os.path.join('static', 'uploads', 'logbook', row['gambar'])
            if os.path.exists(old_path):
                os.remove(old_path)

        # 2. Jika ada gambar baru, simpan dan update DB
        if image_file and image_file.filename != '':
            filename = compress_and_save_image(image_file, nim)
            cursor.execute(
                "UPDATE logbook_entries SET tanggal=%s, aktivitas=%s, deskripsi=%s, gambar=%s WHERE id=%s",
                (data['tanggal'], data['aktivitas'], data['deskripsi'], filename, entry_id)
            )
        # 3. Jika cuma minta hapus gambar (tanpa gambar baru), set NULL di DB
        elif hapus_lama:
            cursor.execute(
                "UPDATE logbook_entries SET tanggal=%s, aktivitas=%s, deskripsi=%s, gambar=NULL WHERE id=%s",
                (data['tanggal'], data['aktivitas'], data['deskripsi'], entry_id)
            )
    else:
        # Jika gak ngotak-ngatik gambar sama sekali
        cursor.execute(
            "UPDATE logbook_entries SET tanggal=%s, aktivitas=%s, deskripsi=%s WHERE id=%s",
            (data['tanggal'], data['aktivitas'], data['deskripsi'], entry_id)
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
        # Format tanggal pelaksanaan
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
            # Set lebar kolom identitas biar rapi
            row_cells[0].width = Inches(1.5)
            row_cells[1].width = Inches(0.2)
            row_cells[2].width = Inches(4.3)

    # 3. Pengelompokan Kegiatan Berdasarkan Bulan
    months_id = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']
    
    grouped_entries = {}
    for entry in entries:
        tgl = entry['tanggal'] # Asumsi ini tipe datetime.date
        if tgl:
            month_key = f"{months_id[tgl.month]} {tgl.year}"
            month_only = months_id[tgl.month]
        else:
            month_key = "Belum Diketahui"
            month_only = ""
            
        if month_key not in grouped_entries:
            grouped_entries[month_key] = {'month_only': month_only, 'data': []}
            
        grouped_entries[month_key]['data'].append(entry)

    # 4. Render Logbook Per Bulan
    for month_key, group in grouped_entries.items():
        doc.add_paragraph() # Spacing
        
        # Sub Judul Bulan
        doc.add_heading(f'Aktivitas Bulan {month_key}', level=2)
        
        # Buat Tabel Kegiatan (3 Kolom sesuai docx)
        table = doc.add_table(rows=1, cols=3)
        table.style = 'Table Grid'
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = 'No'
        hdr_cells[1].text = 'Aktivitas'
        hdr_cells[2].text = 'Deskripsi Kegiatan'
        
        # Lebar Kolom
        hdr_cells[0].width = Inches(0.5)
        hdr_cells[1].width = Inches(2.0)
        hdr_cells[2].width = Inches(4.0)

        # Isi Tabel
        for idx, entry in enumerate(group['data'], start=1):
            row_cells = table.add_row().cells
            row_cells[0].text = str(idx)
            
            # Gabungkan Tanggal ke Kolom Aktivitas karena formatnya cuma 3 kolom
            tgl_str = entry['tanggal'].strftime('%d-%m-%Y') if entry['tanggal'] else '-'
            row_cells[1].text = f"{tgl_str}\n{entry['aktivitas']}"
            
            p = row_cells[2].paragraphs[0]
            p.add_run(entry['deskripsi'] + "\n")
            
            # Bukti Gambar
            if entry['gambar']:
                img_path = os.path.join('static', 'uploads', 'logbook', entry['gambar'])
                if os.path.exists(img_path):
                    row_cells[2].add_paragraph().add_run().add_picture(img_path, width=Inches(2.5))
            
        doc.add_paragraph() # Spacing
        
        # 5. Tambahkan Format Resume & Tanda Tangan Mentor di Bawah Tabel
        month_name = group['month_only']
        if month_name:
            doc.add_heading(f'Resume Kegiatan Bulan {month_name}:', level=3)
            doc.add_paragraph("...\n\n") # Placeholder agar lu bisa ngetik bebas di Word
        
        # Bikin Layout Tanda Tangan Rata Tengah di Sebelah Kanan/Bawah
        sig_p = doc.add_paragraph()
        sig_p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        sig_p.add_run("Disetujui Oleh\n")
        sig_p.add_run("Tanda Tangan Mentor\n\n\n\n")
        sig_p.add_run(f"{logbook.get('nama_mentor', 'Nama Mentor')}").bold = True

    # Save to Stream
    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    
    return send_file(
        file_stream, 
        as_attachment=True, 
        download_name=f"Logbook_Magang_{logbook['nim']}.docx",
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )