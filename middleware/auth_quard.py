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
                leeway=30
            )
            
            # Cek expired JWT
            exp_time = datetime.fromtimestamp(payload['exp'], JAKARTA_TZ)
            if exp_time < datetime.now(JAKARTA_TZ):
                raise jwt.ExpiredSignatureError("Token expired")
            
            # Simpan user info ke global object 'g'
            g.user = payload

        except jwt.ExpiredSignatureError:
            logging.info("[GUARD] Access Token Expired.")
            # TODO: Di sini idealnya kita lakukan Auto-Refresh Access Token 
            # karena Refresh Token (di langkah 2) sudah terbukti VALID.
            # Tapi untuk sekarang, redirect login dulu biar aman.
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