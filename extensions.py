# extensions.py
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Inisialisasi limiter tanpa 'app' dulu
# Global limit longgar (user normal browsing bisa kena banyak request).
# Endpoint sensitif (login, register) punya limit ketat sendiri via @limiter.limit().
limiter = Limiter(key_func=get_remote_address, default_limits=["500 per day", "300 per hour"], storage_uri="memory://")