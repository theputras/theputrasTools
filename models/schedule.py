from connection import get_connection
import logging

class UserSchedule:
    @staticmethod
    def _get_connection():
        return get_connection()

    @staticmethod
    def save_schedules(user_id, last_scraped, schedules_list):
        """
        Schedules_list is a list of dicts: 
        [{ 'Hari, Tanggal': '...', 'Jam': '...', 'Ruang': '...', 'Nama Matakuliah': '...', 'Dosen': '...' }]
        """
        conn = UserSchedule._get_connection()
        if not conn:
            return False
            
        cursor = conn.cursor()
        try:
            # Update meta (last_scraped)
            query_meta = """
                INSERT INTO user_schedules_metadata (user_id, last_scraped) 
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE SET last_scraped = EXCLUDED.last_scraped
            """
            cursor.execute(query_meta, (user_id, last_scraped))

            # Delete old schedules
            cursor.execute("DELETE FROM user_schedules WHERE user_id = %s", (user_id,))

            # Insert new schedules
            if schedules_list:
                query_insert = """
                    INSERT INTO user_schedules (user_id, hari_tanggal, jam, ruang, mata_kuliah, dosen, status_kuliah, keterangan)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                # Mapping the keys from the scraped data
                data_to_insert = []
                for s in schedules_list:
                    data_to_insert.append((
                        user_id,
                        s.get('Hari, Tanggal', '-'),
                        s.get('Jam', '-'),
                        s.get('Ruangan', '-'), # Updated to match Sicyca's actual header
                        s.get('Nama Matakuliah', '-'),
                        s.get('Dosen', '-'), # No longer in Sicyca, defaults to -
                        s.get('Status Kuliah', '-'),
                        s.get('Keterangan', '-')
                    ))
                
                cursor.executemany(query_insert, data_to_insert)

            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logging.error(f"[UserSchedule] Error saving schedules for user_id {user_id}: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def get_schedules_by_user(user_id):
        conn = UserSchedule._get_connection()
        if not conn:
            return None, []
            
        cursor = conn.cursor(dictionary=True)
        try:
            # Get metadata
            cursor.execute("SELECT last_scraped FROM user_schedules_metadata WHERE user_id = %s", (user_id,))
            meta = cursor.fetchone()
            last_scraped = meta['last_scraped'] if meta else "Belum pernah di-scrape"

            # Get schedules
            cursor.execute("SELECT * FROM user_schedules WHERE user_id = %s ORDER BY id", (user_id,))
            rows = cursor.fetchall()
            
            # Map back to original json structure for compatibility with frontend/ICS gen if needed
            schedules = []
            for r in rows:
                schedules.append({
                    "Hari, Tanggal": r['hari_tanggal'],
                    "Jam": r['jam'],
                    "Ruangan": r['ruang'],
                    "Nama Matakuliah": r['mata_kuliah'],
                    "Dosen": r['dosen'],
                    "Status Kuliah": r['status_kuliah'],
                    "Keterangan": r['keterangan']
                })
                
            return last_scraped, schedules
        except Exception as e:
            logging.error(f"[UserSchedule] Error getting schedules for user_id {user_id}: {e}")
            return None, []
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def get_or_create_calendar_uuid(user_id):
        import uuid
        conn = UserSchedule._get_connection()
        if not conn:
            return None
            
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT kalendar_uuid FROM user_schedules_metadata WHERE user_id = %s", (user_id,))
            meta = cursor.fetchone()
            
            if meta and meta['kalendar_uuid']:
                return meta['kalendar_uuid']
                
            # Generate new UUID
            new_uuid = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO user_schedules_metadata (user_id, kalendar_uuid) 
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE SET kalendar_uuid = EXCLUDED.kalendar_uuid
            """, (user_id, new_uuid))
            conn.commit()
            return new_uuid
        except Exception as e:
            conn.rollback()
            logging.error(f"[UserSchedule] Error handling calendar UUID for user_id {user_id}: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def get_schedules_by_uuid(calendar_uuid):
        conn = UserSchedule._get_connection()
        if not conn:
            return None, [], None
            
        cursor = conn.cursor(dictionary=True)
        try:
            # First map UUID to user_id
            cursor.execute("SELECT user_id, last_scraped FROM user_schedules_metadata WHERE kalendar_uuid = %s", (calendar_uuid,))
            meta = cursor.fetchone()
            if not meta:
                return None, [], None
                
            user_id = meta['user_id']
            last_scraped = meta['last_scraped'] if meta['last_scraped'] else "Belum pernah di-scrape"

            # Fetch schedules with the mapped user_id
            cursor.execute("SELECT * FROM user_schedules WHERE user_id = %s ORDER BY id", (user_id,))
            rows = cursor.fetchall()
            
            schedules = []
            for r in rows:
                schedules.append({
                    "Hari, Tanggal": r['hari_tanggal'],
                    "Jam": r['jam'],
                    "Ruangan": r['ruang'],
                    "Nama Matakuliah": r['mata_kuliah'],
                    "Dosen": r['dosen'],
                    "Status Kuliah": r['status_kuliah'],
                    "Keterangan": r['keterangan']
                })
                
            return last_scraped, schedules, user_id
        except Exception as e:
            logging.error(f"[UserSchedule] Error getting schedules for UUID {calendar_uuid}: {e}")
            return None, [], None
        finally:
            cursor.close()
            conn.close()

user_schedule_model = UserSchedule()
