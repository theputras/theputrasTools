import os
import psycopg2
from psycopg2 import Error
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import logging

# Load .env di root project
load_dotenv()

from psycopg2.extensions import connection as _connection

class DictSupportConnection(_connection):
    def cursor(self, *args, **kwargs):
        if kwargs.pop('dictionary', False):
            kwargs['cursor_factory'] = RealDictCursor
        return super().cursor(*args, **kwargs)

def get_connection():
    try:
        connection = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
            user=os.getenv("DB_USERNAME"),
            password=os.getenv("DB_PASSWORD"),
            dbname=os.getenv("DB_DATABASE"),
            connection_factory=DictSupportConnection
        )
        
        logging.info("=== Koneksi ke database berhasil ===")
        return connection
    except Error as e:
        logging.error(f"=== Gagal konek database: {e} ===")
        return None
if not all([os.getenv("DB_HOST"), os.getenv("DB_USERNAME"), os.getenv("DB_DATABASE")]):
    logging.error(f"⚠️  Missing DB config in .env")
    raise SystemExit("⚠️  Missing DB config in .env")
