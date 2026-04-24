# models/konselor.py
# Model untuk fitur Pencatatan Sesi Konseling

import logging
from connection import get_connection


class KategoriMasalahModel:
    """CRUD untuk master data Kategori Masalah."""

    def _get_connection(self):
        return get_connection()

    def get_all(self):
        """Ambil semua kategori masalah."""
        conn = self._get_connection()
        if not conn:
            return []
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT id, nama FROM konselor_kategori_masalah ORDER BY id")
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"[Konselor] Error get_all kategori: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def create(self, nama):
        """Tambah kategori baru."""
        conn = self._get_connection()
        if not conn:
            return False, "Gagal koneksi database."
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO konselor_kategori_masalah (nama) VALUES (%s)",
                (nama.strip(),)
            )
            conn.commit()
            return True, "Kategori berhasil ditambahkan."
        except Exception as e:
            if 'Duplicate' in str(e):
                return False, "Kategori sudah ada."
            logging.error(f"[Konselor] Error create kategori: {e}")
            return False, "Gagal menambah kategori."
        finally:
            cursor.close()
            conn.close()

    def update(self, kategori_id, nama):
        """Update nama kategori."""
        conn = self._get_connection()
        if not conn:
            return False, "Gagal koneksi database."
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE konselor_kategori_masalah SET nama = %s WHERE id = %s",
                (nama.strip(), kategori_id)
            )
            conn.commit()
            return True, "Kategori berhasil diperbarui."
        except Exception as e:
            if 'Duplicate' in str(e):
                return False, "Nama kategori sudah digunakan."
            logging.error(f"[Konselor] Error update kategori: {e}")
            return False, "Gagal memperbarui kategori."
        finally:
            cursor.close()
            conn.close()

    def delete(self, kategori_id):
        """Hapus kategori. Gagal jika masih dipakai di sesi."""
        conn = self._get_connection()
        if not conn:
            return False, "Gagal koneksi database."
        cursor = conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM konselor_kategori_masalah WHERE id = %s",
                (kategori_id,)
            )
            conn.commit()
            if cursor.rowcount == 0:
                return False, "Kategori tidak ditemukan."
            return True, "Kategori berhasil dihapus."
        except Exception as e:
            if 'foreign key' in str(e).lower() or 'restrict' in str(e).lower():
                return False, "Kategori masih digunakan di data sesi. Tidak bisa dihapus."
            logging.error(f"[Konselor] Error delete kategori: {e}")
            return False, "Gagal menghapus kategori."
        finally:
            cursor.close()
            conn.close()


class JenisLayananModel:
    """CRUD untuk master data Jenis Layanan."""

    def _get_connection(self):
        return get_connection()

    def get_all(self):
        """Ambil semua jenis layanan."""
        conn = self._get_connection()
        if not conn:
            return []
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT id, nama FROM konselor_jenis_layanan ORDER BY id")
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"[Konselor] Error get_all layanan: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def create(self, nama):
        """Tambah jenis layanan baru."""
        conn = self._get_connection()
        if not conn:
            return False, "Gagal koneksi database."
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO konselor_jenis_layanan (nama) VALUES (%s)",
                (nama.strip(),)
            )
            conn.commit()
            return True, "Jenis layanan berhasil ditambahkan."
        except Exception as e:
            if 'Duplicate' in str(e):
                return False, "Jenis layanan sudah ada."
            logging.error(f"[Konselor] Error create layanan: {e}")
            return False, "Gagal menambah jenis layanan."
        finally:
            cursor.close()
            conn.close()

    def update(self, layanan_id, nama):
        """Update nama jenis layanan."""
        conn = self._get_connection()
        if not conn:
            return False, "Gagal koneksi database."
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE konselor_jenis_layanan SET nama = %s WHERE id = %s",
                (nama.strip(), layanan_id)
            )
            conn.commit()
            return True, "Jenis layanan berhasil diperbarui."
        except Exception as e:
            if 'Duplicate' in str(e):
                return False, "Nama layanan sudah digunakan."
            logging.error(f"[Konselor] Error update layanan: {e}")
            return False, "Gagal memperbarui jenis layanan."
        finally:
            cursor.close()
            conn.close()

    def delete(self, layanan_id):
        """Hapus jenis layanan. Gagal jika masih dipakai di sesi."""
        conn = self._get_connection()
        if not conn:
            return False, "Gagal koneksi database."
        cursor = conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM konselor_jenis_layanan WHERE id = %s",
                (layanan_id,)
            )
            conn.commit()
            if cursor.rowcount == 0:
                return False, "Jenis layanan tidak ditemukan."
            return True, "Jenis layanan berhasil dihapus."
        except Exception as e:
            if 'foreign key' in str(e).lower() or 'restrict' in str(e).lower():
                return False, "Jenis layanan masih digunakan di data sesi. Tidak bisa dihapus."
            logging.error(f"[Konselor] Error delete layanan: {e}")
            return False, "Gagal menghapus jenis layanan."
        finally:
            cursor.close()
            conn.close()


class TindakLanjutModel:
    """CRUD untuk master data Tindak Lanjut."""

    def _get_connection(self):
        return get_connection()

    def get_all(self):
        """Ambil semua tindak lanjut."""
        conn = self._get_connection()
        if not conn:
            return []
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT id, nama FROM konselor_tindak_lanjut ORDER BY id")
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"[Konselor] Error get_all tindak_lanjut: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def create(self, nama):
        """Tambah tindak lanjut baru."""
        conn = self._get_connection()
        if not conn:
            return False, "Gagal koneksi database."
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO konselor_tindak_lanjut (nama) VALUES (%s)",
                (nama.strip(),)
            )
            conn.commit()
            return True, "Tindak lanjut berhasil ditambahkan."
        except Exception as e:
            if 'Duplicate' in str(e):
                return False, "Tindak lanjut sudah ada."
            logging.error(f"[Konselor] Error create tindak_lanjut: {e}")
            return False, "Gagal menambah tindak lanjut."
        finally:
            cursor.close()
            conn.close()

    def update(self, tl_id, nama):
        """Update nama tindak lanjut."""
        conn = self._get_connection()
        if not conn:
            return False, "Gagal koneksi database."
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE konselor_tindak_lanjut SET nama = %s WHERE id = %s",
                (nama.strip(), tl_id)
            )
            conn.commit()
            return True, "Tindak lanjut berhasil diperbarui."
        except Exception as e:
            if 'Duplicate' in str(e):
                return False, "Nama tindak lanjut sudah digunakan."
            logging.error(f"[Konselor] Error update tindak_lanjut: {e}")
            return False, "Gagal memperbarui tindak lanjut."
        finally:
            cursor.close()
            conn.close()

    def delete(self, tl_id):
        """Hapus tindak lanjut. Gagal jika masih dipakai di sesi."""
        conn = self._get_connection()
        if not conn:
            return False, "Gagal koneksi database."
        cursor = conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM konselor_tindak_lanjut WHERE id = %s",
                (tl_id,)
            )
            conn.commit()
            if cursor.rowcount == 0:
                return False, "Tindak lanjut tidak ditemukan."
            return True, "Tindak lanjut berhasil dihapus."
        except Exception as e:
            if 'foreign key' in str(e).lower() or 'restrict' in str(e).lower():
                return False, "Tindak lanjut masih digunakan di data sesi. Tidak bisa dihapus."
            logging.error(f"[Konselor] Error delete tindak_lanjut: {e}")
            return False, "Gagal menghapus tindak lanjut."
        finally:
            cursor.close()
            conn.close()


class KonselorSessionModel:
    """Model untuk data sesi konseling."""

    def _get_connection(self):
        return get_connection()

    def create_session(self, data):
        """Simpan sesi konseling baru."""
        conn = self._get_connection()
        if not conn:
            return False, "Gagal koneksi database."
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO konselor_sessions
                (konselor_user_id, nim_id, nama, dosen_wali, prodi, jenis_layanan_id, topik, tanggal_sesi, tindak_lanjut_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                data['konselor_user_id'],
                data['nim_id'],
                data.get('nama'),
                data.get('dosen_wali'),
                data.get('prodi'),
                data['jenis_layanan_id'],
                data['topik'],
                data['tanggal_sesi'],
                data.get('tindak_lanjut_id')
            ))
            
            session_id = cursor.fetchone()[0]
            kategori_ids = data.get('kategori_masalah_ids', [])
            if kategori_ids:
                mapped_values = [(session_id, int(k_id)) for k_id in kategori_ids if k_id]
                if mapped_values:
                    cursor.executemany(
                        "INSERT INTO konselor_session_kategori (session_id, kategori_id) VALUES (%s, %s)",
                        mapped_values
                    )
            
            conn.commit()
            return True, "Sesi konseling berhasil disimpan."
        except Exception as e:
            logging.error(f"[Konselor] Error create_session: {e}")
            return False, f"Gagal menyimpan sesi: {str(e)}"
        finally:
            cursor.close()
            conn.close()

    def get_sessions_by_konselor(self, user_id, bulan=None, tahun=None):
        """Ambil daftar sesi milik konselor tertentu, opsional filter bulan/tahun."""
        conn = self._get_connection()
        if not conn:
            return []
        cursor = conn.cursor(dictionary=True)
        try:
            query = """
                SELECT s.id, s.nim_id, s.nama, s.dosen_wali, s.prodi, s.topik, s.tanggal_sesi, s.tindak_lanjut_id, s.created_at,
                       s.jenis_layanan_id,
                       STRING_AGG(km.id::text, ',') AS kategori_masalah_id,
                       jl.nama AS jenis_layanan, STRING_AGG(km.nama, ', ') AS kategori_masalah, tl.nama AS tindak_lanjut
                FROM konselor_sessions s
                LEFT JOIN konselor_jenis_layanan jl ON s.jenis_layanan_id = jl.id
                LEFT JOIN konselor_session_kategori sk ON s.id = sk.session_id
                LEFT JOIN konselor_kategori_masalah km ON sk.kategori_id = km.id
                LEFT JOIN konselor_tindak_lanjut tl ON s.tindak_lanjut_id = tl.id
                WHERE s.konselor_user_id = %s
            """
            params = [user_id]

            if bulan and tahun:
                query += " AND EXTRACT(MONTH FROM s.tanggal_sesi) = %s AND EXTRACT(YEAR FROM s.tanggal_sesi) = %s"
                params.extend([bulan, tahun])
            elif tahun:
                query += " AND EXTRACT(YEAR FROM s.tanggal_sesi) = %s"
                params.append(tahun)

            query += " GROUP BY s.id, jl.nama, tl.nama ORDER BY s.tanggal_sesi DESC, s.created_at DESC"
            cursor.execute(query, tuple(params))
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"[Konselor] Error get_sessions: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def get_rekap_stats(self, user_id, tahun=None):
        """
        Hitung statistik rekap:
        - Total sesi
        - Klien unik (distinct nim_id)
        - Sesi bulan ini
        - Distribusi per kategori masalah (untuk pie chart)
        """
        conn = self._get_connection()
        if not conn:
            return None
        cursor = conn.cursor(dictionary=True)
        try:
            # Total sesi & klien unik (all time atau per tahun)
            if tahun:
                cursor.execute("""
                    SELECT COUNT(*) AS total_sesi,
                           COUNT(DISTINCT nim_id) AS klien_unik
                    FROM konselor_sessions
                    WHERE konselor_user_id = %s AND EXTRACT(YEAR FROM tanggal_sesi) = %s
                """, (user_id, tahun))
            else:
                cursor.execute("""
                    SELECT COUNT(*) AS total_sesi,
                           COUNT(DISTINCT nim_id) AS klien_unik
                    FROM konselor_sessions
                    WHERE konselor_user_id = %s
                """, (user_id,))
            totals = cursor.fetchone()

            # Sesi bulan ini
            cursor.execute("""
                SELECT COUNT(*) AS sesi_bulan_ini
                FROM konselor_sessions
                WHERE konselor_user_id = %s
                  AND EXTRACT(MONTH FROM tanggal_sesi) = EXTRACT(MONTH FROM CURRENT_DATE)
                  AND EXTRACT(YEAR FROM tanggal_sesi) = EXTRACT(YEAR FROM CURRENT_DATE)
            """, (user_id,))
            bulan_ini = cursor.fetchone()

            # Distribusi per kategori
            if tahun:
                cursor.execute("""
                    SELECT km.nama AS kategori, COUNT(sk.session_id) AS jumlah
                    FROM konselor_session_kategori sk
                    JOIN konselor_kategori_masalah km ON sk.kategori_id = km.id
                    JOIN konselor_sessions s ON sk.session_id = s.id
                    WHERE s.konselor_user_id = %s AND EXTRACT(YEAR FROM s.tanggal_sesi) = %s
                    GROUP BY km.nama
                    ORDER BY jumlah DESC
                """, (user_id, tahun))
            else:
                cursor.execute("""
                    SELECT km.nama AS kategori, COUNT(sk.session_id) AS jumlah
                    FROM konselor_session_kategori sk
                    JOIN konselor_kategori_masalah km ON sk.kategori_id = km.id
                    JOIN konselor_sessions s ON sk.session_id = s.id
                    WHERE s.konselor_user_id = %s
                    GROUP BY km.nama
                    ORDER BY jumlah DESC
                """, (user_id,))
            kategori_dist = cursor.fetchall()

            # Distribusi per jenis layanan
            if tahun:
                cursor.execute("""
                    SELECT jl.nama AS layanan, COUNT(s.id) AS jumlah
                    FROM konselor_sessions s
                    LEFT JOIN konselor_jenis_layanan jl ON s.jenis_layanan_id = jl.id
                    WHERE s.konselor_user_id = %s AND EXTRACT(YEAR FROM s.tanggal_sesi) = %s
                    GROUP BY jl.nama
                    ORDER BY jumlah DESC
                """, (user_id, tahun))
            else:
                cursor.execute("""
                    SELECT jl.nama AS layanan, COUNT(s.id) AS jumlah
                    FROM konselor_sessions s
                    LEFT JOIN konselor_jenis_layanan jl ON s.jenis_layanan_id = jl.id
                    WHERE s.konselor_user_id = %s
                    GROUP BY jl.nama
                    ORDER BY jumlah DESC
                """, (user_id,))
            layanan_dist = cursor.fetchall()

            return {
                'total_sesi': totals['total_sesi'] if totals else 0,
                'klien_unik': totals['klien_unik'] if totals else 0,
                'sesi_bulan_ini': bulan_ini['sesi_bulan_ini'] if bulan_ini else 0,
                'kategori_distribusi': kategori_dist,
                'layanan_distribusi': layanan_dist
            }
        except Exception as e:
            logging.error(f"[Konselor] Error get_rekap_stats: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    def update_session(self, session_id, user_id, data):
        """Update sesi konseling (ownership check). NIM tidak bisa diubah."""
        conn = self._get_connection()
        if not conn:
            return False, "Gagal koneksi database."
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE konselor_sessions
                SET prodi = %s,
                    jenis_layanan_id = %s,
                    topik = %s,
                    tanggal_sesi = %s,
                    tindak_lanjut_id = %s
                WHERE id = %s AND konselor_user_id = %s
            """, (
                data.get('prodi'),
                data['jenis_layanan_id'],
                data['topik'],
                data['tanggal_sesi'],
                data.get('tindak_lanjut_id'),
                session_id,
                user_id
            ))
            
            if cursor.rowcount > 0 or True:
                # Update mapping kategori
                cursor.execute("DELETE FROM konselor_session_kategori WHERE session_id = %s", (session_id,))
                kategori_ids = data.get('kategori_masalah_ids', [])
                if kategori_ids:
                    mapped_values = [(session_id, int(k_id)) for k_id in kategori_ids if k_id]
                    if mapped_values:
                        cursor.executemany(
                            "INSERT INTO konselor_session_kategori (session_id, kategori_id) VALUES (%s, %s)",
                            mapped_values
                        )
                conn.commit()
                return True, "Sesi berhasil diperbarui."
            else:
                conn.rollback()
                return False, "Sesi tidak ditemukan atau Anda tidak memiliki akses."
        except Exception as e:
            logging.error(f"[Konselor] Error update_session: {e}")
            return False, f"Gagal memperbarui sesi: {str(e)}"
        finally:
            cursor.close()
            conn.close()

    def delete_session(self, session_id, user_id):
        """Hapus sesi (ownership check)."""
        conn = self._get_connection()
        if not conn:
            return False, "Gagal koneksi database."
        cursor = conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM konselor_sessions WHERE id = %s AND konselor_user_id = %s",
                (session_id, user_id)
            )
            conn.commit()
            if cursor.rowcount == 0:
                return False, "Sesi tidak ditemukan atau Anda tidak memiliki akses."
            return True, "Sesi berhasil dihapus."
        except Exception as e:
            logging.error(f"[Konselor] Error delete_session: {e}")
            return False, "Gagal menghapus sesi."
        finally:
            cursor.close()
            conn.close()


# Instances
kategori_masalah_model = KategoriMasalahModel()
jenis_layanan_model = JenisLayananModel()
tindak_lanjut_model = TindakLanjutModel()
konselor_session_model = KonselorSessionModel()
