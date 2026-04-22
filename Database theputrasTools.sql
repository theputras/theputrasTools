-- ==========================================================
-- 1. MASTER TABEL (TIDAK BERGANTUNG PADA TABEL LAIN)
-- ==========================================================

CREATE TABLE roles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nama_role VARCHAR(50) NOT NULL,
    deskripsi TEXT
);

CREATE TABLE tools (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nama_tool VARCHAR(100) NOT NULL,
    route_name VARCHAR(100) NOT NULL UNIQUE,
    deskripsi VARCHAR(255)
);

-- ==========================================================
-- 2. TABEL JEMBATAN ROLE & TOOLS
-- ==========================================================

CREATE TABLE role_permissions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    role_id INT NOT NULL,
    tool_id INT NOT NULL,
    is_allowed TINYINT(1) DEFAULT 0,
    CONSTRAINT fk_perm_role FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
    CONSTRAINT fk_perm_tool FOREIGN KEY (tool_id) REFERENCES tools(id) ON DELETE CASCADE,
    UNIQUE KEY unique_role_tool (role_id, tool_id)
);
-- ==========================================================
-- 3. TABEL USERS UTAMA
-- ==========================================================
CREATE TABLE `users` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `username` varchar(100) NOT NULL,
  `password` varchar(255) NOT NULL,
  `email` varchar(150) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `role_id` INT DEFAULT 3,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  UNIQUE KEY `email` (`email`),
  -- Tambahan Constraint Foreign Key ke tabel Roles
  CONSTRAINT fk_users_role FOREIGN KEY (`role_id`) REFERENCES roles(id) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
-- ==========================================================
-- 4. TABEL FITUR: GATE SICYCA
-- ==========================================================

CREATE TABLE gate_users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    gate_username VARCHAR(50) NOT NULL,
    gate_password VARCHAR(255) NOT NULL,
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_user_gate (user_id),
    CONSTRAINT fk_gate_users_parent FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE gate_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    gate_user_id INT NOT NULL,
    xsrf_token TEXT,
    gate_session TEXT,
    sso_token TEXT,
    user_agent TEXT,
    is_valid TINYINT(1) DEFAULT 0,
    last_checked_at DATETIME NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_gate_session_user FOREIGN KEY (gate_user_id) REFERENCES gate_users(id) ON DELETE CASCADE
);-- ==========================================================
-- 5. TABEL FITUR: MANAJEMEN ULTAH
-- ==========================================================

CREATE TABLE ultah_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nama VARCHAR(255) NOT NULL,
    nim VARCHAR(20) DEFAULT NULL,
    tanggal INT NOT NULL,
    bulan INT NOT NULL,
    tahun_lahir INT DEFAULT NULL,
    foto_base64 LONGTEXT DEFAULT NULL,
    google_calendar_event_id VARCHAR(255) DEFAULT NULL,
    prodi VARCHAR(100) DEFAULT NULL,
    is_from_sicyca TINYINT(1) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_nim (nim)
);

CREATE TABLE google_oauth_tokens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    token_data JSON NOT NULL,
    email VARCHAR(255) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_user (user_id),
    CONSTRAINT fk_google_oauth_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ==========================================================
-- 6. TABEL FITUR: LOGBOOK MAGANG
-- ==========================================================

-- A. Induk: logbooks
CREATE TABLE logbooks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    uuid VARCHAR(36) UNIQUE,
    user_id BIGINT UNSIGNED NOT NULL,
    fakultas VARCHAR(100),
    prodi VARCHAR(100),
    nama VARCHAR(150),
    nim VARCHAR(50),
    nama_mitra VARCHAR(150),
    waktu_mulai DATE,
    waktu_selesai DATE,
    posisi_magang VARCHAR(100),
    nama_mentor VARCHAR(150),
    wa_mentor VARCHAR(20),
    email_mentor VARCHAR(100),
    google_doc_id VARCHAR(255) NULL,
    google_doc_name VARCHAR(255) NULL,
    ttd_mentor_path VARCHAR(255) NULL,  -- Path file gambar tanda tangan mentor (PNG)
    CONSTRAINT fk_logbooks_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- B. Anak dari logbooks: logbook_entries
CREATE TABLE logbook_entries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    uuid VARCHAR(36) UNIQUE,
    logbook_id INT NOT NULL,
    tanggal DATE NOT NULL,
    aktivitas VARCHAR(255) NOT NULL,
    deskripsi TEXT NOT NULL,
    CONSTRAINT fk_logbook_entries_parent FOREIGN KEY (logbook_id) REFERENCES logbooks(id) ON DELETE CASCADE
);

-- C. Anak dari logbook_entries: logbook_images
CREATE TABLE logbook_images (
    id INT AUTO_INCREMENT PRIMARY KEY,
    entry_id INT NOT NULL,
    path VARCHAR(255) NOT NULL,
    nama_asli VARCHAR(255) DEFAULT NULL,
    deskripsi TEXT DEFAULT NULL,
    tipe_berkas VARCHAR(50) NULL,      -- Contoh: image/jpeg, image/png
    ukuran_berkas BIGINT NULL,         -- Dalam Bytes
    dimensi VARCHAR(20) NULL,          -- Contoh: 1920x1080
    CONSTRAINT fk_logbook_images_parent FOREIGN KEY (entry_id) REFERENCES logbook_entries(id) ON DELETE CASCADE
);

-- D. Tracking approval tanda tangan per bulan
CREATE TABLE logbook_signatures (
    id INT AUTO_INCREMENT PRIMARY KEY,
    logbook_id INT NOT NULL,
    bulan VARCHAR(20) NOT NULL,        -- e.g. "Maret 2026"
    is_approved TINYINT(1) DEFAULT 0,
    approved_at TIMESTAMP NULL,
    CONSTRAINT fk_sig_logbook FOREIGN KEY (logbook_id) REFERENCES logbooks(id) ON DELETE CASCADE,
    UNIQUE KEY unique_logbook_month (logbook_id, bulan)
);

-- E. Resume kegiatan per bulan (rich text dari TipTap editor)
CREATE TABLE logbook_resumes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    logbook_id INT NOT NULL,
    bulan VARCHAR(20) NOT NULL,        -- e.g. "Februari 2026"
    content TEXT,                       -- HTML content dari TipTap editor
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_resume_logbook FOREIGN KEY (logbook_id) REFERENCES logbooks(id) ON DELETE CASCADE,
    UNIQUE KEY unique_logbook_resume_month (logbook_id, bulan)
);


CREATE TABLE webauthn_credentials (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL, -- Diubah jadi BIGINT UNSIGNED
    credential_id TEXT NOT NULL,
    public_key TEXT NOT NULL,
    sign_count INT DEFAULT 0,
    transports VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ==========================================================
-- SEED DATA: TOOLS & PERMISSIONS
-- ==========================================================
-- Tool: Manajemen Ultah
INSERT INTO tools (nama_tool, route_name, deskripsi) 
VALUES ('Manajemen Ultah', 'manajemen_ultah', 'Kelola data ulang tahun & sync ke Google Calendar')
ON DUPLICATE KEY UPDATE nama_tool = VALUES(nama_tool), deskripsi = VALUES(deskripsi);

-- ==========================================================
-- 7. TABEL FITUR: JADWAL SHOLAT & KALENDER HIJRIAH
-- ==========================================================

-- A. Preferensi sholat per-user (Muhammadiyah/NU, lokasi)
CREATE TABLE user_prayer_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    preference ENUM('muhammadiyah', 'nu') DEFAULT 'nu',
    city VARCHAR(100) DEFAULT 'Surabaya',
    country VARCHAR(100) DEFAULT 'Indonesia',
    hijri_adj INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_user (user_id),
    CONSTRAINT fk_prayer_settings_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- B. Konfigurasi tanggal Ramadhan (admin-only, per tahun Hijriah)
CREATE TABLE ramadan_config (
    id INT AUTO_INCREMENT PRIMARY KEY,
    hijri_year INT NOT NULL,
    start_ramadan_muhammadiyah DATE DEFAULT NULL,
    start_ramadan_pemerintah DATE DEFAULT NULL,
    total_days INT DEFAULT 30,
    updated_by BIGINT UNSIGNED DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_hijri_year (hijri_year),
    CONSTRAINT fk_ramadan_updater FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
);

-- ==========================================================
-- 8. TABEL FITUR: PEMBAYARAN (iPaymu QRIS)
-- ==========================================================

CREATE TABLE payment_transactions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    reference_id VARCHAR(100) NOT NULL UNIQUE,
    ipaymu_transaction_id INT NULL,
    amount DECIMAL(12,2) NOT NULL,
    status TINYINT DEFAULT 0,               -- 0=pending, 1=success, -2=expired
    payment_method VARCHAR(50) DEFAULT 'qris',
    payment_channel VARCHAR(50) NULL,
    qr_data TEXT NULL,                      -- QR string/URL dari iPaymu
    buyer_name VARCHAR(150) NULL,
    buyer_phone VARCHAR(20) NULL,
    buyer_email VARCHAR(150) NULL,
    comments TEXT NULL,
    paid_at TIMESTAMP NULL,
    expired_at TIMESTAMP NULL,
    callback_data JSON NULL,                -- Raw callback data dari iPaymu
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_payment_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_reference (reference_id),
    INDEX idx_status (status),
    INDEX idx_user_created (user_id, created_at)
);

-- ==========================================================
-- 9. TABEL FITUR: JADWAL KULIAH USER
-- ==========================================================

CREATE TABLE user_schedules_metadata (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL UNIQUE,
    last_scraped VARCHAR(100),
    kalendar_uuid VARCHAR(100) UNIQUE NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_schedules_meta_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE user_schedules (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    hari_tanggal VARCHAR(100),
    jam VARCHAR(50),
    ruang VARCHAR(50),
    mata_kuliah VARCHAR(255),
    dosen VARCHAR(255),
    status_kuliah VARCHAR(100),
    keterangan VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_schedules_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ==========================================================
-- 10. TABEL FITUR: KONSELOR — PENCATATAN SESI KONSELING
-- ==========================================================

-- A. Master: Kategori Masalah (CRUD dinamis)
CREATE TABLE konselor_kategori_masalah (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nama VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- B. Master: Jenis Layanan (CRUD dinamis)
CREATE TABLE konselor_jenis_layanan (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nama VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- C. Data Sesi Konseling
CREATE TABLE konselor_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    konselor_user_id BIGINT UNSIGNED NOT NULL,
    nim_hash VARCHAR(64) NOT NULL,
    nim_encrypted TEXT NOT NULL,
    prodi VARCHAR(100),
    jenis_layanan_id INT NOT NULL,
    kategori_masalah_id INT NOT NULL,
    topik TEXT NOT NULL,
    tanggal_sesi DATE NOT NULL,
    tindak_lanjut TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_konselor_session_user FOREIGN KEY (konselor_user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_konselor_session_layanan FOREIGN KEY (jenis_layanan_id) REFERENCES konselor_jenis_layanan(id) ON DELETE RESTRICT,
    CONSTRAINT fk_konselor_session_kategori FOREIGN KEY (kategori_masalah_id) REFERENCES konselor_kategori_masalah(id) ON DELETE RESTRICT,
    INDEX idx_konselor_nim (nim_hash),
    INDEX idx_konselor_kategori (kategori_masalah_id),
    INDEX idx_konselor_tanggal (tanggal_sesi)
);

