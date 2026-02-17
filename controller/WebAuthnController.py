from connection import get_connection

def save_credential(user_id, credential_id, public_key, sign_count, transports):
    """Menyimpan Public Key ke database setelah registrasi sidik jari sukses"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO webauthn_credentials (user_id, credential_id, public_key, sign_count, transports)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, credential_id, public_key, sign_count, transports))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error save_credential: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def get_credentials_by_user(user_id):
    """Mengambil daftar sidik jari yang dimiliki oleh user (untuk Login)"""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM webauthn_credentials WHERE user_id = %s", (user_id,))
    creds = cursor.fetchall()
    conn.close()
    return creds

def get_user_by_credential(credential_id):
    """Mencari user berdasarkan ID perangkat (Saat unlock login awal)"""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT u.*, wc.public_key, wc.sign_count 
        FROM webauthn_credentials wc
        JOIN users u ON wc.user_id = u.id
        WHERE wc.credential_id = %s
    """, (credential_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_sign_count(credential_id, new_sign_count):
    """Update hitungan login untuk mencegah serangan cloning (replay attack)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE webauthn_credentials SET sign_count = %s WHERE credential_id = %s", (new_sign_count, credential_id))
    conn.commit()
    cursor.close()
    conn.close()