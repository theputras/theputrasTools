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
# import json
# from webauthn import verify_registration_response, verify_authentication_response, generate_authentication_options, generate_registration_options, serialize_options
import base64
import json
from webauthn import verify_registration_response, verify_authentication_response, generate_authentication_options, generate_registration_options


from datetime import datetime, timedelta


def serialize_options(options):
    def encode_bytes(obj):
        if isinstance(obj, bytes):
            return base64.b64encode(obj).decode('utf-8')
        elif isinstance(obj, dict):
            return {k: encode_bytes(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [encode_bytes(item) for item in obj]
        elif hasattr(obj, '__dict__'):
            return encode_bytes(obj.__dict__)
        else:
            return obj
    return encode_bytes(options)
load_dotenv()

JAKARTA_TZ = pytz.timezone("Asia/Jakarta")

auth_bp = Blueprint('auth', __name__)

# === Utility ===
def generate_access_token(user_id):
    payload = {
        'sub': str(user_id),  # Ubah ke str() agar jadi string, e.g., '1' bukan 1
        'iat': datetime.now(JAKARTA_TZ),
        'exp': datetime.now(JAKARTA_TZ) + timedelta(minutes=30)
    }
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')





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
    session['access_token'] = access_token  # Tambahkan ini
    session.modified = True  # Sudah ada, tapi pastikan
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


@auth_bp.route('/register-face', methods=['POST'])
def register_face():
    data = request.json
    face_data = data.get('faceData')
    user_id = session.get('user_id')
    if not user_id or not face_data:
        return jsonify({'error': 'Invalid data'}), 400
    
    # Simpan face_data sebagai JSON di DB (tambah kolom face_data di tabel)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET face_data = %s WHERE id = %s", (json.dumps(face_data), user_id))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True})

@auth_bp.route('/verify-face-id-registration', methods=['POST'])
def verify_face_id_registration():
    data = request.json
    challenge = session.pop('face_id_challenge', None)
    if not challenge:
        return jsonify({'error': 'No challenge'}), 400
    
    try:
        credential = verify_registration_response(
            credential=data,
            expected_challenge=challenge,
            expected_origin="https://tools.theputras.my.id",
            expected_rp_id="tools.theputras.my.id"
        )
        
        # Simpan ke DB dengan device_type 'face'
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO fingerprint_credentials (user_id, credential_id, public_key, sign_count, device_type)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            session.get('user_id'),
            credential.credential_id,
            json.dumps(credential.public_key),
            credential.sign_count,
            'face'  # Device type untuk Face ID
        ))
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400
        
        
@auth_bp.route('/login-face', methods=['POST'])
def login_face():
    data = request.json
    face_data = data.get('faceData')
    if not face_data:
        return jsonify({'error': 'Invalid data'}), 400
    
    # Query face_data dari DB
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, face_data FROM users WHERE face_data IS NOT NULL")
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    
    for user in users:
        stored_face = json.loads(user['face_data'])
        # Simple Euclidean distance (gunakan library seperti numpy untuk accuracy)
        distance = sum((a - b) ** 2 for a, b in zip(face_data, stored_face)) ** 0.5
        if distance < 0.6:  # Threshold
            session['user_id'] = user['id']
            session.modified = True
            return jsonify({'success': True})
    return jsonify({'error': 'Face not recognized'}), 401
    

@auth_bp.route('/verify-face-id-login', methods=['POST'])
def verify_face_id_login():
    data = request.json
    challenge = session.pop('face_id_auth_challenge', None)
    user_id = session.pop('face_id_user_id', None)
    if not challenge or not user_id:
        return jsonify({'error': 'No challenge or user'}), 400
    
    # Query credential dengan device_type 'face'
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM fingerprint_credentials WHERE user_id = %s AND credential_id = %s AND device_type = 'face'", (user_id, data['id']))
    cred = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not cred:
        return jsonify({'error': 'Face ID credential not found'}), 404
    
    try:
        assertion = verify_authentication_response(
            credential=data,
            expected_challenge=challenge,
            expected_origin="https://tools.theputras.my.id",
            expected_rp_id="tools.theputras.my.id",
            credential_public_key=json.loads(cred['public_key']),  # Load dari DB
            credential_current_sign_count=cred['sign_count']
        )
        
        # Update sign_count dan last_used
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE fingerprint_credentials SET sign_count = %s, last_used = NOW() WHERE id = %s", (assertion.new_sign_count, cred['id']))
        conn.commit()
        cursor.close()
        conn.close()
        
        # Set session
        session['user_id'] = user_id
        session.modified = True
        
        return jsonify({'success': True, 'redirect': '/'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400