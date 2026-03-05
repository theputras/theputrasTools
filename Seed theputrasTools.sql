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
