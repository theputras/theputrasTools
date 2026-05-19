# models/mbti.py
# Model untuk fitur Tes Kepribadian MBTI

import logging
from connection import get_connection


class MBTIQuestionModel:
    """CRUD untuk pertanyaan MBTI."""

    def _get_connection(self):
        return get_connection()

    def get_all_active(self):
        """Ambil semua pertanyaan aktif, urut sort_order."""
        conn = self._get_connection()
        if not conn: return []
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM mbti_questions WHERE is_active = 1 ORDER BY sort_order ASC, id ASC")
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"[MBTI] Error get_all_active: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def get_all(self):
        """Ambil semua pertanyaan (termasuk nonaktif) untuk admin."""
        conn = self._get_connection()
        if not conn: return []
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM mbti_questions ORDER BY sort_order ASC, id ASC")
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"[MBTI] Error get_all: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def create(self, data):
        conn = self._get_connection()
        if not conn: return False, "Gagal koneksi database."
        cursor = conn.cursor()
        try:
            cursor.execute(
                """INSERT INTO mbti_questions (question_text, dimension, choice_a, choice_b, sort_order, is_active)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                (data['question_text'], data['dimension'], data['choice_a'], data['choice_b'],
                 data.get('sort_order', 0), data.get('is_active', 1))
            )
            new_id = cursor.fetchone()[0]
            conn.commit()
            return True, new_id
        except Exception as e:
            logging.error(f"[MBTI] Error create question: {e}")
            return False, str(e)
        finally:
            cursor.close()
            conn.close()

    def update(self, q_id, data):
        conn = self._get_connection()
        if not conn: return False, "Gagal koneksi database."
        cursor = conn.cursor()
        try:
            cursor.execute(
                """UPDATE mbti_questions SET question_text=%s, dimension=%s, choice_a=%s, choice_b=%s,
                   sort_order=%s, is_active=%s WHERE id=%s""",
                (data['question_text'], data['dimension'], data['choice_a'], data['choice_b'],
                 data.get('sort_order', 0), data.get('is_active', 1), q_id)
            )
            conn.commit()
            return True, "Pertanyaan berhasil diperbarui."
        except Exception as e:
            logging.error(f"[MBTI] Error update question: {e}")
            return False, str(e)
        finally:
            cursor.close()
            conn.close()

    def delete(self, q_id):
        conn = self._get_connection()
        if not conn: return False, "Gagal koneksi database."
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM mbti_questions WHERE id = %s", (q_id,))
            conn.commit()
            return cursor.rowcount > 0, "Pertanyaan berhasil dihapus." if cursor.rowcount > 0 else "Pertanyaan tidak ditemukan."
        except Exception as e:
            logging.error(f"[MBTI] Error delete question: {e}")
            return False, str(e)
        finally:
            cursor.close()
            conn.close()


class MBTIResultInfoModel:
    """Ambil informasi detail tipe kepribadian MBTI."""

    def _get_connection(self):
        return get_connection()

    def get_by_type(self, mbti_type):
        conn = self._get_connection()
        if not conn: return None
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM mbti_results_info WHERE mbti_type = %s", (mbti_type.upper(),))
            return cursor.fetchone()
        except Exception as e:
            logging.error(f"[MBTI] Error get_by_type: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    def get_all(self):
        conn = self._get_connection()
        if not conn: return []
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM mbti_results_info ORDER BY mbti_type")
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"[MBTI] Error get_all: {e}")
            return []
        finally:
            cursor.close()
            conn.close()


class MBTIConfigModel:
    """Kelola konfigurasi MBTI (interval retake, dll)."""

    def _get_connection(self):
        return get_connection()

    def get(self, key, default=None):
        conn = self._get_connection()
        if not conn: return default
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT config_value FROM mbti_configs WHERE config_key = %s", (key,))
            row = cursor.fetchone()
            return row['config_value'] if row else default
        except Exception as e:
            logging.error(f"[MBTI] Error get config: {e}")
            return default
        finally:
            cursor.close()
            conn.close()

    def set(self, key, value):
        conn = self._get_connection()
        if not conn: return False
        cursor = conn.cursor()
        try:
            cursor.execute(
                """INSERT INTO mbti_configs (config_key, config_value) VALUES (%s, %s)
                   ON CONFLICT (config_key) DO UPDATE SET config_value = EXCLUDED.config_value""",
                (key, str(value))
            )
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"[MBTI] Error set config: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def get_all(self):
        conn = self._get_connection()
        if not conn: return {}
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT config_key, config_value FROM mbti_configs")
            return {r['config_key']: r['config_value'] for r in cursor.fetchall()}
        except Exception as e:
            logging.error(f"[MBTI] Error get_all config: {e}")
            return {}
        finally:
            cursor.close()
            conn.close()


class MBTITestHistoryModel:
    """Model untuk riwayat tes MBTI mahasiswa."""

    def _get_connection(self):
        return get_connection()

    def save_result(self, data):
        """Simpan hasil tes MBTI."""
        conn = self._get_connection()
        if not conn: return None
        cursor = conn.cursor()
        try:
            cursor.execute(
                """INSERT INTO mbti_test_history
                   (user_id, id_civitas, score_e, score_i, score_s, score_n,
                    score_t, score_f, score_j, score_p, mbti_result)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (data['user_id'],
                 data.get('nim'),
                 data.get('score_e',0), data.get('score_i',0),
                 data.get('score_s',0), data.get('score_n',0),
                 data.get('score_t',0), data.get('score_f',0),
                 data.get('score_j',0), data.get('score_p',0),
                 data['mbti_result'])
            )
            history_id = cursor.fetchone()[0]
            conn.commit()

            # Sync hasil MBTI ke tabel konselor_data_klien
            try:
                from models.konselor import klien_model
                klien_model.upsert({
                    "id_civitas": data.get('nim'),
                    "nama": data.get('nama'),
                    "prodi": data.get('prodi'),
                    "mbti": history_id,
                    "status_civitas": "Mahasiswa"
                })
            except Exception as sync_err:
                logging.error(f"[MBTI] Gagal sync ke konselor_data_klien: {sync_err}")

            return history_id
        except Exception as e:
            logging.error(f"[MBTI] Error save_result: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    def get_by_id(self, history_id):
        conn = self._get_connection()
        if not conn: return None
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """SELECT h.*, 
                          COALESCE(h.id_civitas, dk.id_civitas, u.username) AS nim,
                          COALESCE(dk.nama, u.username) AS nama,
                          dk.prodi,
                          r.title, r.description, r.characteristics,
                          r.development_suggestions, r.suitable_professions
                   FROM mbti_test_history h
                   JOIN mbti_results_info r ON h.mbti_result = r.mbti_type
                   LEFT JOIN users u ON h.user_id = u.id
                   LEFT JOIN konselor_data_klien dk ON COALESCE(h.id_civitas, u.username) = dk.id_civitas
                   WHERE h.id = %s""", (history_id,))
            return cursor.fetchone()
        except Exception as e:
            logging.error(f"[MBTI] Error get_by_id: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    def get_latest_by_user(self, user_id):
        """Ambil tes terakhir milik user."""
        conn = self._get_connection()
        if not conn: return None
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """SELECT h.*, 
                          COALESCE(h.id_civitas, dk.id_civitas, u.username) AS nim,
                          COALESCE(dk.nama, u.username) AS nama,
                          dk.prodi,
                          r.title 
                   FROM mbti_test_history h
                   JOIN mbti_results_info r ON h.mbti_result = r.mbti_type
                   LEFT JOIN users u ON h.user_id = u.id
                   LEFT JOIN konselor_data_klien dk ON COALESCE(h.id_civitas, u.username) = dk.id_civitas
                   WHERE h.user_id = %s ORDER BY h.tested_at DESC LIMIT 1""", (user_id,))
            return cursor.fetchone()
        except Exception as e:
            logging.error(f"[MBTI] Error get_latest_by_user: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    def get_all_by_user(self, user_id):
        conn = self._get_connection()
        if not conn: return []
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """SELECT h.id, 
                          COALESCE(dk.nama, u.username) AS nama, 
                          COALESCE(h.id_civitas, dk.id_civitas, u.username) AS nim, 
                          dk.prodi, 
                          h.mbti_result, h.tested_at, r.title
                   FROM mbti_test_history h
                   JOIN mbti_results_info r ON h.mbti_result = r.mbti_type
                   LEFT JOIN users u ON h.user_id = u.id
                   LEFT JOIN konselor_data_klien dk ON COALESCE(h.id_civitas, u.username) = dk.id_civitas
                   WHERE h.user_id = %s ORDER BY h.tested_at DESC""", (user_id,))
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"[MBTI] Error get_all_by_user: {e}")
            return []
        finally:
            cursor.close()
            conn.close()


# Singleton instances
mbti_question_model = MBTIQuestionModel()
mbti_result_info_model = MBTIResultInfoModel()
mbti_config_model = MBTIConfigModel()
mbti_test_history_model = MBTITestHistoryModel()
