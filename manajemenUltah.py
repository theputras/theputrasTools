# manajemenUltah.py
# Model dan helper untuk manajemen ulang tahun

import logging
import base64
from datetime import datetime
from zoneinfo import ZoneInfo
from connection import get_connection
from scrapper_requests import fetch_data_ultah, fetch_photo_from_sicyca

JKT = ZoneInfo("Asia/Jakarta")

# --- MODEL CLASS ---
class UltahRecord:
    def __init__(self):
        pass
    
    def _get_connection(self):
        return get_connection()
    
    def get_all(self):
        """Ambil semua data ultah dari database"""
        conn = self._get_connection()
        if not conn: return []
        
        cursor = conn.cursor(dictionary=True)
        try:
            query = """
                SELECT id, nama, nim, tanggal, bulan, tahun_lahir, 
                       foto_base64, google_calendar_event_id, prodi, is_from_sicyca,
                       created_at
                FROM ultah_records 
                ORDER BY bulan, tanggal
            """
            cursor.execute(query)
            results = cursor.fetchall()
            
            # Hitung usia untuk setiap record
            now = datetime.now(JKT)
            for r in results:
                if r['tahun_lahir']:
                    r['usia'] = now.year - r['tahun_lahir']
                else:
                    r['usia'] = None
                    
                # Format tanggal lahir untuk display
                bulan_indo = {
                    1: "Januari", 2: "Februari", 3: "Maret", 4: "April", 
                    5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus", 
                    9: "September", 10: "Oktober", 11: "November", 12: "Desember"
                }
                r['tanggal_display'] = f"{r['tanggal']} {bulan_indo.get(r['bulan'], '')}"
                if r['tahun_lahir']:
                    r['tanggal_display'] += f" {r['tahun_lahir']}"
            
            return results
        except Exception as e:
            logging.error(f"[Ultah] Error get_all: {e}")
            return []
        finally:
            cursor.close()
            conn.close()
    
    def get_by_id(self, record_id):
        """Ambil satu record by ID"""
        conn = self._get_connection()
        if not conn: return None
        
        cursor = conn.cursor(dictionary=True)
        try:
            query = "SELECT * FROM ultah_records WHERE id = %s"
            cursor.execute(query, (record_id,))
            return cursor.fetchone()
        except Exception as e:
            logging.error(f"[Ultah] Error get_by_id: {e}")
            return None
        finally:
            cursor.close()
            conn.close()
    
    def check_nim_exists(self, nim, exclude_id=None):
        """Cek apakah NIM sudah ada"""
        if not nim:
            return False
        conn = self._get_connection()
        if not conn: return False
        
        cursor = conn.cursor()
        try:
            if exclude_id:
                query = "SELECT COUNT(*) FROM ultah_records WHERE nim = %s AND id != %s"
                cursor.execute(query, (nim, exclude_id))
            else:
                query = "SELECT COUNT(*) FROM ultah_records WHERE nim = %s"
                cursor.execute(query, (nim,))
            count = cursor.fetchone()[0]
            return count > 0
        except Exception as e:
            logging.error(f"[Ultah] Error check_nim: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    def create(self, data):
        """Insert record baru"""
        conn = self._get_connection()
        if not conn: return False
        
        cursor = conn.cursor()
        try:
            query = """
                INSERT INTO ultah_records 
                (nama, nim, tanggal, bulan, tahun_lahir, foto_base64, prodi, is_from_sicyca)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (
                data.get('nama'),
                data.get('nim') or None,
                data.get('tanggal'),
                data.get('bulan'),
                data.get('tahun_lahir') or None,
                data.get('foto_base64') or None,
                data.get('prodi') or None,
                data.get('is_from_sicyca', 0)
            ))
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"[Ultah] Error create: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    def update(self, record_id, data):
        """Update record"""
        conn = self._get_connection()
        if not conn: return False
        
        cursor = conn.cursor()
        try:
            query = """
                UPDATE ultah_records 
                SET nama = %s, nim = %s, tanggal = %s, bulan = %s, 
                    tahun_lahir = %s, foto_base64 = %s, prodi = %s
                WHERE id = %s
            """
            cursor.execute(query, (
                data.get('nama'),
                data.get('nim') or None,
                data.get('tanggal'),
                data.get('bulan'),
                data.get('tahun_lahir') or None,
                data.get('foto_base64') or None,
                data.get('prodi') or None,
                record_id
            ))
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"[Ultah] Error update: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    
    def delete(self, record_id):
        """Hapus record"""
        conn = self._get_connection()
        if not conn: return False
        
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM ultah_records WHERE id = %s", (record_id,))
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"[Ultah] Error delete: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def update_google_event_id(self, record_id, event_id):
        """Update Google Calendar Event ID"""
        conn = self._get_connection()
        if not conn: return False
        
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE ultah_records SET google_calendar_event_id = %s WHERE id = %s", 
                (event_id, record_id)
            )
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"[Ultah] Error update_event_id: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

# Instance model
ultah_model = UltahRecord()

# --- HELPER FUNCTIONS ---
def parse_tanggal_sicyca(tanggal_str):
    """Parse tanggal dari format SICYCA (DD-MM-YYYY atau 'DD Bulan YYYY')"""
    bulan_map = {
        "januari": 1, "februari": 2, "maret": 3, "april": 4,
        "mei": 5, "juni": 6, "juli": 7, "agustus": 8,
        "september": 9, "oktober": 10, "november": 11, "desember": 12
    }
    
    try:
        # Format: "10 Desember 2004"
        parts = tanggal_str.split()
        if len(parts) >= 2:
            tanggal = int(parts[0])
            bulan = bulan_map.get(parts[1].lower(), 1)
            tahun = int(parts[2]) if len(parts) > 2 else None
            return tanggal, bulan, tahun
    except:
        pass
    
    return None, None, None
