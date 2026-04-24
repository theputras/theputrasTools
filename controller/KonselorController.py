# controller/KonselorController.py
# Controller untuk fitur Pencatatan Sesi Konseling
# NIM disimpan mentah, nama disensor saat display

import logging
from models.konselor import (
    kategori_masalah_model,
    jenis_layanan_model,
    konselor_session_model,
    tindak_lanjut_model
)


def censor_name(nama):
    """
    Sensor nama mahasiswa untuk ditampilkan di frontend.
    Option B: karakter pertama tiap kata tetap, sisanya '*'
    Contoh: "BUDI SANTOSO" → "B*** S******"
    """
    if not nama:
        return "-"
    words = nama.strip().split()
    censored = []
    for word in words:
        if len(word) <= 1:
            censored.append(word)
        else:
            censored.append(word[0] + '*' * (len(word) - 1))
    return ' '.join(censored)


def create_sesi(konselor_user_id, form_data):
    """
    Proses pembuatan sesi baru:
    1. Validasi input
    2. Simpan NIM mentah, nama (plain text), dosen wali ke database
    """
    # 1. Validasi
    nim_raw = form_data.get('nim', '').strip()
    nama = form_data.get('nama', '').strip()
    dosen_wali = form_data.get('dosen_wali', '').strip()
    prodi = form_data.get('prodi', '').strip()
    jenis_layanan_id = form_data.get('jenis_layanan_id')
    kategori_masalah_ids_str = form_data.get('kategori_masalah_ids', '[]')
    try:
        import json
        kategori_masalah_ids = json.loads(kategori_masalah_ids_str)
    except:
        kategori_masalah_ids = []
    topik = form_data.get('topik', '').strip()
    tanggal_sesi = form_data.get('tanggal_sesi')
    tindak_lanjut = form_data.get('tindak_lanjut', '').strip()
    
    if not nim_raw:
        return False, "NIM wajib diisi."
    if not jenis_layanan_id:
        return False, "Jenis layanan wajib dipilih."
    if not kategori_masalah_ids:
        return False, "Kategori masalah wajib dipilih minimal 1."
    if not topik:
        return False, "Topik permasalahan wajib diisi."
    if not tanggal_sesi:
        return False, "Tanggal sesi wajib diisi."

    # 2. Simpan ke database
    data = {
        'konselor_user_id': konselor_user_id,
        'nim_id': nim_raw,
        'nama': nama if nama else None,
        'dosen_wali': dosen_wali if dosen_wali else None,
        'prodi': prodi if prodi else None,
        'jenis_layanan_id': int(jenis_layanan_id),
        'kategori_masalah_ids': kategori_masalah_ids,
        'topik': topik,
        'tanggal_sesi': tanggal_sesi,
        'tindak_lanjut_id': int(tindak_lanjut) if tindak_lanjut else None
    }

    success, message = konselor_session_model.create_session(data)
    return success, message


def get_rekap(konselor_user_id, tahun=None):
    """
    Ambil data rekap untuk dashboard konselor.
    Return dict dengan stats + distribusi kategori untuk pie chart.
    """
    stats = konselor_session_model.get_rekap_stats(konselor_user_id, tahun=tahun)
    if not stats:
        return {
            'total_sesi': 0,
            'klien_unik': 0,
            'sesi_bulan_ini': 0,
            'kategori_distribusi': [],
            'layanan_distribusi': []
        }
    return stats


def get_riwayat_sesi(konselor_user_id, bulan=None, tahun=None):
    """Ambil riwayat sesi konseling, sensor nama untuk frontend."""
    sessions = konselor_session_model.get_sessions_by_konselor(
        konselor_user_id, bulan=bulan, tahun=tahun
    )
    for s in sessions:
        # NIM sudah mentah di nim_id
        s['nim_asli'] = s.get('nim_id', '-')
        # Sensor nama untuk display
        s['nama_sensor'] = censor_name(s.get('nama'))
        # dosen_wali sudah ada di record dari query
    return sessions


def delete_sesi(session_id, konselor_user_id):
    """Hapus sesi konseling (ownership check)."""
    return konselor_session_model.delete_session(session_id, konselor_user_id)


def update_sesi(session_id, konselor_user_id, form_data):
    """Update sesi konseling (NIM tidak bisa diubah)."""
    prodi = form_data.get('prodi', '').strip()
    jenis_layanan_id = form_data.get('jenis_layanan_id')
    kategori_masalah_ids_str = form_data.get('kategori_masalah_ids', '[]')
    try:
        import json
        kategori_masalah_ids = json.loads(kategori_masalah_ids_str)
    except:
        kategori_masalah_ids = []
    topik = form_data.get('topik', '').strip()
    tanggal_sesi = form_data.get('tanggal_sesi')
    tindak_lanjut = form_data.get('tindak_lanjut', '').strip()

    if not jenis_layanan_id:
        return False, "Jenis layanan wajib dipilih."
    if not kategori_masalah_ids:
        return False, "Kategori masalah wajib dipilih minimal 1."
    if not topik:
        return False, "Topik permasalahan wajib diisi."
    if not tanggal_sesi:
        return False, "Tanggal sesi wajib diisi."

    data = {
        'prodi': prodi if prodi else None,
        'jenis_layanan_id': int(jenis_layanan_id),
        'kategori_masalah_ids': kategori_masalah_ids,
        'topik': topik,
        'tanggal_sesi': tanggal_sesi,
        'tindak_lanjut_id': int(tindak_lanjut) if tindak_lanjut else None
    }

    return konselor_session_model.update_session(session_id, konselor_user_id, data)


# === CRUD Master Data ===

def get_all_kategori():
    return kategori_masalah_model.get_all()

def create_kategori(nama):
    return kategori_masalah_model.create(nama)

def update_kategori(kategori_id, nama):
    return kategori_masalah_model.update(kategori_id, nama)

def delete_kategori(kategori_id):
    return kategori_masalah_model.delete(kategori_id)

def get_all_layanan():
    return jenis_layanan_model.get_all()

def create_layanan(nama):
    return jenis_layanan_model.create(nama)

def update_layanan(layanan_id, nama):
    return jenis_layanan_model.update(layanan_id, nama)

def delete_layanan(layanan_id):
    return jenis_layanan_model.delete(layanan_id)

def get_all_tindak_lanjut():
    return tindak_lanjut_model.get_all()

def create_tindak_lanjut(nama):
    return tindak_lanjut_model.create(nama)

def update_tindak_lanjut(tl_id, nama):
    return tindak_lanjut_model.update(tl_id, nama)

def delete_tindak_lanjut(tl_id):
    return tindak_lanjut_model.delete(tl_id)

import pandas as pd
from io import BytesIO
from flask import send_file, jsonify
from scrapper_requests import search_mahasiswa

def download_template_excel():
    df = pd.DataFrame(columns=[
        "NIM", "Tanggal Sesi (YYYY-MM-DD)", "Topik Permasalahan", 
        "Jenis Layanan ID", "Kategori Masalah IDs (Pisahkan dengan koma)", "Tindak Lanjut ID (Opsional)",
        "Prodi (Opsional)", "Nama (Opsional)", "Dosen Wali (Opsional)"
    ])
    
    layanan = pd.DataFrame(get_all_layanan())
    kategori = pd.DataFrame(get_all_kategori())
    tindak_lanjut = pd.DataFrame(get_all_tindak_lanjut())
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Form Import', index=False)
        layanan.to_excel(writer, sheet_name='Ref Layanan', index=False)
        kategori.to_excel(writer, sheet_name='Ref Kategori', index=False)
        tindak_lanjut.to_excel(writer, sheet_name='Ref Tindak Lanjut', index=False)
        
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name="Template_Import_Sesi_Konseling.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

def import_sesi_excel(request, user_id):
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "Tidak ada file yang diunggah"})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "message": "File tidak valid"})
        
    try:
        df = pd.read_excel(file, sheet_name='Form Import')
        df = df.fillna('')
        
        success_count = 0
        error_count = 0
        
        from app import majorID
        
        layanan_map = {v['nama'].lower().strip(): v['id'] for v in get_all_layanan()}
        kategori_map = {v['nama'].lower().replace(" ", ""): v['id'] for v in get_all_kategori()}
        tl_map = {v['nama'].lower().strip(): v['id'] for v in get_all_tindak_lanjut()}
        
        for index, row in df.iterrows():
            nim = str(row.get('NIM', '')).strip()
            if nim.endswith('.0'): nim = nim[:-2]
            
            tanggal_raw = str(row.get('Tanggal Sesi (YYYY-MM-DD)', '')).strip()
            if ' ' in tanggal_raw: tanggal_raw = tanggal_raw.split(' ')[0]
            try:
                parsed_date = pd.to_datetime(tanggal_raw, dayfirst=True)
                tanggal = parsed_date.strftime('%Y-%m-%d')
            except Exception:
                tanggal = tanggal_raw
            
            topik = str(row.get('Topik Permasalahan', '')).strip()
            
            jenis_layanan_val = str(row.get('Jenis Layanan ID', '')).strip()
            jenis_layanan_id = None
            if jenis_layanan_val.isdigit(): jenis_layanan_id = int(jenis_layanan_val)
            elif jenis_layanan_val.endswith('.0') and jenis_layanan_val[:-2].isdigit(): jenis_layanan_id = int(jenis_layanan_val[:-2])
            else: jenis_layanan_id = layanan_map.get(jenis_layanan_val.lower())
            
            tl_val = str(row.get('Tindak Lanjut ID (Opsional)', '')).strip()
            tindak_lanjut_id = None
            if tl_val:
                if tl_val.isdigit(): tindak_lanjut_id = int(tl_val)
                elif tl_val.endswith('.0') and tl_val[:-2].isdigit(): tindak_lanjut_id = int(tl_val[:-2])
                else: tindak_lanjut_id = tl_map.get(tl_val.lower())
                
            kategori_raw = str(row.get('Kategori Masalah IDs (Pisahkan dengan koma)', '')).strip()
            
            prodi = str(row.get('Prodi (Opsional)', '')).strip()
            nama = str(row.get('Nama (Opsional)', '')).strip()
            dosen_wali = str(row.get('Dosen Wali (Opsional)', '')).strip()
            
            if not nim or not tanggal or not topik or not jenis_layanan_id or not kategori_raw:
                error_count += 1
                logging.error(f"[Konselor Import] Data tidak lengkap untuk NIM {nim}")
                continue
                
            kategori_ids = []
            for k in kategori_raw.split(','):
                k = k.strip()
                if not k: continue
                if k.isdigit():
                    kategori_ids.append(int(k))
                elif k.endswith('.0') and k[:-2].isdigit():
                    kategori_ids.append(int(k[:-2]))
                else:
                    k_norm = k.lower().replace(" ", "")
                    if k_norm in kategori_map:
                        kategori_ids.append(kategori_map[k_norm])
            
            if not kategori_ids:
                error_count += 1
                logging.error(f"[Konselor Import] Kategori tidak valid untuk NIM {nim}: {kategori_raw}")
                continue
            
            if not nama or not dosen_wali or not prodi:
                try:
                    df_mhs = search_mahasiswa(nim, user_id=user_id)
                    if not df_mhs.empty:
                        mhs_data = df_mhs.iloc[0]
                        mhs_dict = {str(k).lower(): v for k, v in mhs_data.items()}
                        if not nama: nama = mhs_dict.get('nama', '')
                        if not dosen_wali: dosen_wali = mhs_dict.get('dosen wali', '')
                        if not prodi: 
                            if nim and len(nim) >= 7:
                                prodi = majorID.get(nim[2:7], '')
                except Exception as e:
                    logging.error(f"[Konselor] Auto-fill gagal untuk NIM {nim}: {e}")
            
            data = {
                'konselor_user_id': user_id,
                'nim_id': nim,
                'nama': nama if nama else None,
                'dosen_wali': dosen_wali if dosen_wali else None,
                'prodi': prodi if prodi else None,
                'jenis_layanan_id': jenis_layanan_id,
                'kategori_masalah_ids': kategori_ids,
                'topik': topik,
                'tanggal_sesi': tanggal,
                'tindak_lanjut_id': tindak_lanjut_id
            }
            
            success, msg = konselor_session_model.create_session(data)
            if success:
                success_count += 1
            else:
                error_count += 1
                logging.error(f"[Konselor Import] Gagal simpan sesi {nim}: {msg}")
                
        return jsonify({
            "success": True, 
            "message": f"Import selesai. {success_count} berhasil, {error_count} gagal/dilewati."
        })
        
    except Exception as e:
        logging.error(f"[Konselor Import] Error: {e}")
        return jsonify({"success": False, "message": f"Gagal membaca file: {str(e)}"})
