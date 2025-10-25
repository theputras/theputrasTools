import os
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv
import logging

# Load .env di root project
load_dotenv()

def get_connection():
    try:
        connection = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
            user=os.getenv("DB_USERNAME"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_DATABASE")
        )
        
        logging.info("=== Koneksi ke database berhasil ===")
        return connection
    except Error as e:
        logging.error(f"=== Gagal konek database: {e} ===")
        return None
if not all([os.getenv("DB_HOST"), os.getenv("DB_USERNAME"), os.getenv("DB_DATABASE")]):
    logging.error(f"⚠️  Missing DB config in .env")
    raise SystemExit("⚠️  Missing DB config in .env")
