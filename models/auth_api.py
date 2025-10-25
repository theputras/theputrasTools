import uuid
import bcrypt
import os
import jwt
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, make_response, session, current_app as app
from connection import get_connection
from flask import session
import logging
from dotenv import load_dotenv


from datetime import datetime, timedelta
import pytz

load_dotenv()

JAKARTA_TZ = pytz.timezone("Asia/Jakarta")

auth_bp = Blueprint('auth', __name__)
SECRET_KEY = os.getenv("SECRET_KEY")  # Ganti sama env var di produksi


# === Utility ===
def generate_access_token(user_id):
    payload = {
        "sub": user_id,
        "exp": datetime.now(JAKARTA_TZ) + timedelta(minutes=15),
        "iat": datetime.now(JAKARTA_TZ)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def generate_refresh_token():
    return str(uuid.uuid4())


# === LOGIN ===
@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.form
    username = data.get('username')
    password = data.get('password')

    conn = get_connection()
    if not conn:
        return jsonify({"error": "Koneksi ke database gagal"}), 500
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, username, password FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()

    if not user or not bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
        cursor.close()
        conn.close()
        return jsonify({"error": "Username atau password salah"}), 401

    access_token = generate_access_token(user['id'])
    refresh_token = generate_refresh_token()
    expires_at = datetime.now(JAKARTA_TZ) + timedelta(days=30)

    ip_address = request.remote_addr or "0.0.0.0"
    user_agent = request.headers.get('User-Agent', 'Unknown')

    cursor.execute("""
        INSERT INTO user_sessions (user_id, refresh_token, expires_at, ip_address, user_agent, revoked, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW())
    """, (user['id'], refresh_token, expires_at, ip_address, user_agent, 0))
    conn.commit()
    cursor.close()
    conn.close()

    # ===== SET SESSION =====
    session['access_token'] = access_token
    session['user_id'] = user['id']
    session.modified = True

    # ===== BUAT RESPONSE =====
    resp = make_response(jsonify({
        "message": "Login berhasil",
        "redirect": "/"
    }))

    # ===== SIMPAN SESSION KE RESPONSE (ini penting!) =====
    session.modified = True

    # ===== LOG DEBUG =====
    logging.info(f"[LOGIN DEBUG] Session keys={list(session.keys())}")
    logging.info(f"[LOGIN DEBUG] Set-Cookie (before return): {resp.headers.get('Set-Cookie')}")

    return resp, 200




# === LOGOUT (hapus 1 session aktif) ===
@auth_bp.route('/logout', methods=['POST'])
def logout():
    data = request.form
    refresh_token = data.get('refresh_token')

    conn = get_connection()
    if not conn:
        return jsonify({"error": "DB connection failed"}), 500
    cursor = conn.cursor()

    cursor.execute("UPDATE user_sessions SET revoked = 1 WHERE refresh_token = %s", (refresh_token,))
    
    conn.commit()

    cursor.close()
    conn.close()
    return jsonify({"message": "Berhasil logout"}), 200


# === LOGOUT ALL DEVICE ===
@auth_bp.route('/logout_all', methods=['POST'])
def logout_all():
    data = request.form
    user_id = data.get('user_id')

    conn = get_connection()
    if not conn:
        return jsonify({"error": "DB connection failed"}), 500
    cursor = conn.cursor()

    cursor.execute("UPDATE user_sessions SET revoked = TRUE WHERE user_id = %s", (user_id,))
    conn.commit()

    cursor.close()
    conn.close()
    return jsonify({"message": "Semua sesi berhasil dihapus"}), 200
