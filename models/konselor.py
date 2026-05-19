# models/konselor.py
# Model untuk fitur Pencatatan Sesi Konseling

import logging

from connection import get_connection


class KlienModel:
    """CRUD untuk master data Klien (Mahasiswa/Staff)."""

    def _get_connection(self):
        return get_connection()

    def get_all(self):
        conn = self._get_connection()
        if not conn: return []
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM konselor_data_klien ORDER BY nama ASC")
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"[Konselor] Error get_all klien: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def get_by_id_civitas(self, id_civitas):
        """Ambil satu data klien terbaru berdasarkan ID."""
        conn = self._get_connection()
        if not conn: return None
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM konselor_data_klien WHERE id_civitas = %s ORDER BY updated_at DESC", (id_civitas,))
            return cursor.fetchone()
        except Exception as e:
            logging.error(f"[Konselor] Error get_by_id_civitas: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    def get_all_by_id_civitas(self, id_civitas):
        """Ambil semua data klien yang memiliki ID yang sama (untuk 001/002)."""
        conn = self._get_connection()
        if not conn: return []
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM konselor_data_klien WHERE id_civitas = %s ORDER BY nama ASC", (id_civitas,))
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"[Konselor] Error get_all_by_id_civitas: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def search_klien(self, query):
        """Cari klien berdasarkan ID atau Nama (ILIKE)."""
        conn = self._get_connection()
        if not conn: return []
        cursor = conn.cursor(dictionary=True)
        try:
            q = f"%{query}%"
            cursor.execute("SELECT * FROM konselor_data_klien WHERE id_civitas LIKE %s OR nama ILIKE %s ORDER BY nama ASC LIMIT 50", (q, q))
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"[Konselor] Error search_klien: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def get_by_identity(self, id_civitas, nama):
        """Ambil data klien berdasarkan kombinasi ID dan Nama."""
        conn = self._get_connection()
        if not conn: return None
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM konselor_data_klien WHERE id_civitas = %s AND nama = %s", (id_civitas, (nama or "").strip()))
            return cursor.fetchone()
        except Exception as e:
            logging.error(f"[Konselor] Error get_by_identity: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    def upsert(self, data):
        """Tambah atau update data klien (id_civitas + nama sebagai key). Mengembalikan ID klien."""
        conn = self._get_connection()
        if not conn: return None
        cursor = conn.cursor()
        try:
            sql = """
                INSERT INTO konselor_data_klien (id_civitas, nama, prodi, dosen_wali, mbti, status_abk, status_civitas)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id_civitas, nama) DO UPDATE SET
                    prodi = EXCLUDED.prodi,
                    dosen_wali = EXCLUDED.dosen_wali,
                    mbti = COALESCE(EXCLUDED.mbti, konselor_data_klien.mbti),
                    status_abk = COALESCE(EXCLUDED.status_abk, konselor_data_klien.status_abk),
                    status_civitas = EXCLUDED.status_civitas,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            """
            cursor.execute(sql, (
                data.get('id_civitas'),
                data.get('nama'),
                data.get('prodi'),
                data.get('dosen_wali'),
                data.get('mbti'),
                data.get('status_abk'),
                data.get('status_civitas', 'Mahasiswa')
            ))
            client_id = cursor.fetchone()[0]
            conn.commit()
            return client_id
        except Exception as e:
            logging.error(f"[Konselor] Error upsert klien: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    def update_metadata(self, id_civitas, nama, metadata):
        """Update metadata khusus seperti MBTI atau ABK."""
        conn = self._get_connection()
        if not conn: return False
        cursor = conn.cursor()
        try:
            fields = []
            values = []
            for k, v in metadata.items():
                fields.append(f"{k} = %s")
                values.append(v)
            values.append(id_civitas)
            values.append((nama or "").strip())
            
            sql = f"UPDATE konselor_data_klien SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP WHERE id_civitas = %s AND nama = %s"
            cursor.execute(sql, tuple(values))
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"[Konselor] Error update_metadata klien: {e}")
            return False
        finally:
            cursor.close()
            conn.close()


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
                (nama.strip(),),
            )
            conn.commit()
            return True, "Kategori berhasil ditambahkan."
        except Exception as e:
            if "Duplicate" in str(e):
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
                (nama.strip(), kategori_id),
            )
            conn.commit()
            return True, "Kategori berhasil diperbarui."
        except Exception as e:
            if "Duplicate" in str(e):
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
                "DELETE FROM konselor_kategori_masalah WHERE id = %s", (kategori_id,)
            )
            conn.commit()
            if cursor.rowcount == 0:
                return False, "Kategori tidak ditemukan."
            return True, "Kategori berhasil dihapus."
        except Exception as e:
            if "foreign key" in str(e).lower() or "restrict" in str(e).lower():
                return (
                    False,
                    "Kategori masih digunakan di data sesi. Tidak bisa dihapus.",
                )
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
        """Ambil semua jenis layanan beserta value_jenislayanan."""
        conn = self._get_connection()
        if not conn:
            return []
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT id, nama, value_jenislayanan FROM konselor_jenis_layanan ORDER BY id")
            rows = cursor.fetchall()
            # Parse JSONB value_jenislayanan jika masih string
            import json as _json
            for r in rows:
                val = r.get('value_jenislayanan')
                if isinstance(val, str):
                    try:
                        r['value_jenislayanan'] = _json.loads(val)
                    except Exception:
                        r['value_jenislayanan'] = {}
                elif val is None:
                    r['value_jenislayanan'] = {}
            return rows
        except Exception as e:
            logging.error(f"[Konselor] Error get_all layanan: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def create(self, nama, value_jenislayanan=None):
        """Tambah jenis layanan baru dengan opsional value_jenislayanan (JSON)."""
        import json as _json
        conn = self._get_connection()
        if not conn:
            return False, "Gagal koneksi database."
        cursor = conn.cursor()
        try:
            val_json = _json.dumps(value_jenislayanan) if value_jenislayanan else '{}'
            cursor.execute(
                "INSERT INTO konselor_jenis_layanan (nama, value_jenislayanan) VALUES (%s, %s::jsonb)",
                (nama.strip(), val_json),
            )
            conn.commit()
            return True, "Jenis layanan berhasil ditambahkan."
        except Exception as e:
            if "Duplicate" in str(e):
                return False, "Jenis layanan sudah ada."
            logging.error(f"[Konselor] Error create layanan: {e}")
            return False, "Gagal menambah jenis layanan."
        finally:
            cursor.close()
            conn.close()

    def update(self, layanan_id, nama, value_jenislayanan=None):
        """Update nama dan value_jenislayanan jenis layanan."""
        import json as _json
        conn = self._get_connection()
        if not conn:
            return False, "Gagal koneksi database."
        cursor = conn.cursor()
        try:
            if value_jenislayanan is not None:
                val_json = _json.dumps(value_jenislayanan)
                cursor.execute(
                    "UPDATE konselor_jenis_layanan SET nama = %s, value_jenislayanan = %s::jsonb WHERE id = %s",
                    (nama.strip(), val_json, layanan_id),
                )
            else:
                cursor.execute(
                    "UPDATE konselor_jenis_layanan SET nama = %s WHERE id = %s",
                    (nama.strip(), layanan_id),
                )
            conn.commit()
            return True, "Jenis layanan berhasil diperbarui."
        except Exception as e:
            if "Duplicate" in str(e):
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
                "DELETE FROM konselor_jenis_layanan WHERE id = %s", (layanan_id,)
            )
            conn.commit()
            if cursor.rowcount == 0:
                return False, "Jenis layanan tidak ditemukan."
            return True, "Jenis layanan berhasil dihapus."
        except Exception as e:
            if "foreign key" in str(e).lower() or "restrict" in str(e).lower():
                return (
                    False,
                    "Jenis layanan masih digunakan di data sesi. Tidak bisa dihapus.",
                )
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
                "INSERT INTO konselor_tindak_lanjut (nama) VALUES (%s)", (nama.strip(),)
            )
            conn.commit()
            return True, "Tindak lanjut berhasil ditambahkan."
        except Exception as e:
            if "Duplicate" in str(e):
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
                (nama.strip(), tl_id),
            )
            conn.commit()
            return True, "Tindak lanjut berhasil diperbarui."
        except Exception as e:
            if "Duplicate" in str(e):
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
            cursor.execute("DELETE FROM konselor_tindak_lanjut WHERE id = %s", (tl_id,))
            conn.commit()
            if cursor.rowcount == 0:
                return False, "Tindak lanjut tidak ditemukan."
            return True, "Tindak lanjut berhasil dihapus."
        except Exception as e:
            if "foreign key" in str(e).lower() or "restrict" in str(e).lower():
                return (
                    False,
                    "Tindak lanjut masih digunakan di data sesi. Tidak bisa dihapus.",
                )
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
            cursor.execute(
                """
                INSERT INTO konselor_sessions
                (konselor_user_id, id_klien, jenis_layanan_id, topik, tanggal_sesi, waktu_mulai, waktu_selesai, tindak_lanjut_id, catatan_kesimpulan)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """,
                (
                    data["konselor_user_id"],
                    data["id_klien"],
                    data["jenis_layanan_id"],
                    data["topik"],
                    data["tanggal_sesi"],
                    data.get("waktu_mulai"),
                    data.get("waktu_selesai"),
                    data.get("tindak_lanjut_id"),
                    data.get("catatan_kesimpulan"),
                ),
            )

            session_id = cursor.fetchone()[0]
            kategori_ids = data.get("kategori_masalah_ids", [])
            if kategori_ids:
                mapped_values = [
                    (session_id, int(k_id)) for k_id in kategori_ids if k_id
                ]
                if mapped_values:
                    cursor.executemany(
                        "INSERT INTO konselor_session_kategori (session_id, kategori_id) VALUES (%s, %s)",
                        mapped_values,
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
        """Ambil daftar sesi milik konselor tertentu, opsional filter bulan/tahun dengan metadata klien."""
        conn = self._get_connection()
        if not conn:
            return []
        cursor = conn.cursor(dictionary=True)
        try:
            query = """
                SELECT s.id, s.id_klien, dk.id_civitas as nim_id, dk.nama, dk.dosen_wali, dk.prodi, s.topik, s.tanggal_sesi, s.waktu_mulai, s.waktu_selesai, s.tindak_lanjut_id, s.catatan_kesimpulan, s.created_at,
                       s.jenis_layanan_id,
                       dk.nama as nama_klien, dk.prodi as prodi_klien, dk.dosen_wali as dosen_wali_klien,
                       dk.mbti, dk.status_abk, dk.status_civitas,
                       STRING_AGG(DISTINCT km.id::text, ',') AS kategori_masalah_id,
                       jl.nama AS jenis_layanan, STRING_AGG(DISTINCT km.nama, ', ') AS kategori_masalah, tl.nama AS tindak_lanjut
                FROM konselor_sessions s
                LEFT JOIN konselor_jenis_layanan jl ON s.jenis_layanan_id = jl.id
                LEFT JOIN konselor_session_kategori sk ON s.id = sk.session_id
                LEFT JOIN konselor_kategori_masalah km ON sk.kategori_id = km.id
                LEFT JOIN konselor_tindak_lanjut tl ON s.tindak_lanjut_id = tl.id
                JOIN konselor_data_klien dk ON s.id_klien = dk.id
            """
            params = []
            group_by = """
                GROUP BY s.id, dk.id, jl.nama, tl.nama
                ORDER BY s.tanggal_sesi DESC, s.id DESC
            """

            if bulan and tahun:
                query += " AND EXTRACT(MONTH FROM s.tanggal_sesi) = %s AND EXTRACT(YEAR FROM s.tanggal_sesi) = %s"
                params.extend([bulan, tahun])
            elif tahun:
                query += " AND EXTRACT(YEAR FROM s.tanggal_sesi) = %s"
                params.append(tahun)

            query += group_by
            cursor.execute(query, tuple(params))
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"[Konselor] Error get_sessions: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def get_rekap_stats(self, user_id=None, tahun=None):
        """
        Hitung statistik rekap GLOBAL:
        - Total sesi
        - Klien unik (distinct id_klien)
        - Sesi bulan ini
        - Distribusi per kategori masalah
        - Distribusi per jenis layanan
        - Distribusi per prodi
        """
        conn = self._get_connection()
        if not conn:
            return None
        cursor = conn.cursor(dictionary=True)
        try:
            # 1. Total sesi & klien unik
            if tahun:
                cursor.execute(
                    """
                    SELECT COUNT(*) AS total_sesi,
                           COUNT(DISTINCT id_klien) AS klien_unik
                    FROM konselor_sessions
                    WHERE EXTRACT(YEAR FROM tanggal_sesi) = %s
                """,
                    (tahun,),
                )
            else:
                cursor.execute(
                    """
                    SELECT COUNT(*) AS total_sesi,
                           COUNT(DISTINCT id_klien) AS klien_unik
                    FROM konselor_sessions
                """,
                    (),
                )
            totals = cursor.fetchone()

            # 2. Sesi bulan ini
            cursor.execute(
                """
                SELECT
                    (SELECT COUNT(*)
                     FROM konselor_sessions
                     WHERE EXTRACT(MONTH FROM tanggal_sesi) = EXTRACT(MONTH FROM CURRENT_DATE)
                       AND EXTRACT(YEAR FROM tanggal_sesi) = EXTRACT(YEAR FROM CURRENT_DATE)
                    )
                    +
                    (SELECT COUNT(*)
                     FROM konselor_jadwal
                     WHERE status IN ('Menunggu', 'Berlangsung')
                       AND EXTRACT(MONTH FROM tanggal) = EXTRACT(MONTH FROM CURRENT_DATE)
                       AND EXTRACT(YEAR FROM tanggal) = EXTRACT(YEAR FROM CURRENT_DATE)
                    ) AS sesi_bulan_ini
            """,
                (),
            )
            bulan_ini = cursor.fetchone()

            # 3. Distribusi per kategori
            if tahun:
                cursor.execute(
                    """
                    SELECT km.nama AS kategori, COUNT(sk.session_id) AS jumlah
                    FROM konselor_session_kategori sk
                    JOIN konselor_kategori_masalah km ON sk.kategori_id = km.id
                    JOIN konselor_sessions s ON sk.session_id = s.id
                    WHERE EXTRACT(YEAR FROM s.tanggal_sesi) = %s
                    GROUP BY km.nama
                    ORDER BY jumlah DESC
                """,
                    (tahun,),
                )
            else:
                cursor.execute(
                    """
                    SELECT km.nama AS kategori, COUNT(sk.session_id) AS jumlah
                    FROM konselor_session_kategori sk
                    JOIN konselor_kategori_masalah km ON sk.kategori_id = km.id
                    GROUP BY km.nama
                    ORDER BY jumlah DESC
                """
                )
            kategori_dist = cursor.fetchall()

            # 4. Distribusi per jenis layanan
            if tahun:
                cursor.execute(
                    """
                    SELECT jl.nama AS layanan, COUNT(s.id) AS jumlah
                    FROM konselor_sessions s
                    LEFT JOIN konselor_jenis_layanan jl ON s.jenis_layanan_id = jl.id
                    WHERE EXTRACT(YEAR FROM s.tanggal_sesi) = %s
                    GROUP BY jl.nama
                    ORDER BY jumlah DESC
                """,
                    (tahun,),
                )
            else:
                cursor.execute(
                    """
                    SELECT jl.nama AS layanan, COUNT(s.id) AS jumlah
                    FROM konselor_sessions s
                    LEFT JOIN konselor_jenis_layanan jl ON s.jenis_layanan_id = jl.id
                    GROUP BY jl.nama
                    ORDER BY jumlah DESC
                """
                )
            layanan_dist = cursor.fetchall()

            # 5. Distribusi per Prodi
            if tahun:
                cursor.execute(
                    """
                    SELECT COALESCE(dk.prodi, 'Lainnya/Staff') AS prodi, COUNT(s.id) AS jumlah
                    FROM konselor_sessions s
                    JOIN konselor_data_klien dk ON s.id_klien = dk.id
                    WHERE EXTRACT(YEAR FROM s.tanggal_sesi) = %s
                    GROUP BY dk.prodi
                    ORDER BY jumlah DESC
                """,
                    (tahun,),
                )
            else:
                cursor.execute(
                    """
                    SELECT COALESCE(dk.prodi, 'Lainnya/Staff') AS prodi, COUNT(s.id) AS jumlah
                    FROM konselor_sessions s
                    JOIN konselor_data_klien dk ON s.id_klien = dk.id
                    GROUP BY dk.prodi
                    ORDER BY jumlah DESC
                """
                )
            prodi_dist = cursor.fetchall()

            return {
                "total_sesi": totals["total_sesi"] if totals else 0,
                "klien_unik": totals["klien_unik"] if totals else 0,
                "sesi_bulan_ini": bulan_ini["sesi_bulan_ini"] if bulan_ini else 0,
                "kategori_distribusi": kategori_dist,
                "layanan_distribusi": layanan_dist,
                "prodi_distribusi": prodi_dist,
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
            cursor.execute(
                """
                UPDATE konselor_sessions
                SET jenis_layanan_id = %s,
                    topik = %s,
                    tanggal_sesi = %s,
                    tindak_lanjut_id = %s,
                    catatan_kesimpulan = %s
                WHERE id = %s AND konselor_user_id = %s
            """,
                (
                    data["jenis_layanan_id"],
                    data["topik"],
                    data["tanggal_sesi"],
                    data.get("tindak_lanjut_id"),
                    data.get("catatan_kesimpulan"),
                    session_id,
                    user_id,
                ),
            )

            if cursor.rowcount > 0 or True:
                # Update mapping kategori
                cursor.execute(
                    "DELETE FROM konselor_session_kategori WHERE session_id = %s",
                    (session_id,),
                )
                kategori_ids = data.get("kategori_masalah_ids", [])
                if kategori_ids:
                    mapped_values = [
                        (session_id, int(k_id)) for k_id in kategori_ids if k_id
                    ]
                    if mapped_values:
                        cursor.executemany(
                            "INSERT INTO konselor_session_kategori (session_id, kategori_id) VALUES (%s, %s)",
                            mapped_values,
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
                (session_id, user_id),
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


class KonselorJadwalModel:
    """Model untuk penjadwalan konseling."""

    def _get_connection(self):
        return get_connection()

    def create(self, data):
        conn = self._get_connection()
        if not conn:
            return False, "Gagal koneksi database."
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO konselor_jadwal (konselor_user_id, id_klien, layanan_id, tanggal, jam, status)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """,
                (
                    data["konselor_user_id"],
                    data["id_klien"],
                    data["layanan_id"],
                    data["tanggal"],
                    data["jam"],
                    data.get("status", "Menunggu"),
                ),
            )
            conn.commit()
            return True, "Jadwal berhasil dibuat."
        except Exception as e:
            logging.error(f"[Konselor] Error create_jadwal: {e}")
            return False, "Gagal membuat jadwal."
        finally:
            cursor.close()
            conn.close()

    def get_by_konselor_and_date_range(self, user_id, start_date, end_date=None):
        conn = self._get_connection()
        if not conn:
            return []
        cursor = conn.cursor(dictionary=True)
        try:
            if end_date:
                query = """
                    SELECT j.*, l.nama as layanan, dk.id_civitas as nim, dk.nama, dk.prodi
                    FROM konselor_jadwal j
                    LEFT JOIN konselor_jenis_layanan l ON j.layanan_id = l.id
                    JOIN konselor_data_klien dk ON j.id_klien = dk.id
                    WHERE j.tanggal >= %s AND j.tanggal <= %s
                    ORDER BY j.tanggal ASC, j.jam ASC
                """
                cursor.execute(query, (start_date, end_date))
            else:
                query = """
                    SELECT j.*, l.nama as layanan, dk.id_civitas as nim, dk.nama, dk.prodi
                    FROM konselor_jadwal j
                    LEFT JOIN konselor_jenis_layanan l ON j.layanan_id = l.id
                    JOIN konselor_data_klien dk ON j.id_klien = dk.id
                    WHERE j.tanggal >= %s
                    ORDER BY j.tanggal ASC, j.jam ASC
                """
                cursor.execute(query, (start_date,))
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"[Konselor] Error get_jadwal: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def get_by_id(self, jadwal_id):
        conn = self._get_connection()
        if not conn:
            return None
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT j.*, l.nama as layanan, dk.id_civitas as nim, dk.nama, dk.prodi
                FROM konselor_jadwal j
                LEFT JOIN konselor_jenis_layanan l ON j.layanan_id = l.id
                JOIN konselor_data_klien dk ON j.id_klien = dk.id
                WHERE j.id = %s
            """,
                (jadwal_id,),
            )
            return cursor.fetchone()
        except Exception as e:
            logging.error(f"[Konselor] Error get_jadwal_by_id: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    def update_waktu(self, jadwal_id, user_id, tanggal, jam):
        conn = self._get_connection()
        if not conn:
            return False, "Gagal koneksi database."
        cursor = conn.cursor()
        try:
            group_subquery = """
                SELECT j2.id FROM konselor_jadwal j2 
                JOIN konselor_jadwal j1 ON j1.id = %s::INT 
                WHERE j2.konselor_user_id = j1.konselor_user_id
                  AND j2.layanan_id = j1.layanan_id
                  AND j2.tanggal = j1.tanggal
                  AND j2.jam = j1.jam
            """
            cursor.execute(f"""
                UPDATE konselor_jadwal
                SET tanggal = %s, jam = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id IN ({group_subquery}) AND konselor_user_id = %s::BIGINT
            """, (tanggal, jam, jadwal_id, user_id))
            
            if cursor.rowcount > 0:
                conn.commit()
                return True, "Jadwal berhasil di-reschedule."
            else:
                conn.rollback()
                return False, "Jadwal tidak ditemukan atau bukan milik Anda."
        except Exception as e:
            logging.error(f"[Konselor] Error reschedule: {e}")
            return False, "Gagal melakukan reschedule."
        finally:
            cursor.close()
            conn.close()

    def get_all_by_konselor(self, user_id):
        """Ambil semua jadwal konselor (riwayat lengkap), diurutkan terbaru dulu."""
        conn = self._get_connection()
        if not conn:
            return []
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT j.*, l.nama AS layanan, dk.id_civitas as nim, dk.nama, dk.prodi
                FROM konselor_jadwal j
                LEFT JOIN konselor_jenis_layanan l ON j.layanan_id = l.id
                JOIN konselor_data_klien dk ON j.id_klien = dk.id
                ORDER BY j.tanggal DESC, j.jam ASC
            """,
                (),
            )
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"[Konselor] Error get_all_jadwal: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def get_public_schedules(self, start_date, end_date=None):
        """Ambil jadwal untuk rentang tanggal tertentu (semua konselor) untuk tampilan publik."""
        conn = self._get_connection()
        if not conn:
            return []
        cursor = conn.cursor(dictionary=True)
        try:
            if end_date:
                query = """
                    SELECT j.*, l.nama as layanan, dk.id_civitas as nim, dk.nama, dk.prodi
                    FROM konselor_jadwal j
                    LEFT JOIN konselor_jenis_layanan l ON j.layanan_id = l.id
                    LEFT JOIN konselor_data_klien dk ON j.id_klien = dk.id
                    WHERE j.tanggal >= %s AND j.tanggal <= %s AND j.status NOT IN ('Dibatalkan')
                    ORDER BY j.tanggal ASC, j.jam ASC
                """
                cursor.execute(query, (start_date, end_date))
            else:
                query = """
                    SELECT j.*, l.nama as layanan, dk.id_civitas as nim, dk.nama, dk.prodi
                    FROM konselor_jadwal j
                    LEFT JOIN konselor_jenis_layanan l ON j.layanan_id = l.id
                    LEFT JOIN konselor_data_klien dk ON j.id_klien = dk.id
                    WHERE j.tanggal >= %s AND j.status NOT IN ('Dibatalkan')
                    ORDER BY j.tanggal ASC, j.jam ASC
                """
                cursor.execute(query, (start_date,))
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"[Konselor] Error get_public_schedules: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def get_grouped_jadwal(self, jadwal_id, user_id):
        conn = self._get_connection()
        if not conn: return []
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT j2.*, l.nama as layanan, dk.id_civitas as nim, dk.nama, dk.prodi
                FROM konselor_jadwal j1
                JOIN konselor_jadwal j2 ON j1.konselor_user_id = j2.konselor_user_id 
                                       AND j1.layanan_id = j2.layanan_id 
                                       AND j1.tanggal = j2.tanggal 
                                       AND j1.jam = j2.jam
                LEFT JOIN konselor_jenis_layanan l ON j2.layanan_id = l.id
                JOIN konselor_data_klien dk ON j2.id_klien = dk.id
                WHERE j1.id = %s AND j1.konselor_user_id = %s
                ORDER BY j2.id ASC
            """, (jadwal_id, user_id))
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"[Konselor] Error get_grouped_jadwal: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def takeover_live_session(self, jadwal_id, user_id):
        import uuid
        conn = self._get_connection()
        if not conn: return False, "Gagal koneksi", None
        cursor = conn.cursor()
        try:
            token = str(uuid.uuid4())
            # Update seluruh jadwal dalam group yang sama menjadi Berlangsung, set token, dan catat last_active
            cursor.execute("""
                UPDATE konselor_jadwal
                SET status = 'Berlangsung',
                    conselling_token = %s,
                    conselling_last_active = CURRENT_TIMESTAMP,
                    waktu_mulai = COALESCE(waktu_mulai, CURRENT_TIMESTAMP),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id IN (
                    SELECT j2.id FROM konselor_jadwal j2 
                    JOIN konselor_jadwal j1 ON j1.id = %s::INT 
                    WHERE j2.konselor_user_id = j1.konselor_user_id
                      AND j2.layanan_id = j1.layanan_id
                      AND j2.tanggal = j1.tanggal
                      AND j2.jam = j1.jam
                ) AND konselor_user_id = %s::BIGINT
            """, (token, jadwal_id, user_id))
            conn.commit()
            return True, "Sesi berhasil diambil alih", token
        except Exception as e:
            logging.error(f"[Konselor] Error takeover_live_session: {e}")
            return False, "Gagal ambil alih sesi", None
        finally:
            cursor.close()
            conn.close()

    def check_token(self, jadwal_id, user_id, token):
        conn = self._get_connection()
        if not conn: return False
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT conselling_token FROM konselor_jadwal WHERE id = %s AND konselor_user_id = %s", (jadwal_id, user_id))
            row = cursor.fetchone()
            if row and row[0] == token:
                return True
            return False
        except Exception as e:
            logging.error(f"[Konselor] Error check_token: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def update_status(self, jadwal_id, user_id, status, token=None):
        conn = self._get_connection()
        if not conn:
            return False, "Gagal koneksi database."
        cursor = conn.cursor()
        try:
            if token is not None:
                cursor.execute("SELECT conselling_token FROM konselor_jadwal WHERE id = %s AND konselor_user_id = %s", (jadwal_id, user_id))
                row = cursor.fetchone()
                if row and row[0] and row[0] != token:
                    return False, "Sesi telah diambil alih oleh perangkat lain. Silakan muat ulang halaman."

            group_subquery = """
                SELECT j2.id FROM konselor_jadwal j2 
                JOIN konselor_jadwal j1 ON j1.id = %s::INT 
                WHERE j2.konselor_user_id = j1.konselor_user_id
                  AND j2.layanan_id = j1.layanan_id
                  AND j2.tanggal = j1.tanggal
                  AND j2.jam = j1.jam
            """

            if status == "Berlangsung":
                cursor.execute(f"""
                    UPDATE konselor_jadwal
                    SET status = %s,
                        total_pause_ms = CASE WHEN last_pause_time IS NOT NULL
                                              THEN COALESCE(total_pause_ms, 0) + (EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - last_pause_time)) * 1000)::BIGINT
                                              ELSE COALESCE(total_pause_ms, 0) END,
                        last_pause_time = NULL,
                        waktu_mulai = COALESCE(waktu_mulai, CURRENT_TIMESTAMP),
                        conselling_last_active = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id IN ({group_subquery}) AND konselor_user_id = %s::BIGINT
                """, (status, jadwal_id, user_id))
            elif status == "Jeda":
                cursor.execute(f"""
                    UPDATE konselor_jadwal
                    SET status = %s,
                        last_pause_time = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id IN ({group_subquery}) AND konselor_user_id = %s::BIGINT
                """, (status, jadwal_id, user_id))
            else:
                cursor.execute(f"""
                    UPDATE konselor_jadwal
                    SET status = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id IN ({group_subquery}) AND konselor_user_id = %s::BIGINT
                """, (status, jadwal_id, user_id))

            if cursor.rowcount > 0:
                conn.commit()
                return True, f"Status diperbarui menjadi {status}."
            else:
                conn.rollback()
                return False, "Jadwal tidak ditemukan."
        except Exception as e:
            logging.error(f"[Konselor] Error update_status: {e}")
            return False, "Gagal memperbarui status."
        finally:
            cursor.close()
            conn.close()


class KonselorRolePermissionModel:
    """Model untuk manajemen hak akses dinamis per role per halaman di Konselor App."""

    def _get_connection(self):
        return get_connection()

    def get_permissions_by_role(self, role_id):
        """Ambil semua permission untuk role tertentu. Return dict {page_identifier: {can_view, can_create, ...}}."""
        conn = self._get_connection()
        if not conn:
            return {}
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT * FROM konselor_role_permissions WHERE role_id = %s",
                (role_id,),
            )
            rows = cursor.fetchall()
            result = {}
            for r in rows:
                result[r["page_identifier"]] = {
                    "can_view": r["can_view"],
                    "can_create": r["can_create"],
                    "can_update": r["can_update"],
                    "can_delete": r["can_delete"],
                    "can_import": r["can_import"],
                    "can_export": r["can_export"],
                    "data_scope": r["data_scope"],
                }
            return result
        except Exception as e:
            logging.error(f"[KonselorPerm] Error get_permissions_by_role: {e}")
            return {}
        finally:
            cursor.close()
            conn.close()

    def get_all_permissions(self):
        """Ambil semua permission untuk semua role (untuk halaman admin kelola akses)."""
        conn = self._get_connection()
        if not conn:
            return []
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT krp.*, r.nama_role
                FROM konselor_role_permissions krp
                JOIN roles r ON krp.role_id = r.id
                ORDER BY krp.role_id, krp.page_identifier
            """)
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"[KonselorPerm] Error get_all_permissions: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def upsert_permission(self, role_id, page_identifier, data):
        """Insert atau update permission untuk role + halaman tertentu."""
        conn = self._get_connection()
        if not conn:
            return False, "Gagal koneksi database."
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO konselor_role_permissions
                    (role_id, page_identifier, can_view, can_create, can_update, can_delete, can_import, can_export, data_scope)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (role_id, page_identifier) DO UPDATE SET
                    can_view = EXCLUDED.can_view,
                    can_create = EXCLUDED.can_create,
                    can_update = EXCLUDED.can_update,
                    can_delete = EXCLUDED.can_delete,
                    can_import = EXCLUDED.can_import,
                    can_export = EXCLUDED.can_export,
                    data_scope = EXCLUDED.data_scope
            """, (
                role_id,
                page_identifier,
                data.get("can_view", 0),
                data.get("can_create", 0),
                data.get("can_update", 0),
                data.get("can_delete", 0),
                data.get("can_import", 0),
                data.get("can_export", 0),
                data.get("data_scope", "OWN"),
            ))
            conn.commit()
            return True, "Permission berhasil disimpan."
        except Exception as e:
            logging.error(f"[KonselorPerm] Error upsert_permission: {e}")
            return False, f"Gagal menyimpan permission: {str(e)}"
        finally:
            cursor.close()
            conn.close()

    def get_accessible_pages(self, role_id):
        """Return list of page_identifier yang boleh diakses (can_view=1) oleh role tertentu."""
        conn = self._get_connection()
        if not conn:
            return []
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT page_identifier FROM konselor_role_permissions WHERE role_id = %s AND can_view = 1",
                (role_id,),
            )
            return [r["page_identifier"] for r in cursor.fetchall()]
        except Exception as e:
            logging.error(f"[KonselorPerm] Error get_accessible_pages: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def check_permission(self, role_id, page_identifier, action="can_view"):
        """Cek apakah role punya izin untuk action tertentu di halaman tertentu."""
        conn = self._get_connection()
        if not conn:
            return False, "NONE"
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT * FROM konselor_role_permissions WHERE role_id = %s AND page_identifier = %s",
                (role_id, page_identifier),
            )
            row = cursor.fetchone()
            if not row:
                return False, "NONE"
            return bool(row.get(action, 0)), row.get("data_scope", "NONE")
        except Exception as e:
            logging.error(f"[KonselorPerm] Error check_permission: {e}")
            return False, "NONE"
        finally:
            cursor.close()
            conn.close()


class KonselorUserModel:
    """Model untuk manajemen user khusus Konselor App (tabel konselor_users)."""

    def _get_connection(self):
        return get_connection()

    def get_by_source_user_id(self, source_user_id):
        """Cari user konselor berdasarkan ID user utama (untuk middleware auth)."""
        conn = self._get_connection()
        if not conn:
            return None
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """SELECT ku.*, r.nama_role
                   FROM konselor_users ku
                   JOIN roles r ON ku.role_id = r.id
                   WHERE ku.source_user_id = %s""",
                (source_user_id,),
            )
            return cursor.fetchone()
        except Exception as e:
            logging.error(f"[KonselorUser] Error get_by_source_user_id: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    def get_all(self):
        """Ambil semua user konselor."""
        conn = self._get_connection()
        if not conn:
            return []
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT ku.*, r.nama_role
                FROM konselor_users ku
                LEFT JOIN roles r ON ku.role_id = r.id
                ORDER BY ku.role_id, ku.username
            """)
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"[KonselorUser] Error get_all: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

    def add_from_main_user(self, source_user_id, konselor_role_id):
        """Copy user dari tabel users utama ke konselor_users dengan role konselor."""
        conn = self._get_connection()
        if not conn:
            return False, "Gagal koneksi database."
        cursor = conn.cursor(dictionary=True)
        try:
            # Cek apakah sudah ada
            cursor.execute(
                "SELECT id FROM konselor_users WHERE source_user_id = %s",
                (source_user_id,),
            )
            if cursor.fetchone():
                return False, "User sudah terdaftar di Konselor App."

            # Ambil data dari users utama
            cursor.execute(
                "SELECT id, username, password, email FROM users WHERE id = %s",
                (source_user_id,),
            )
            main_user = cursor.fetchone()
            if not main_user:
                return False, "User tidak ditemukan di tabel utama."

            # Insert ke konselor_users
            cursor.execute("""
                INSERT INTO konselor_users (source_user_id, username, password, email, role_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                main_user["id"],
                main_user["username"],
                main_user["password"],
                main_user["email"],
                konselor_role_id,
            ))
            conn.commit()
            return True, f"User '{main_user['username']}' berhasil ditambahkan ke Konselor App."
        except Exception as e:
            logging.error(f"[KonselorUser] Error add_from_main_user: {e}")
            return False, f"Gagal menambahkan user: {str(e)}"
        finally:
            cursor.close()
            conn.close()

    def update_role(self, konselor_user_id, new_role_id):
        """Update role konselor untuk user tertentu."""
        conn = self._get_connection()
        if not conn:
            return False, "Gagal koneksi database."
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE konselor_users SET role_id = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (new_role_id, konselor_user_id),
            )
            conn.commit()
            return True, "Role berhasil diperbarui."
        except Exception as e:
            logging.error(f"[KonselorUser] Error update_role: {e}")
            return False, f"Gagal update role: {str(e)}"
        finally:
            cursor.close()
            conn.close()

    def remove(self, konselor_user_id):
        """Hapus user dari konselor_users (tidak menghapus dari users utama)."""
        conn = self._get_connection()
        if not conn:
            return False, "Gagal koneksi database."
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM konselor_users WHERE id = %s", (konselor_user_id,))
            conn.commit()
            return True, "User berhasil dihapus dari Konselor App."
        except Exception as e:
            logging.error(f"[KonselorUser] Error remove: {e}")
            return False, f"Gagal menghapus user: {str(e)}"
        finally:
            cursor.close()
            conn.close()

    def search_main_users(self, query=""):
        """Cari user dari tabel utama (untuk dropdown tambah user)."""
        conn = self._get_connection()
        if not conn:
            return []
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT u.id, u.username, u.email, u.role_id, r.nama_role,
                       CASE WHEN ku.id IS NOT NULL THEN 1 ELSE 0 END AS already_added
                FROM users u
                LEFT JOIN roles r ON u.role_id = r.id
                LEFT JOIN konselor_users ku ON u.id = ku.source_user_id
                WHERE u.username ILIKE %s OR u.email ILIKE %s
                ORDER BY u.username
                LIMIT 20
            """, (f"%{query}%", f"%{query}%"))
            return cursor.fetchall()
        except Exception as e:
            logging.error(f"[KonselorUser] Error search_main_users: {e}")
            return []
        finally:
            cursor.close()
            conn.close()


# Instances
kategori_masalah_model = KategoriMasalahModel()
jenis_layanan_model = JenisLayananModel()
tindak_lanjut_model = TindakLanjutModel()
konselor_session_model = KonselorSessionModel()
klien_model = KlienModel()
konselor_jadwal_model = KonselorJadwalModel()
konselor_role_permission_model = KonselorRolePermissionModel()
konselor_user_model = KonselorUserModel()


