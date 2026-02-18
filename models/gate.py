# models/gate.py

import os
import logging
import requests
from cryptography.fernet import Fernet
from connection import get_connection

# === MODEL USER (Kredensial) ===
class GateUser:
    def __init__(self):
        self.key = os.getenv("GATE_ENCRYPTION_KEY")
        if not self.key:
            logging.error("FATAL: GATE_ENCRYPTION_KEY belum diset di .env")
            self.cipher = None
        else:
            self.cipher = Fernet(self.key)

    def _get_connection(self):
        return get_connection()

    def get_credentials_by_user_id(self, user_id):
        if not self.cipher: return None, None, None
        conn = self._get_connection()
        if not conn: return None, None, None
            
        cursor = conn.cursor(dictionary=True)
        try:
            # Ambil credentials
            query = """
                SELECT id, gate_username, gate_password 
                FROM gate_users 
                WHERE user_id = %s AND is_active = 1 
                LIMIT 1
            """
            cursor.execute(query, (user_id,))
            result = cursor.fetchone()
            
            if result:
                try:
                    decrypted_pwd = self.cipher.decrypt(result['gate_password'].encode()).decode()
                    return result['id'], result['gate_username'], decrypted_pwd
                except Exception as e:
                    logging.error(f"[GateUser] Dekripsi gagal user {user_id}: {e}")
            return None, None, None
        finally:
            cursor.close()
            conn.close()
    def get_bot_user(self):
        """
        Cari satu user yang punya akun Gate aktif buat dipake sama Bot/Scheduler.
        Prioritas: User ID terkecil yang is_active = 1.
        """
        conn = self._get_connection()
        if not conn: return 1 # Fallback darurat
        
        cursor = conn.cursor()
        try:
            # Ambil user pertama yang punya kredensial aktif
            query = "SELECT user_id FROM gate_users WHERE is_active = 1 ORDER BY user_id ASC LIMIT 1"
            cursor.execute(query)
            result = cursor.fetchone()
            
            if result:
                # KETEMU! Pake user ini (misal: User ID 2)
                return result[0] 
            
            # Kalau tabel kosong melompong, yaudah pasrah balik ke 1
            return 1 
        except Exception as e:
            logging.error(f"[GateModel] Error cari bot user: {e}")
            return 1
        finally:
            cursor.close()
            conn.close()

# === MODEL SESSION (Cookies Terpisah) ===
class GateSession:
    def _get_connection(self):
        return get_connection()

    def load_cookies(self, user_id):
        """
        Flow: Cek tabel gate_sessions -> Ambil token terpisah -> Susun CookieJar
        """
        conn = self._get_connection()
        if not conn: return None

        cursor = conn.cursor(dictionary=True)
        jar = requests.cookies.RequestsCookieJar()
        
        try:
            # Ambil kolom spesifik
            query = """
                SELECT s.xsrf_token, s.gate_session, s.sso_token 
                FROM gate_sessions s
                JOIN gate_users u ON s.gate_user_id = u.id
                WHERE u.user_id = %s 
                LIMIT 1
            """
            cursor.execute(query, (user_id,))
            res = cursor.fetchone()
            
            if res:
                # 1. XSRF-TOKEN (Gate)
                if res['xsrf_token']:
                    jar.set('XSRF-TOKEN', res['xsrf_token'], domain='gate.dinamika.ac.id', path='/')

                # 2. gate_dinamika_session (Gate)
                if res['gate_session']:
                    jar.set('gate_dinamika_session', res['gate_session'], domain='gate.dinamika.ac.id', path='/')

                # 3. SSO_TOKEN (Global)
                if res['sso_token']:
                    jar.set('SSO_TOKEN', res['sso_token'], domain='.dinamika.ac.id', path='/')

                return jar
            return None
        except Exception as e:
            logging.error(f"[GateSession] Gagal load cookies: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    def save_cookies(self, gate_user_id, cookie_source, user_agent):
        """
        Flow: Ambil cookies dari session -> Pisah token -> Simpan ke kolom DB
        """
        conn = self._get_connection()
        if not conn: return False

        cursor = conn.cursor()
        try:
            # PERBAIKAN DI SINI:
            # Cek apakah inputnya Dictionary (dari controller baru) atau Object Session (legacy)
            if isinstance(cookie_source, dict):
                val_xsrf = cookie_source.get('XSRF-TOKEN')
                val_gate = cookie_source.get('gate_dinamika_session')
                val_sso  = cookie_source.get('SSO_TOKEN')
            else:
                # Fallback jika yang dikirim masih object requests.Session
                val_xsrf = cookie_source.cookies.get('XSRF-TOKEN')
                val_gate = cookie_source.cookies.get('gate_dinamika_session')
                val_sso  = cookie_source.cookies.get('SSO_TOKEN')

            query = """
                INSERT INTO gate_sessions 
                (gate_user_id, xsrf_token, gate_session, sso_token, user_agent, is_valid, last_checked_at)
                VALUES (%s, %s, %s, %s, %s, 1, NOW())
                ON DUPLICATE KEY UPDATE
                    xsrf_token = VALUES(xsrf_token),
                    gate_session = VALUES(gate_session),
                    sso_token = VALUES(sso_token),
                    user_agent = VALUES(user_agent),
                    is_valid = 1,
                    last_checked_at = NOW(),
                    updated_at = NOW()
            """
            cursor.execute(query, (gate_user_id, val_xsrf, val_gate, val_sso, user_agent))
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"[GateSession] Gagal save cookies: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
    # --- TAMBAHAN BARU: DELETE SESSION ---
    def delete_session_by_user_id(self, user_id):
        """
        Menghapus sesi dari tabel gate_sessions berdasarkan user_id (Parent User).
        """
        conn = self._get_connection()
        if not conn: return False
        
        cursor = conn.cursor()
        try:
            # Hapus session milik gate_user yang terhubung dengan user_id ini
            query = """
                DELETE s 
                FROM gate_sessions s
                INNER JOIN gate_users u ON s.gate_user_id = u.id
                WHERE u.user_id = %s
            """
            cursor.execute(query, (user_id,))
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"[GateSession] Gagal delete session user {user_id}: {e}")
            return False
        finally:
            cursor.close()
            conn.close()
            
