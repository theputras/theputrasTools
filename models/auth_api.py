import uuid
import bcrypt
import os
import jwt
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session, url_for
from flask import current_app
from connection import get_connection
import logging
import pytz
from dotenv import load_dotenv


from datetime import datetime, timedelta

load_dotenv()

JAKARTA_TZ = pytz.timezone("Asia/Jakarta")

auth_bp = Blueprint('auth', __name__)

# === Utility ===
def generate_access_token(user_id):
    now = datetime.now(JAKARTA_TZ)
    payload = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=30)).timestamp())
    }
    secret = current_app.config.get("SECRET_KEY")
    if not secret:
        from flask import current_app as app
        secret = app.secret_key  # fallback ke global Flask app
    logging.info(f"[AUTH_API] Using SECRET_KEY hash={hash(secret)}")
    token = jwt.encode(payload, secret, algorithm="HS256")
    logging.info(f"[AUTH_API] Generated access token for user {user_id}")
    return token if isinstance(token, str) else token.decode()




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
    if isinstance(access_token, bytes):
        access_token = access_token.decode('utf-8')
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
    session['user_id'] = user['id']
    session.modified = True
    
    # Simpan JWT ke cookie HTTP-only agar ga ilang tiap reload
    resp = jsonify({
        "message": "Login successful!",
        "redirect": url_for('index')
    })
    resp.set_cookie(
        "access_token",
        access_token,
        httponly=True,
        secure=False,      # kalau masih localhost, pakai False
        samesite="Lax",    # kalau udah deploy (https), ganti jadi "None"
        max_age=1800
    )
    logging.info(f"[LOGIN DEBUG] Session keys={list(session.keys())}")
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
