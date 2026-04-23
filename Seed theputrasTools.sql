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

-- Default Tindak Lanjut
INSERT INTO konselor_tindak_lanjut (nama) VALUES ('Monitoring') ON DUPLICATE KEY UPDATE nama = VALUES(nama);
INSERT INTO konselor_tindak_lanjut (nama) VALUES ('Terminasi Sementara') ON DUPLICATE KEY UPDATE nama = VALUES(nama);
INSERT INTO konselor_tindak_lanjut (nama) VALUES ('Rujuk ke Pihak Lain') ON DUPLICATE KEY UPDATE nama = VALUES(nama);
