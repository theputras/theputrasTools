import bcrypt
import logging
from connection import get_connection

def get_all_users():
    """Mengambil semua data user beserta nama rolenya."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT u.id, u.username, u.email, u.role_id, r.nama_role 
            FROM users u 
            LEFT JOIN roles r ON u.role_id = r.id
            ORDER BY u.id DESC
        """)
        return cursor.fetchall()
    except Exception as e:
        logging.error(f"[UserController] Error get_all_users: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

def get_all_roles(include_super_admin=True):
    """Mengambil semua data role."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if include_super_admin:
            cursor.execute("SELECT id, nama_role FROM roles")
        else:
            cursor.execute("SELECT id, nama_role FROM roles WHERE id != 1")
        return cursor.fetchall()
    except Exception as e:
        logging.error(f"[UserController] Error get_all_roles: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

def create_user(username, email, password, role_id):
    """Menambahkan user baru ke database beserta enkripsi password."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Enkripsi password
        hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        cursor.execute("""
            INSERT INTO users (username, email, password, role_id) 
            VALUES (%s, %s, %s, %s)
        """, (username, email if email else None, hashed_pw, role_id))
        conn.commit()
        return True, "User baru berhasil ditambahkan!"
        
    except Exception as e:
        if 'Duplicate entry' in str(e):
            return False, "Gagal! Username atau Email sudah terdaftar."
        logging.error(f"[UserController] Error create_user: {e}")
        return False, "Terjadi kesalahan sistem saat menambah user."
    finally:
        cursor.close()
        conn.close()

def change_user_role(user_id, role_id):
    """Mengubah role_id dari seorang user."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET role_id = %s WHERE id = %s", (role_id, user_id))
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"[UserController] Error change_user_role: {e}")
        return False
    finally:
        cursor.close()
        conn.close()
        
def update_user_detail(user_id, username, email):
    """Mengupdate detail dasar user (username & email)."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE users SET username = %s, email = %s WHERE id = %s
        """, (username, email if email else None, user_id))
        conn.commit()
        return True, "Data user berhasil diperbarui!"
    except Exception as e:
        if 'Duplicate entry' in str(e):
            return False, "Gagal! Username atau Email sudah digunakan."
        logging.error(f"[UserController] Error update_user_detail: {e}")
        return False, "Terjadi kesalahan saat mengupdate user."
    finally:
        cursor.close()
        conn.close()

def delete_user(user_id):
    """Menghapus user dari database berdasarkan ID."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"[UserController] Error delete_user: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def reset_user_password(user_id):
    """Mereset password user ke default 'mhs123'."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Password default
        default_pw = "mhs123"
        # Enkripsi password default
        hashed_pw = bcrypt.hashpw(default_pw.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_pw, user_id))
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"[UserController] Error reset_user_password: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def update_user_password(user_id, new_password):
    """Fungsi khusus untuk mengganti password user secara mandiri"""
    # Validasi backend
    if not new_password or len(new_password) < 6:
        return False, "Password minimal 6 karakter!"
        
    # Enkripsi password baru pakai bcrypt
    hashed_pw = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Update ke tabel users
        cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_pw, user_id))
        conn.commit()
        return True, "Password berhasil diperbarui! Silakan gunakan password baru pada login berikutnya."
    except Exception as e:
        logging.error(f"[Update Password] Error: {e}")
        return False, "Gagal memperbarui password."
    finally:
        cursor.close()
        conn.close()