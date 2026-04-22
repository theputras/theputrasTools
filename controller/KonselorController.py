# controller/KonselorController.py
# Controller untuk fitur Pencatatan Sesi Konseling
# NIM di-hash SHA-256 (satu arah) untuk privasi mahasiswa

import hashlib
import logging
from models.konselor import (
    kategori_masalah_model,
    jenis_layanan_model,
    konselor_session_model
)


import os
from cryptography.fernet import Fernet

def get_fernet():
    key = os.getenv("SECRET_KEY")
    if not key:
        raise ValueError("SECRET_KEY missing in environment for Fernet encryption")
    return Fernet(key.encode('utf-8'))

def hash_nim(nim_raw):
    """
    Hash NIM menggunakan SHA-256 (satu arah) untuk menghitung statistik unique.
    """
    if not nim_raw:
        return None
    return hashlib.sha256(nim_raw.strip().encode('utf-8')).hexdigest()

def encrypt_nim(nim_raw):
    """Enkripsi NIM dua arah."""
    if not nim_raw:
        return None
    f = get_fernet()
    return f.encrypt(nim_raw.strip().encode('utf-8')).decode('utf-8')

def decrypt_nim(nim_encrypted):
    """Dekripsi NIM dua arah."""
    if not nim_encrypted:
        return None
    f = get_fernet()
    try:
        return f.decrypt(nim_encrypted.encode('utf-8')).decode('utf-8')
    except Exception as e:
        logging.error(f"[Konselor] Error decrypting NIM: {e}")
        return "ERROR_DECRYPT"


def create_sesi(konselor_user_id, form_data):
    """
    Proses pembuatan sesi baru:
    1. Validasi input
    2. Hash NIM (SHA-256) untuk counting
    3. Encrypt NIM (Fernet) untuk display
    4. Simpan ke database
    5. Buang NIM asli dari memori
    """
    # 1. Validasi
    nim_raw = form_data.get('nim', '').strip()
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

    # 2. Hash & Encrypt
    nim_hashed = hash_nim(nim_raw)
    nim_encrypted = encrypt_nim(nim_raw)

    # 3. Buang NIM asli dari variabel lokal
    nim_raw = None
    del nim_raw

    # 4. Simpan ke database
    data = {
        'konselor_user_id': konselor_user_id,
        'nim_hash': nim_hashed,
        'nim_encrypted': nim_encrypted,
        'prodi': prodi if prodi else None,
        'jenis_layanan_id': int(jenis_layanan_id),
        'kategori_masalah_id': int(kategori_masalah_id),
        'topik': topik,
        'tanggal_sesi': tanggal_sesi,
        'tindak_lanjut': tindak_lanjut if tindak_lanjut else None
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
    """Ambil riwayat sesi konseling dan decrypt NIM."""
    sessions = konselor_session_model.get_sessions_by_konselor(
        konselor_user_id, bulan=bulan, tahun=tahun
    )
    for s in sessions:
        if s.get('nim_encrypted'):
            s['nim_asli'] = decrypt_nim(s['nim_encrypted'])
            # Don't send the encrypted string to frontend if we don't need to (optional, but safe)
            del s['nim_encrypted']
    return sessions


def delete_sesi(session_id, konselor_user_id):
    """Hapus sesi konseling (ownership check)."""
    return konselor_session_model.delete_session(session_id, konselor_user_id)


def update_sesi(session_id, konselor_user_id, form_data):
    """Update sesi konseling (NIM tidak bisa diubah karena sudah di-hash)."""
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
        'tindak_lanjut': tindak_lanjut if tindak_lanjut else None
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
