import jwt
from functools import wraps
from flask import request, redirect, url_for, session, g, make_response, current_app
from datetime import datetime
import pytz
import os
from flask import current_app as app
import logging
from connection import get_connection

JAKARTA_TZ = pytz.timezone(os.getenv("TIMEZONE"))

def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        print("[GUARD DEBUG] Session keys:", list(session.keys()))

        # 2. SEKARANG KITA BUTUH KEDUA TOKEN
        access_token = session.get('access_token') or request.cookies.get('access_token')
        refresh_token = request.cookies.get('refresh_token') # <-- AMBIL INI JUGA

        # Kalo salah satu token aja nggak ada, pasti logout
        if not access_token or not refresh_token:
            logging.info("[GUARD] Token(s) missing. Redirecting to login.")
            # Pastiin kita clear cookie-nya kalo mau redirect
            resp = make_response(redirect(url_for('login_page')))
            session.clear()
            resp.set_cookie("access_token", "", expires=0)
            resp.set_cookie("refresh_token", "", expires=0)
            return resp

        try:
            # 3. DECODE ACCESS TOKEN (JWT)
            secret = current_app.config.get('SECRET_KEY') or app.secret_key
            payload = jwt.decode(
                access_token,
                secret,
                algorithms=["HS256"],
                options={"require": ["exp", "iat", "sub"]},
                leeway=30
            )
            
            # Cek kalo udah expired
            exp_time = datetime.fromtimestamp(payload['exp'], JAKARTA_TZ)
            if exp_time < datetime.now(JAKARTA_TZ):
                raise jwt.ExpiredSignatureError("Token expired")

            # 4. === INI BAGIAN BARU: VALIDASI KE DATABASE ===
            user_id = payload['sub']
            session_status = None
            conn = None
            cursor = None
            try:
                conn = get_connection()
                if conn:
                    cursor = conn.cursor(dictionary=True)
                    # Cek pake refresh_token DAN user_id
                    cursor.execute(
                        "SELECT revoked FROM user_sessions WHERE refresh_token = %s AND user_id = %s", 
                        (refresh_token, user_id)
                    )
                    session_status = cursor.fetchone()
                else:
                    logging.error("[GUARD] DB connection failed.")
            except Exception as e:
                logging.error(f"[GUARD] DB check error: {e}")
            finally:
                if cursor: cursor.close()
                if conn: conn.close()

            # 5. CEK HASIL DARI DATABASE
            if not session_status:
                # Skenario aneh: Token JWT-nya valid, 
                # tapi refresh_token-nya nggak ada di DB
                logging.warning(f"[GUARD] Session not found in DB for user {user_id}. Forcing logout.")
                raise jwt.InvalidTokenError("Session not in DB")

            if session_status['revoked'] == 1:
                # INI DIA! Session-nya di-revoke (misal dari 'Logout All')
                logging.warning(f"[GUARD] Session revoked for user {user_id}. Forcing logout.")
                raise jwt.InvalidTokenError("Session revoked")
            
            # === AKHIR DARI BAGIAN BARU ===

            # Kalo lolos semua cek di atas, baru kita aman
            g.user = payload

        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError) as e:
            logging.info(f"[GUARD DEBUG] Token invalid ({e}). Redirecting to login.")
            # Kalo token-nya bermasalah (expired, revoked, dll), 
            # kita bersihin dan redirect
            resp = make_response(redirect(url_for('login_page')))
            session.clear()
            resp.set_cookie("access_token", "", expires=0)
            resp.set_cookie("refresh_token", "", expires=0)
            return resp

        # Lolos
        return view_func(*args, **kwargs)
        
    return wrapped_view
