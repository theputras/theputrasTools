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
    kategori_masalah_id = form_data.get('kategori_masalah_id')
    topik = form_data.get('topik', '').strip()
    tanggal_sesi = form_data.get('tanggal_sesi')
    tindak_lanjut = form_data.get('tindak_lanjut', '').strip()
    
    if not nim_raw:
        return False, "NIM wajib diisi."
    if not jenis_layanan_id:
        return False, "Jenis layanan wajib dipilih."
    if not kategori_masalah_id:
        return False, "Kategori masalah wajib dipilih."
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
        'kategori_masalah_id': int(kategori_masalah_id),
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
    kategori_masalah_id = form_data.get('kategori_masalah_id')
    topik = form_data.get('topik', '').strip()
    tanggal_sesi = form_data.get('tanggal_sesi')
    tindak_lanjut = form_data.get('tindak_lanjut', '').strip()

    if not jenis_layanan_id:
        return False, "Jenis layanan wajib dipilih."
    if not kategori_masalah_id:
        return False, "Kategori masalah wajib dipilih."
    if not topik:
        return False, "Topik permasalahan wajib diisi."
    if not tanggal_sesi:
        return False, "Tanggal sesi wajib diisi."

    data = {
        'prodi': prodi if prodi else None,
        'jenis_layanan_id': int(jenis_layanan_id),
        'kategori_masalah_id': int(kategori_masalah_id),
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
