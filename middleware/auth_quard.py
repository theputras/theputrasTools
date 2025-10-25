import jwt
from functools import wraps
from flask import request, redirect, url_for, session
from datetime import datetime, timezone
from models.auth_api import SECRET_KEY

def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        print("[GUARD DEBUG] Session keys:", list(session.keys()))

        token = None

        # 1️⃣ Coba ambil token dari Flask session dulu
        if 'access_token' in session:
            token = session['access_token']

        # 2️⃣ Kalau gak ada di session, coba ambil dari Authorization header
        if not token:
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]

        # 3️⃣ Kalau tetap gak ada token sama sekali, redirect ke login
        if not token:
            return redirect(url_for('login_page'))

        try:
            # 4️⃣ Decode JWT dan cek expired
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            exp_time = datetime.fromtimestamp(payload['exp'], tz=timezone.utc)

            if exp_time < datetime.now(timezone.utc):
                session.clear()
                return redirect(url_for('login_page'))

        except jwt.ExpiredSignatureError:
            session.clear()
            return redirect(url_for('login_page'))
        except jwt.InvalidTokenError:
            session.clear()
            return redirect(url_for('login_page'))

        # 5️⃣ Kalau semua valid, lanjut ke view
        return view_func(*args, **kwargs)
        
    return wrapped_view
