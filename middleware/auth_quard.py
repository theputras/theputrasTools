import jwt
from functools import wraps
from flask import request, redirect, url_for, session, g, make_response, current_app
from datetime import datetime
import pytz
import os
from flask import current_app as app
import logging
from connection import get_connection

JAKARTA_TZ = pytz.timezone(os.getenv("TIMEZONE", "Asia/Jakarta"))

def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        # 1. AMBIL TOKEN
        access_token = session.get('access_token') or request.cookies.get('access_token')
        refresh_token = request.cookies.get('refresh_token')

        # Jika salah satu tidak ada, redirect login
        if not access_token or not refresh_token:
            resp = make_response(redirect(url_for('login_page', next=request.url)))
            session.clear()
            resp.set_cookie("access_token", "", expires=0)
            resp.set_cookie("refresh_token", "", expires=0)
            return resp

        secret = current_app.config.get('SECRET_KEY') or app.secret_key

        # 2. === VALIDASI REFRESH TOKEN (UUID) KE DATABASE ===
        # Kita TIDAK pakai jwt.decode() karena refresh_token kamu adalah UUID string.
        conn = None
        cursor = None
        refresh_valid = False
        
        try:
            conn = get_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)
                # Cek apakah token ada, tidak revoked, dan belum expired
                cursor.execute(
                    "SELECT user_id, expires_at, revoked FROM user_sessions WHERE refresh_token = %s", 
                    (refresh_token,)
                )
                session_data = cursor.fetchone()
                
                if session_data:
                    # Cek Status Revoked
                    if session_data['revoked'] == 1:
                        logging.warning(f"[GUARD] Refresh token revoked. Logout.")
                    # Cek Expired (expires_at di DB vs Sekarang)
                    elif session_data['expires_at'] < datetime.now():
                        logging.info(f"[GUARD] Refresh token expired database time. Logout.")
                        # Opsional: Set revoked=1 di sini biar database bersih
                    else:
                        # Token Valid!
                        refresh_valid = True
                else:
                     logging.warning(f"[GUARD] Refresh token tidak ditemukan di DB.")

        except Exception as e:
            logging.error(f"[GUARD] DB Check Error: {e}")
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

        # Jika Refresh Token Invalid secara Database -> TENDANG
        if not refresh_valid:
            resp = make_response(redirect(url_for('login_page', next=request.url)))
            session.clear()
            resp.set_cookie("access_token", "", expires=0)
            resp.set_cookie("refresh_token", "", expires=0)
            return resp

        # 3. === VALIDASI ACCESS TOKEN (JWT) ===
        try:
            payload = jwt.decode(
                access_token,
                secret,
                algorithms=["HS256"],
                options={"require": ["exp", "iat", "sub"]},
                leeway=10
            )
            
            # Cek expired JWT
            exp_time = datetime.fromtimestamp(payload['exp'], JAKARTA_TZ)
            if exp_time < datetime.now(JAKARTA_TZ):
                raise jwt.ExpiredSignatureError("Token expired")
            
            # Simpan user info ke global object 'g'
            g.user = payload

        except jwt.ExpiredSignatureError:
            logging.info("[GUARD] Access Token Expired. Attempting auto-refresh...")
            
            # AUTO-REFRESH: Refresh token sudah terbukti VALID di langkah 2.
            # Ambil user_id dari session DB untuk generate token baru.
            try:
                conn2 = get_connection()
                if conn2:
                    cursor2 = conn2.cursor(dictionary=True)
                    cursor2.execute(
                        "SELECT user_id FROM user_sessions WHERE refresh_token = %s AND revoked = 0",
                        (refresh_token,)
                    )
                    session_row = cursor2.fetchone()
                    cursor2.close()
                    conn2.close()

                    if session_row:
                        from models.auth_api import generate_access_token
                        
                        # Decode token lama TANPA validasi exp untuk ambil role_id
                        old_payload = jwt.decode(
                            access_token, secret, algorithms=["HS256"],
                            options={"verify_exp": False}
                        )
                        role_id = old_payload.get('role_id', 3)
                        user_id = session_row['user_id']

                        # Generate token baru (30 menit default)
                        new_access_token = generate_access_token(user_id, role_id)
                        if isinstance(new_access_token, bytes):
                            new_access_token = new_access_token.decode('utf-8')

                        # Set g.user supaya request bisa lanjut
                        new_payload = jwt.decode(
                            new_access_token, secret, algorithms=["HS256"],
                            leeway=10
                        )
                        g.user = new_payload
                        session['access_token'] = new_access_token
                        session.modified = True

                        # Lanjutkan request, tapi set cookie baru di response
                        response = make_response(view_func(*args, **kwargs))
                        response.set_cookie(
                            "access_token", new_access_token,
                            httponly=True, secure=False, samesite="Lax",
                            max_age=1800  # 30 menit (default)
                        )
                        logging.info(f"[GUARD] Auto-refresh berhasil untuk user_id {user_id}")
                        return response
            except Exception as refresh_err:
                logging.error(f"[GUARD] Auto-refresh gagal: {refresh_err}")

            # Kalau auto-refresh gagal, fallback ke redirect login
            resp = make_response(redirect(url_for('login_page', next=request.url)))
            session.clear()
            resp.set_cookie("access_token", "", expires=0)
            return resp

        except jwt.InvalidTokenError as e:
            logging.warning(f"[GUARD] Access Token Rusak: {e}")
            resp = make_response(redirect(url_for('login_page', next=request.url)))
            session.clear()
            resp.set_cookie("access_token", "", expires=0)
            return resp

        # Lolos semua pengecekan
        return view_func(*args, **kwargs)
        
    return wrapped_view
    
def check_permission(tool_route_name):
    """
    Decorator untuk mengecek apakah user boleh mengakses fitur ini berdasarkan tabel role_permissions.
    HARUS diletakkan di bawah @login_required.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(*args, **kwargs):
            # 1. Pastikan user udah login (variabel g.user diset oleh @login_required)
            if not hasattr(g, 'user'):
                return "Unauthorized", 401

            # 2. Ambil role_id dari token JWT (Default 3 = Mahasiswa kalau gak ada)
            role_id = g.user.get('role_id', 3) 
            
            # 3. KEKUATAN ORANG DALAM: Kalau Super Admin (1), tembusin aja semua fitur!
            if role_id == 1:
                return view_func(*args, **kwargs)

            # 4. Kalau bukan Super Admin, cek izin ke Database (tabel role_permissions)
            conn = None
            cursor = None
            try:
                conn = get_connection()
                cursor = conn.cursor(dictionary=True)
                
                # Cek apakah is_allowed = 1 untuk role_id dan tool ini
                query = """
                    SELECT rp.is_allowed 
                    FROM role_permissions rp
                    JOIN tools t ON rp.tool_id = t.id
                    WHERE rp.role_id = %s AND t.route_name = %s
                """
                cursor.execute(query, (role_id, tool_route_name))
                permission = cursor.fetchone()

                # Kalau datanya gak ada, atau is_allowed = 0, gembok!
                if not permission or permission['is_allowed'] == 0:
                    logging.warning(f"[GUARD] Akses Ditolak: Role {role_id} mencoba akses {tool_route_name}")
                    return "Akses Ditolak! Fitur ini sedang dikunci atau Anda tidak memiliki izin.", 403

            except Exception as e:
                logging.error(f"[PERMISSION GUARD] Error: {e}")
                return "Terjadi kesalahan server saat mengecek hak akses", 500
            finally:
                if cursor: cursor.close()
                if conn: conn.close()

            # Lolos semua razia, silakan masuk!
            return view_func(*args, **kwargs)
            
        return wrapped_view
    return decorator