-- ==========================================================
-- SEED DATA: TOOLS & PERMISSIONS
-- ==========================================================

-- Tool: Manajemen Ultah
INSERT INTO tools (nama_tool, route_name, deskripsi) 
VALUES ('Manajemen Ultah', 'manajemen_ultah', 'Kelola data ulang tahun & sync ke Google Calendar')
ON DUPLICATE KEY UPDATE nama_tool = VALUES(nama_tool), deskripsi = VALUES(deskripsi);

-- Tool: Pembayaran QRIS
INSERT INTO tools (nama_tool, route_name, deskripsi) 
VALUES ('Pembayaran QRIS', 'pembayaran_qris', 'Generate QRIS via iPaymu untuk pembayaran')
ON DUPLICATE KEY UPDATE nama_tool = VALUES(nama_tool), deskripsi = VALUES(deskripsi);

-- ==========================================================
-- SEED DATA: RAMADHAN
-- ==========================================================

-- Seed: Ramadhan 1447 H (2026)
INSERT INTO ramadan_config (hijri_year, start_ramadan_muhammadiyah, start_ramadan_pemerintah, total_days)
VALUES (1447, '2026-02-17', '2026-02-18', 30)
ON DUPLICATE KEY UPDATE hijri_year = VALUES(hijri_year);

-- ==========================================================
-- SEED DATA: ROLE KONSELOR
-- ==========================================================

-- Role: Konselor (id = 5)
INSERT INTO roles (id, nama_role, deskripsi)
VALUES (5, 'Konselor', 'Konselor mahasiswa — akses ke dashboard konseling')
ON DUPLICATE KEY UPDATE nama_role = VALUES(nama_role), deskripsi = VALUES(deskripsi);

-- ==========================================================
-- SEED DATA: USER KONSELOR (fitriyah)
-- ==========================================================

-- Password: fit8872 (bcrypt hashed)
INSERT INTO users (username, email, password, role_id)
VALUES ('fitriyah', 'fitriyah@dinamika.ac.id', '$2b$12$xewcwtKsmLirZwdZOGhVt.XS2hgbeaoc1qlA1cot4ozs0CONowsOe', 5)
ON DUPLICATE KEY UPDATE email = VALUES(email), role_id = VALUES(role_id);

-- ==========================================================
-- SEED DATA: MASTER KONSELOR (Kategori Masalah & Jenis Layanan)
-- ==========================================================

-- Default Kategori Masalah
INSERT INTO konselor_kategori_masalah (nama) VALUES ('Pribadi') ON DUPLICATE KEY UPDATE nama = VALUES(nama);
INSERT INTO konselor_kategori_masalah (nama) VALUES ('Sosial') ON DUPLICATE KEY UPDATE nama = VALUES(nama);
INSERT INTO konselor_kategori_masalah (nama) VALUES ('Keluarga') ON DUPLICATE KEY UPDATE nama = VALUES(nama);
INSERT INTO konselor_kategori_masalah (nama) VALUES ('Akademik') ON DUPLICATE KEY UPDATE nama = VALUES(nama);

-- Default Jenis Layanan
INSERT INTO konselor_jenis_layanan (nama) VALUES ('Konseling Individu') ON DUPLICATE KEY UPDATE nama = VALUES(nama);
INSERT INTO konselor_jenis_layanan (nama) VALUES ('Konseling Kelompok') ON DUPLICATE KEY UPDATE nama = VALUES(nama);
INSERT INTO konselor_jenis_layanan (nama) VALUES ('Bimbingan Kelompok') ON DUPLICATE KEY UPDATE nama = VALUES(nama);
INSERT INTO konselor_jenis_layanan (nama) VALUES ('Konsultasi') ON DUPLICATE KEY UPDATE nama = VALUES(nama);
INSERT INTO konselor_jenis_layanan (nama) VALUES ('Mediasi') ON DUPLICATE KEY UPDATE nama = VALUES(nama);


INSERT INTO konselor_sessions 
(konselor_user_id, nim_hash, nim_encrypted, prodi, jenis_layanan_id, kategori_masalah_id, topik, tanggal_sesi, tindak_lanjut) 
VALUES
-- 1. 24420100040
(11, SHA2('24420100040', 256), TO_BASE64(AES_ENCRYPT('24420100040', 'secret_key')), 'DKV', 1, 1, 'Gagal Move On', '2026-01-05', 'Monitoring'),

-- 2. 24410100064
(11, SHA2('24410100064', 256), TO_BASE64(AES_ENCRYPT('24410100064', 'secret_key')), 'SI', 1, 1, 'Gagal Move On', '2026-01-05', 'Monitoring'),

-- 3. 25410100066
(11, SHA2('25410100066', 256), TO_BASE64(AES_ENCRYPT('25410100066', 'secret_key')), 'SI', 1, 2, 'Adaptasi Sosial', '2026-01-05', 'Monitoring'),

-- 4. 19420100042
(11, SHA2('19420100042', 256), TO_BASE64(AES_ENCRYPT('19420100042', 'secret_key')), 'DKV', 2, 4, 'Progres Penyelesaian TA', '2026-01-05', 'Monitoring'),

-- 5. 24410100064
(11, SHA2('24410100064', 256), TO_BASE64(AES_ENCRYPT('24410100064', 'secret_key')), 'SI', 1, 1, 'Gagal Move On', '2026-01-06', 'Monitoring'),

-- 6. 24420100040
(11, SHA2('24420100040', 256), TO_BASE64(AES_ENCRYPT('24420100040', 'secret_key')), 'DKV', 1, 1, 'Gagal Move On', '2026-01-11', 'Monitoring'),

-- 7. 23410100003
(11, SHA2('23410100003', 256), TO_BASE64(AES_ENCRYPT('23410100003', 'secret_key')), 'SI', 1, 2, 'Problem Pertemanan', '2026-01-11', 'Monitoring'),

-- 8. 24420100040
(11, SHA2('24420100040', 256), TO_BASE64(AES_ENCRYPT('24420100040', 'secret_key')), 'DKV', 1, 4, 'Deadline Tugas dan Bingung Ide Tugas', '2026-01-12', 'Monitoring'),

-- 9. 24420100040
(11, SHA2('24420100040', 256), TO_BASE64(AES_ENCRYPT('24420100040', 'secret_key')), 'DKV', 1, 4, 'Stress Akademik dan Gagal Move On', '2026-01-13', 'Monitoring'),

-- 10. 23410100003
(11, SHA2('23410100003', 256), TO_BASE64(AES_ENCRYPT('23410100003', 'secret_key')), 'SI', 1, 2, 'Problem Pertemanan', '2026-01-14', 'Monitoring'),

-- 11. 24420100040
(11, SHA2('24420100040', 256), TO_BASE64(AES_ENCRYPT('24420100040', 'secret_key')), 'DKV', 1, 1, 'Gagal Move On', '2026-01-15', 'Monitoring'),

-- 12. 24420100040
(11, SHA2('24420100040', 256), TO_BASE64(AES_ENCRYPT('24420100040', 'secret_key')), 'DKV', 1, 1, 'Gagal Move On', '2026-01-16', 'Monitoring'),

-- 13. 25410100066
(11, SHA2('25410100066', 256), TO_BASE64(AES_ENCRYPT('25410100066', 'secret_key')), 'SI', 1, 3, 'Masalah keluarga', '2026-01-19', 'Monitoring'),

-- 14. 24410100064
(11, SHA2('24410100064', 256), TO_BASE64(AES_ENCRYPT('24410100064', 'secret_key')), 'SI', 1, 3, 'Masalah keluarga', '2026-01-20', 'Monitoring'),

-- 15. 24420100040
(11, SHA2('24420100040', 256), TO_BASE64(AES_ENCRYPT('24420100040', 'secret_key')), 'DKV', 1, 1, 'Gagal Move On', '2026-01-21', 'Monitoring'),

-- 16. 23410100003
(11, SHA2('23410100003', 256), TO_BASE64(AES_ENCRYPT('23410100003', 'secret_key')), 'SI', 1, 4, 'Bingung Perihal Magang', '2026-01-21', 'Monitoring'),

-- 17. 24420100040
(11, SHA2('24420100040', 256), TO_BASE64(AES_ENCRYPT('24420100040', 'secret_key')), 'DKV', 1, 4, 'Problem Pertemanan, Stress Tugas', '2026-01-22', 'Terminasi Sementara'),

-- 18. 19420100042
(11, SHA2('19420100042', 256), TO_BASE64(AES_ENCRYPT('19420100042', 'secret_key')), 'DKV', 2, 4, 'Progres Penyelesaian TA', '2026-01-05', 'Monitoring');