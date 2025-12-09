# seed_gate_user.py

import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from connection import get_connection

load_dotenv()

# 1. Ambil kunci enkripsi dari .env
key = os.getenv("GATE_ENCRYPTION_KEY")
if not key:
    raise ValueError("FATAL: GATE_ENCRYPTION_KEY belum diset di .env!")

cipher = Fernet(key)

# === KONFIGURASI DATA ===
# User ID aplikasi (hardcoded ke 1 sesuai request)
TARGET_USER_ID = 1 

# Kredensial Gate/Sicyca yang mau disimpan
gate_username_input = "23410100003"  # Ganti dengan NIM asli
gate_password_asli  = "368010" # Ganti dengan Pass asli
# ========================

# 2. Enkripsi Password
encrypted_password = cipher.encrypt(gate_password_asli.encode()).decode()

print(f"Target User ID   : {TARGET_USER_ID}")
print(f"Gate Username    : {gate_username_input}")
print(f"Password Encrypted: {encrypted_password[:15]}... (disensor)")

# 3. Masukkan ke Database
conn = None
cursor = None
try:
    conn = get_connection()
    if not conn:
        raise Exception("Gagal koneksi ke database.")
        
    cursor = conn.cursor()
    
    # Query disesuaikan dengan struktur tabel baru
    # Menggunakan 'ON DUPLICATE KEY UPDATE' agar kalau dijalankan 2x, dia update data lama (bukan error)
    query = """
    INSERT INTO gate_users (user_id, gate_username, gate_password, is_active) 
    VALUES (%s, %s, %s, 1)
    ON DUPLICATE KEY UPDATE 
        gate_username = VALUES(gate_username),
        gate_password = VALUES(gate_password),
        is_active = 1,
        updated_at = NOW()
    """
    
    cursor.execute(query, (TARGET_USER_ID, gate_username_input, encrypted_password))
    conn.commit()
    
    print("\n[SUKSES] Kredensial Gate berhasil disimpan untuk User ID 1.")
    
except Exception as e:
    print(f"\n[ERROR] Gagal menyimpan data: {e}")
finally:
    if cursor: cursor.close()
    if conn: conn.close()