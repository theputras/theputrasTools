-- ==========================================================
-- SEED DATA: TOOLS & PERMISSIONS
-- ==========================================================

-- Tool: Manajemen Ultah
INSERT INTO tools (nama_tool, route_name, deskripsi) 
VALUES ('Manajemen Ultah', 'manajemen_ultah', 'Kelola data ulang tahun & sync ke Google Calendar')
ON CONFLICT (route_name) DO UPDATE SET nama_tool = EXCLUDED.nama_tool, deskripsi = EXCLUDED.deskripsi;

-- Tool: Pembayaran QRIS
INSERT INTO tools (nama_tool, route_name, deskripsi) 
VALUES ('Pembayaran QRIS', 'pembayaran_qris', 'Generate QRIS via iPaymu untuk pembayaran')
ON CONFLICT (route_name) DO UPDATE SET nama_tool = EXCLUDED.nama_tool, deskripsi = EXCLUDED.deskripsi;

-- Tool: Cari Komunitas
INSERT INTO tools (nama_tool, route_name, deskripsi) 
VALUES ('Cari Komunitas', 'cari_komunitas', 'Pencarian data mahasiswa/staff')
ON CONFLICT (route_name) DO UPDATE SET nama_tool = EXCLUDED.nama_tool, deskripsi = EXCLUDED.deskripsi;

-- Tool: Log Program
INSERT INTO tools (nama_tool, route_name, deskripsi) 
VALUES ('Log Program', 'log_program', 'Catatan update sistem (Changelog)')
ON CONFLICT (route_name) DO UPDATE SET nama_tool = EXCLUDED.nama_tool, deskripsi = EXCLUDED.deskripsi;

-- Tool: Sosmed Download
INSERT INTO tools (nama_tool, route_name, deskripsi) 
VALUES ('Sosmed Downloader', 'sosmed_download', 'Unduh media sosial')
ON CONFLICT (route_name) DO UPDATE SET nama_tool = EXCLUDED.nama_tool, deskripsi = EXCLUDED.deskripsi;

-- Tool: Logbook Magang
INSERT INTO tools (nama_tool, route_name, deskripsi) 
VALUES ('Logbook Magang', 'logbook_magang', 'Catat kegiatan harian & eksport ke Word')
ON CONFLICT (route_name) DO UPDATE SET nama_tool = EXCLUDED.nama_tool, deskripsi = EXCLUDED.deskripsi;

-- ==========================================================
-- SEED DATA: RAMADHAN
-- ==========================================================

-- Seed: Ramadhan 1447 H (2026)
INSERT INTO ramadan_config (hijri_year, start_ramadan_muhammadiyah, start_ramadan_pemerintah, total_days)
VALUES (1447, '2026-02-17', '2026-02-18', 30)
ON CONFLICT (hijri_year) DO UPDATE SET hijri_year = EXCLUDED.hijri_year;

-- ==========================================================
-- SEED DATA: ROLE KONSELOR
-- ==========================================================

-- Role: Admin (id = 1)
INSERT INTO roles (id, nama_role, deskripsi)
VALUES (1, 'Admin', 'Administrator sistem')
ON CONFLICT (id) DO UPDATE SET nama_role = EXCLUDED.nama_role, deskripsi = EXCLUDED.deskripsi;

-- Role: Dosen (id = 2) --> [TAMBAHAN BARU UNTUK MENGHINDARI FK ERROR]
INSERT INTO roles (id, nama_role, deskripsi)
VALUES (2, 'Dosen', 'User Dosen')
ON CONFLICT (id) DO UPDATE SET nama_role = EXCLUDED.nama_role, deskripsi = EXCLUDED.deskripsi;

-- Role: Mahasiswa (id = 3)
INSERT INTO roles (id, nama_role, deskripsi)
VALUES (3, 'Mahasiswa', 'User mahasiswa (default)')
ON CONFLICT (id) DO UPDATE SET nama_role = EXCLUDED.nama_role, deskripsi = EXCLUDED.deskripsi;

-- Role: Konselor (id = 5)
INSERT INTO roles (id, nama_role, deskripsi)
VALUES (5, 'Konselor', 'Konselor mahasiswa — akses ke dashboard konseling')
ON CONFLICT (id) DO UPDATE SET nama_role = EXCLUDED.nama_role, deskripsi = EXCLUDED.deskripsi;

-- ==========================================================
-- SEED DATA: USER KONSELOR (fitriyah)
-- ==========================================================

-- Password: fit8872 (bcrypt hashed)
INSERT INTO users (username, email, password, role_id)
VALUES ('fitriyah', 'fitriyah@dinamika.ac.id', '$2b$12$xewcwtKsmLirZwdZOGhVt.XS2hgbeaoc1qlA1cot4ozs0CONowsOe', 5)
ON CONFLICT (username) DO UPDATE SET email = EXCLUDED.email, role_id = EXCLUDED.role_id;

-- ==========================================================
-- SEED DATA: ROLE PERMISSIONS (Siapa aja yang bisa ngontak tools)
-- ==========================================================

-- Admin (Role 1) bisa akses semua tools
INSERT INTO role_permissions (role_id, tool_id, is_allowed)
SELECT 1, id, 1 FROM tools ON CONFLICT DO NOTHING;

-- Dosen (Role 2) bisa akses Cari Komunitas, Manajemen Ultah, Sosmed Download
INSERT INTO role_permissions (role_id, tool_id, is_allowed)
SELECT 2, id, 1 FROM tools WHERE route_name IN ('cari_komunitas', 'manajemen_ultah', 'sosmed_download') ON CONFLICT DO NOTHING;

-- Mahasiswa (Role 3) bisa akses Logbook Magang, Cari Komunitas, Sosmed Download
INSERT INTO role_permissions (role_id, tool_id, is_allowed)
SELECT 3, id, 1 FROM tools WHERE route_name IN ('logbook_magang', 'cari_komunitas', 'sosmed_download') ON CONFLICT DO NOTHING;

-- ==========================================================
-- SEED DATA: MASTER KONSELOR (Kategori Masalah & Jenis Layanan)
-- ==========================================================

-- Default Kategori Masalah
INSERT INTO konselor_kategori_masalah (nama) VALUES ('Pribadi') ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama;
INSERT INTO konselor_kategori_masalah (nama) VALUES ('Sosial') ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama;
INSERT INTO konselor_kategori_masalah (nama) VALUES ('Keluarga') ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama;
INSERT INTO konselor_kategori_masalah (nama) VALUES ('Akademik') ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama;

-- Default Jenis Layanan
INSERT INTO konselor_jenis_layanan (nama) VALUES ('Konseling Individu') ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama;
INSERT INTO konselor_jenis_layanan (nama) VALUES ('Konseling Kelompok') ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama;
INSERT INTO konselor_jenis_layanan (nama) VALUES ('Bimbingan Kelompok') ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama;
INSERT INTO konselor_jenis_layanan (nama) VALUES ('Konsultasi') ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama;
INSERT INTO konselor_jenis_layanan (nama) VALUES ('Mediasi') ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama;

-- Default Tindak Lanjut
INSERT INTO konselor_tindak_lanjut (nama) VALUES ('Monitoring') ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama;
INSERT INTO konselor_tindak_lanjut (nama) VALUES ('Terminasi Sementara') ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama;
INSERT INTO konselor_tindak_lanjut (nama) VALUES ('Rujuk ke Pihak Lain') ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama;