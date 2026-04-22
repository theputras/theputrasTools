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
(11, SHA2('24420100040', 256), 'gAAAAABp6HxQwooaU8Bb4BY7R69E6MQkYG-DC05VoUIwdudMv3yIIDpQRxQXlUjPcDz9d-FSZAKTy2mzAxbdG5nOmWtS5w9t4Q==', 'S1 Desain KomunikaS1 Sistem Informasi Visual', 1, 1, 'Gagal Move On', '2026-01-05', 'Monitoring'),

-- 2. 24410100064
(11, SHA2('24410100064', 256), 'gAAAAABp6HxQDRR7FTS0nN4okkgyOKb1BJ_jv5MXIsB-MP-RR-JofWeQg_N4r8fvIRT5j-PzNmlXM6OAQ-RPLRI2TQ8hqS0Nig==', 'S1 Sistem Informasi', 1, 1, 'Gagal Move On', '2026-01-05', 'Monitoring'),

-- 3. 25410100066
(11, SHA2('25410100066', 256), 'gAAAAABp6HxQpVSd_UMAHaE8c_aUayib2tn8gGo7zlGm40ANM4yr6Seb0fkb1Pyq3OV7TyQni_BGgHJmhAEVr83ULb7O9uyIgw==', 'S1 Sistem Informasi', 1, 2, 'AdaptaS1 Sistem Informasi SoS1 Sistem Informasial', '2026-01-05', 'Monitoring'),

-- 4. 19420100042
(11, SHA2('19420100042', 256), 'gAAAAABp6HxQD8Izq_6ozcfYI3kfTX6lF5R0FABoNbLc0soOvc3RTlHIMLcpaPly_2_Zo7q2EOyigypgNlu8X_1kLc0fmsvOPQ==', 'S1 Desain KomunikaS1 Sistem Informasi Visual', 2, 4, 'Progres Penyelesaian TA', '2026-01-05', 'Monitoring'),

-- 5. 24410100064
(11, SHA2('24410100064', 256), 'gAAAAABp6HxQ6YZFsKxg_GX9zqOwfCSrP2FYB2KL2vtOIJmthq3MVuoZNiZU9657kO3jw19Zaffk1iUNwVqmBgaC7juEcivKWw==', 'S1 Sistem Informasi', 1, 1, 'Gagal Move On', '2026-01-06', 'Monitoring'),

-- 6. 24420100040
(11, SHA2('24420100040', 256), 'gAAAAABp6HxQeODrHvWZ1NvCqcdaSqq9yHAu8UNUjQy8YZge1PBLrwwy-F0bLhwdbm6d0sX5YBpY_TpK2XtN0_rg5hIAiiX-jw==', 'S1 Desain KomunikaS1 Sistem Informasi Visual', 1, 1, 'Gagal Move On', '2026-01-11', 'Monitoring'),

-- 7. 23410100003
(11, SHA2('23410100003', 256), 'gAAAAABp6HxQ6cvc_AZNcL48PG0UFlGR9Z3EP465A-c2gO0V5BkYtFZnbqLoaitSzrt6VYq205XEOmGeVPQiU-f340DeEjkVLQ==', 'S1 Sistem Informasi', 1, 2, 'Problem Pertemanan', '2026-01-11', 'Monitoring'),

-- 8. 24420100040
(11, SHA2('24420100040', 256), 'gAAAAABp6HxQ45QRMjkn0xEYt0_DVewyUX7zvSx80mzlMBEFMZ9TreLAGdkk-aw4WKYPNRyfvYxhUpnvh4HxmECHbZDASqpf9Q==', 'S1 Desain KomunikaS1 Sistem Informasi Visual', 1, 4, 'Deadline Tugas dan Bingung Ide Tugas', '2026-01-12', 'Monitoring'),

-- 9. 24420100040
(11, SHA2('24420100040', 256), 'gAAAAABp6HxQA_O6C96RqOD_X4uDO1pawW78aVSaAVTqGQyaentv6SwkJbDSVHDkhJhcWgouMkJDgkLw4hcKZP80IBbHJ1RF9g==', 'S1 Desain KomunikaS1 Sistem Informasi Visual', 1, 4, 'Stress Akademik dan Gagal Move On', '2026-01-13', 'Monitoring'),

-- 10. 23410100003
(11, SHA2('23410100003', 256), 'gAAAAABp6HxQtmheP2UCl44zNJhiFWxH-D8apC8uLr0QR9gnK79XFE8GPN5f2LHouNauIFS1O4jNR9bJmP4QQbKBWTeXRYZ8CQ==', 'S1 Sistem Informasi', 1, 2, 'Problem Pertemanan', '2026-01-14', 'Monitoring'),

-- 11. 24420100040
(11, SHA2('24420100040', 256), 'gAAAAABp6HxQ9J-n0Pu9BjBA0upZ0B4TeepXIlPEaaYcOx6OpisU5M8p0G29YvWyfdtLNQeHNOW_5IeyAxvzgDc_uxjoSqys7g==', 'S1 Desain KomunikaS1 Sistem Informasi Visual', 1, 1, 'Gagal Move On', '2026-01-15', 'Monitoring'),

-- 12. 24420100040
(11, SHA2('24420100040', 256), 'gAAAAABp6HxQ6_BYfj8ZTShXgB5_yQUkXPImhRHOzvBAK_jstgEzjWV25jZZrN0H4yzLjFOyHDcrmoan59kxiqhnJcAHEJcsbg==', 'S1 Desain KomunikaS1 Sistem Informasi Visual', 1, 1, 'Gagal Move On', '2026-01-16', 'Monitoring'),

-- 13. 25410100066
(11, SHA2('25410100066', 256), 'gAAAAABp6HxQXO3yO1YbK68eaYwh-sTk0hQSHsZPzjCjArPDkf8ZuW7GJ451RdzTCFDBnLOUSeBFR2uqo5qnowHkoRlj4ILyvg==', 'S1 Sistem Informasi', 1, 3, 'Masalah keluarga', '2026-01-19', 'Monitoring'),

-- 14. 24410100064
(11, SHA2('24410100064', 256), 'gAAAAABp6HxQCXDX-PqBiBwem95QUDmwALFOb4_iswKqlQWlFk6OHxO02YNWkkDyD7BMMIjGogNPRR-l7TXRE3pcwd85sRiZAA==', 'S1 Sistem Informasi', 1, 3, 'Masalah keluarga', '2026-01-20', 'Monitoring'),

-- 15. 24420100040
(11, SHA2('24420100040', 256), 'gAAAAABp6HxQN1NIheA73-Dq8Yz1gkQqovq-C31qPjBB0joS4jROW1fd17-rBM-OXoyTXCBJrXWnmRUDtF8GsQ7RNbGPpJOSgw==', 'S1 Desain KomunikaS1 Sistem Informasi Visual', 1, 1, 'Gagal Move On', '2026-01-21', 'Monitoring'),

-- 16. 23410100003
(11, SHA2('23410100003', 256), 'gAAAAABp6HxQ2NvFvjE78EG4vT9fi4CkwSdhD8J6fYUV5xot7dFg8yNZWl2t4fKvUxbtyeRais3GIcEhYeDbsVL_8PuXlguQqQ==', 'S1 Sistem Informasi', 1, 4, 'Bingung Perihal Magang', '2026-01-21', 'Monitoring'),

-- 17. 24420100040
(11, SHA2('24420100040', 256), 'gAAAAABp6HxQtJaauXt_C7Y4SccbpidsHJkD3k_iQiVKIoQBICvJInPhL8A1f6LOm874FRSDM7oAEs3V1XuPUjsduSOnDliG5A==', 'S1 Desain KomunikaS1 Sistem Informasi Visual', 1, 4, 'Problem Pertemanan, Stress Tugas', '2026-01-22', 'TerminaS1 Sistem Informasi Sementara'),

-- 18. 19420100042
(11, SHA2('19420100042', 256), 'gAAAAABp6HxQwYuAvOG40pmITB9qjLLdr4G2m-cnO4xbeIzKiDIlEUO4U_sJbHeFu-igjmqwDfD-xWjighnTodCXsECiMFJNVA==', 'S1 Desain KomunikaS1 Sistem Informasi Visual', 2, 4, 'Progres Penyelesaian TA', '2026-01-05', 'Monitoring');