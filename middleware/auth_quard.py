import jwt
from functools import wraps
from flask import request, redirect, url_for, session, g
from datetime import datetime, timezone
import pytz
from flask import current_app as app
import logging
JAKARTA_TZ = pytz.timezone("Asia/Jakarta")

def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        print("[GUARD DEBUG] Session keys:", list(session.keys()))

        token = None
        auth_header = None  # Tambahkan ini: Inisialisasi awal

        # 1. Dari session (existing)
        if not token and 'access_token' in session:
            token = session['access_token']
        
    # 2. Dari header Authorization (existing)
        if not token:
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
    
    # 3. Tambah: Dari cookie (baru)
        if not token:
            token = request.cookies.get('access_token')  # Ambil dari cookie
        # Jika masih None, redirect
        if not token:
            return redirect(url_for('login_page'))
        # logging.info(f"[GUARD] Token source: session={bool('access_token' in session)}, header={bool(auth_header)}, cookie={bool(request.cookies.get('access_token'))}")
        try:
            # Decode JWT dan verifikasi waktu dengan toleransi kecil
            secret = app.config.get('SECRET_KEY') or app.secret_key
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                options={"require": ["exp", "iat", "sub"]},
                leeway=30
            )

        
            # logging.info(f"[AUTH_GUARD] SECRET_KEY used for decode: {app.config['SECRET_KEY']}")
            # logging.info(f"[AUTH_GUARD] Payload diterima: {payload}")
        
            exp_time = datetime.fromtimestamp(payload['exp'], JAKARTA_TZ)
            if exp_time < datetime.now(JAKARTA_TZ):
                logging.info("[GUARD DEBUG] Token expired")
                session.clear()
                return redirect(url_for('login_page'))
        
            g.user = payload

        
        except jwt.ExpiredSignatureError:
            logging.info("[GUARD DEBUG] Token expired (ExpiredSignatureError)")
            session.clear()
            return redirect(url_for('login_page'))
        except jwt.InvalidTokenError:
            session.clear()
            logging.info("[GUARD DEBUG] Invalid token")
            return redirect(url_for('login_page'))

        # 5️⃣ Kalau semua valid, lanjut ke view
        return view_func(*args, **kwargs)
        
    return wrapped_view
