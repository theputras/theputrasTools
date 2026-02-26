# models/prayer.py
# Model untuk fitur Jadwal Sholat & Kalender Hijriah

import logging
from connection import get_connection


class UserPrayerSettings:
    """Model untuk preferensi sholat per-user (Muhammadiyah/NU, lokasi)."""

    def _get_connection(self):
        return get_connection()

    def get_by_user_id(self, user_id):
        """Ambil setting user. Return default kalau belum ada."""
        conn = self._get_connection()
        if not conn:
            return self._default_settings(user_id)

        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT * FROM user_prayer_settings WHERE user_id = %s",
                (user_id,)
            )
            result = cursor.fetchone()
            if result:
                return result
            return self._default_settings(user_id)
        except Exception as e:
            logging.error(f"[Prayer] Error get_by_user_id: {e}")
            return self._default_settings(user_id)
        finally:
            cursor.close()
            conn.close()

    def upsert(self, user_id, data):
        """Insert atau update preference user (UPSERT pattern)."""
        conn = self._get_connection()
        if not conn:
            return False

        cursor = conn.cursor()
        try:
            query = """
                INSERT INTO user_prayer_settings 
                (user_id, preference, city, state, country, hijri_adj)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    preference = VALUES(preference),
                    city = VALUES(city),
                    state = VALUES(state),
                    country = VALUES(country),
                    hijri_adj = VALUES(hijri_adj),
                    updated_at = NOW()
            """
            cursor.execute(query, (
                user_id,
                data.get('preference', 'nu'),
                data.get('city', 'Surabaya'),
                data.get('state', ''),
                data.get('country', 'Indonesia'),
                data.get('hijri_adj', 0)
            ))
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"[Prayer] Error upsert settings: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def _default_settings(self, user_id):
        """Return default settings kalau user belum pernah set."""
        return {
            'user_id': user_id,
            'preference': 'nu',
            'city': 'Surabaya',
            'state': '',
            'country': 'Indonesia',
            'hijri_adj': 0
        }


class RamadanConfig:
    """Model untuk konfigurasi tanggal Ramadhan (admin-only)."""

    def _get_connection(self):
        return get_connection()

    def get_by_hijri_year(self, hijri_year):
        """Ambil config Ramadhan per tahun Hijriah."""
        conn = self._get_connection()
        if not conn:
            return None

        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT * FROM ramadan_config WHERE hijri_year = %s",
                (hijri_year,)
            )
            return cursor.fetchone()
        except Exception as e:
            logging.error(f"[Prayer] Error get_by_hijri_year: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    def get_current(self):
        """
        Ambil config Ramadhan yang paling relevan.
        Logika: ambil config dengan tahun Hijriah terdekat.
        """
        conn = self._get_connection()
        if not conn:
            return None

        cursor = conn.cursor(dictionary=True)
        try:
            # Ambil config terbaru berdasarkan hijri_year DESC
            cursor.execute(
                "SELECT * FROM ramadan_config ORDER BY hijri_year DESC LIMIT 1"
            )
            return cursor.fetchone()
        except Exception as e:
            logging.error(f"[Prayer] Error get_current: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    def get_all(self):
        """List semua config Ramadhan (untuk admin panel)."""
        conn = self._get_connection()
        if not conn:
            return []

        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT * FROM ramadan_config ORDER BY hijri_year DESC"
            )
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"[Prayer] Error get_all: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def upsert(self, data, updated_by=None):
        """Insert atau update config Ramadhan (admin-only)."""
        conn = self._get_connection()
        if not conn:
            return False

        cursor = conn.cursor()
        try:
            query = """
                INSERT INTO ramadan_config 
                (hijri_year, start_ramadan_muhammadiyah, start_ramadan_pemerintah, total_days, updated_by)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    start_ramadan_muhammadiyah = VALUES(start_ramadan_muhammadiyah),
                    start_ramadan_pemerintah = VALUES(start_ramadan_pemerintah),
                    total_days = VALUES(total_days),
                    updated_by = VALUES(updated_by),
                    updated_at = NOW()
            """
            cursor.execute(query, (
                data.get('hijri_year'),
                data.get('start_ramadan_muhammadiyah'),
                data.get('start_ramadan_pemerintah'),
                data.get('total_days', 30),
                updated_by
            ))
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"[Prayer] Error upsert ramadan_config: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def delete(self, hijri_year):
        """Hapus config Ramadhan by hijri_year."""
        conn = self._get_connection()
        if not conn:
            return False

        cursor = conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM ramadan_config WHERE hijri_year = %s",
                (hijri_year,)
            )
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"[Prayer] Error delete ramadan_config: {e}")
            return False
        finally:
            cursor.close()
            conn.close()


# Instances
prayer_settings_model = UserPrayerSettings()
ramadan_config_model = RamadanConfig()
