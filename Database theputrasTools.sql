-- ==========================================================
-- 1. TABEL INDEPENDENT (TIDAK ADA FOREIGN KEY KE TABEL LAIN)
-- ==========================================================

CREATE TABLE roles (
    id SERIAL PRIMARY KEY,
    nama_role VARCHAR(50) NOT NULL,
    deskripsi TEXT
);

CREATE TABLE tools (
    id SERIAL PRIMARY KEY,
    nama_tool VARCHAR(100) NOT NULL,
    route_name VARCHAR(100) NOT NULL UNIQUE,
    deskripsi VARCHAR(255) DEFAULT NULL
);

CREATE TABLE konselor_jenis_layanan (
    id SERIAL PRIMARY KEY,
    nama VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE konselor_kategori_masalah (
    id SERIAL PRIMARY KEY,
    nama VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE konselor_tindak_lanjut (
    id SERIAL PRIMARY KEY,
    nama VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE ultah_records (
    id SERIAL PRIMARY KEY,
    nama VARCHAR(255) NOT NULL,
    nim VARCHAR(20) DEFAULT NULL UNIQUE,
    tanggal INT NOT NULL,
    bulan INT NOT NULL,
    tahun_lahir INT DEFAULT NULL,
    foto_base64 TEXT,
    google_calendar_event_id VARCHAR(255) DEFAULT NULL,
    prodi VARCHAR(100) DEFAULT NULL,
    is_from_sicyca SMALLINT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================================
-- 2. TABEL USERS & JEMBATAN PERMISSION
-- ==========================================================

CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    email VARCHAR(150) DEFAULT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    role_id INT DEFAULT 3,
    CONSTRAINT fk_users_role FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE SET NULL
);

CREATE TABLE role_permissions (
    id SERIAL PRIMARY KEY,
    role_id INT NOT NULL,
    tool_id INT NOT NULL,
    is_allowed SMALLINT DEFAULT 0,
    UNIQUE (role_id, tool_id),
    CONSTRAINT fk_perm_role FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
    CONSTRAINT fk_perm_tool FOREIGN KEY (tool_id) REFERENCES tools(id) ON DELETE CASCADE
);

-- ==========================================================
-- 3. TABEL YANG BERGANTUNG LANGSUNG PADA USERS (LEVEL 1)
-- ==========================================================

CREATE TABLE webauthn_credentials (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    credential_id TEXT NOT NULL,
    public_key TEXT NOT NULL,
    sign_count INT DEFAULT 0,
    transports VARCHAR(255) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT webauthn_credentials_ibfk_1 FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE fingerprint_credentials (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    credential_id VARCHAR(255) NOT NULL UNIQUE,
    public_key TEXT NOT NULL,
    sign_count INT DEFAULT 0,
    device_type VARCHAR(50) DEFAULT 'face',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP DEFAULT NULL,
    CONSTRAINT user_credentials_ibfk_1 FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE gate_users (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE,
    gate_username VARCHAR(50) NOT NULL,
    gate_password VARCHAR(255) NOT NULL,
    is_active SMALLINT DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_gate_users_parent FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE google_oauth_tokens (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE,
    token_data JSON NOT NULL,
    email VARCHAR(255) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_google_oauth_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE konselor_data_klien (
    id SERIAL PRIMARY KEY,
    id_civitas VARCHAR(64) NOT NULL,
    nama VARCHAR(150) DEFAULT NULL,
    prodi VARCHAR(100) DEFAULT NULL,
    dosen_wali VARCHAR(150) DEFAULT NULL,
    mbti VARCHAR(20) DEFAULT NULL,
    status_abk VARCHAR(100) DEFAULT NULL,
    status_civitas VARCHAR(50) DEFAULT 'Mahasiswa',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_id_nama UNIQUE (id_civitas, nama)
);

CREATE TABLE konselor_sessions (
    id SERIAL PRIMARY KEY,
    konselor_user_id BIGINT NOT NULL,
    id_klien INT NOT NULL,
    jenis_layanan_id INT NOT NULL,
    topik TEXT NOT NULL,
    tanggal_sesi DATE NOT NULL,
    waktu_mulai VARCHAR(10) DEFAULT NULL,
    waktu_selesai VARCHAR(10) DEFAULT NULL,
    tindak_lanjut_id INT DEFAULT NULL,
    catatan_kesimpulan TEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_konselor_session_user FOREIGN KEY (konselor_user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_konselor_session_layanan FOREIGN KEY (jenis_layanan_id) REFERENCES konselor_jenis_layanan(id) ON DELETE RESTRICT,
    CONSTRAINT fk_konselor_session_tindak_lanjut FOREIGN KEY (tindak_lanjut_id) REFERENCES konselor_tindak_lanjut(id) ON DELETE RESTRICT,
    CONSTRAINT fk_konselor_session_klien FOREIGN KEY (id_klien) REFERENCES konselor_data_klien(id) ON DELETE CASCADE
);

CREATE TABLE konselor_jadwal (
    id SERIAL PRIMARY KEY,
    konselor_user_id BIGINT NOT NULL,
    id_klien INT NOT NULL,
    layanan_id INT NOT NULL,
    tanggal DATE NOT NULL,
    jam VARCHAR(10) NOT NULL,
    waktu_mulai TIMESTAMP DEFAULT NULL,
    total_pause_ms BIGINT DEFAULT 0,
    last_pause_time TIMESTAMP DEFAULT NULL,
    status VARCHAR(20) DEFAULT 'Menunggu' CHECK (status IN ('Menunggu', 'Berlangsung', 'Jeda', 'Selesai', 'Dibatalkan')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_konselor_jadwal_user FOREIGN KEY (konselor_user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_konselor_jadwal_layanan FOREIGN KEY (layanan_id) REFERENCES konselor_jenis_layanan(id) ON DELETE RESTRICT,
    CONSTRAINT fk_konselor_jadwal_klien FOREIGN KEY (id_klien) REFERENCES konselor_data_klien(id) ON DELETE CASCADE
);

CREATE TABLE logbooks (
    id SERIAL PRIMARY KEY,
    uuid VARCHAR(36) DEFAULT NULL UNIQUE,
    user_id BIGINT NOT NULL,
    fakultas VARCHAR(100) DEFAULT NULL,
    prodi VARCHAR(100) DEFAULT NULL,
    nama VARCHAR(150) DEFAULT NULL,
    nim VARCHAR(50) DEFAULT NULL,
    nama_mitra VARCHAR(150) DEFAULT NULL,
    waktu_mulai DATE DEFAULT NULL,
    waktu_selesai DATE DEFAULT NULL,
    posisi_magang VARCHAR(100) DEFAULT NULL,
    nama_mentor VARCHAR(150) DEFAULT NULL,
    wa_mentor VARCHAR(20) DEFAULT NULL,
    email_mentor VARCHAR(100) DEFAULT NULL,
    google_doc_id VARCHAR(255) DEFAULT NULL,
    google_doc_name VARCHAR(255) DEFAULT NULL,
    ttd_mentor_path VARCHAR(255) DEFAULT NULL,
    CONSTRAINT fk_logbooks_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE payment_transactions (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    reference_id VARCHAR(100) NOT NULL UNIQUE,
    ipaymu_transaction_id INT DEFAULT NULL,
    amount DECIMAL(12,2) NOT NULL,
    status SMALLINT DEFAULT 0,
    payment_method VARCHAR(50) DEFAULT 'qris',
    payment_channel VARCHAR(50) DEFAULT NULL,
    qr_data TEXT,
    buyer_name VARCHAR(150) DEFAULT NULL,
    buyer_phone VARCHAR(20) DEFAULT NULL,
    buyer_email VARCHAR(150) DEFAULT NULL,
    comments TEXT,
    paid_at TIMESTAMP DEFAULT NULL,
    expired_at TIMESTAMP DEFAULT NULL,
    callback_data JSON DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_payment_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE ramadan_config (
    id SERIAL PRIMARY KEY,
    hijri_year INT NOT NULL UNIQUE,
    start_ramadan_muhammadiyah DATE DEFAULT NULL,
    start_ramadan_pemerintah DATE DEFAULT NULL,
    total_days INT DEFAULT 30,
    updated_by BIGINT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_ramadan_updater FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE user_prayer_settings (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE,
    preference VARCHAR(20) CHECK (preference IN ('muhammadiyah', 'nu')) DEFAULT 'nu',
    city VARCHAR(100) DEFAULT 'Surabaya',
    country VARCHAR(100) DEFAULT 'Indonesia',
    hijri_adj INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_prayer_settings_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE user_schedules (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    hari_tanggal VARCHAR(100) DEFAULT NULL,
    jam VARCHAR(50) DEFAULT NULL,
    ruang VARCHAR(50) DEFAULT NULL,
    mata_kuliah VARCHAR(255) DEFAULT NULL,
    dosen VARCHAR(255) DEFAULT NULL,
    status_kuliah VARCHAR(100) DEFAULT NULL,
    keterangan VARCHAR(255) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_schedules_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE user_schedules_metadata (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE,
    last_scraped VARCHAR(100) DEFAULT NULL,
    kalendar_uuid VARCHAR(100) DEFAULT NULL UNIQUE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_schedules_meta_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE user_sessions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    refresh_token CHAR(36) NOT NULL UNIQUE,
    expires_at TIMESTAMP NOT NULL,
    ip_address VARCHAR(45) DEFAULT NULL,
    user_agent VARCHAR(255) DEFAULT NULL,
    revoked SMALLINT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT user_sessions_ibfk_1 FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ==========================================================
-- 4. TABEL ANAK (LEVEL 2 & 3 DEEP DEPENDENCIES)
-- ==========================================================

CREATE TABLE gate_sessions (
    id SERIAL PRIMARY KEY,
    gate_user_id INT NOT NULL,
    xsrf_token TEXT,
    gate_session TEXT,
    sso_token TEXT,
    user_agent TEXT,
    is_valid SMALLINT DEFAULT 0,
    last_checked_at TIMESTAMP DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_gate_session_user FOREIGN KEY (gate_user_id) REFERENCES gate_users(id) ON DELETE CASCADE
);

CREATE TABLE konselor_session_kategori (
    session_id INT NOT NULL,
    kategori_id INT NOT NULL,
    PRIMARY KEY (session_id, kategori_id),
    CONSTRAINT fk_sk_kategori FOREIGN KEY (kategori_id) REFERENCES konselor_kategori_masalah(id) ON DELETE CASCADE,
    CONSTRAINT fk_sk_session FOREIGN KEY (session_id) REFERENCES konselor_sessions(id) ON DELETE CASCADE
);

CREATE TABLE logbook_entries (
    id SERIAL PRIMARY KEY,
    uuid VARCHAR(36) DEFAULT NULL UNIQUE,
    logbook_id INT NOT NULL,
    tanggal DATE NOT NULL,
    aktivitas VARCHAR(255) NOT NULL,
    deskripsi TEXT NOT NULL,
    CONSTRAINT fk_logbook_entries_parent FOREIGN KEY (logbook_id) REFERENCES logbooks(id) ON DELETE CASCADE
);

CREATE TABLE logbook_images (
    id SERIAL PRIMARY KEY,
    entry_id INT NOT NULL,
    path VARCHAR(255) NOT NULL,
    nama_asli VARCHAR(255) DEFAULT NULL,
    deskripsi TEXT,
    tipe_berkas VARCHAR(50) DEFAULT NULL,
    ukuran_berkas BIGINT DEFAULT NULL,
    dimensi VARCHAR(20) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_logbook_images_parent FOREIGN KEY (entry_id) REFERENCES logbook_entries(id) ON DELETE CASCADE
);

CREATE TABLE logbook_resumes (
    id SERIAL PRIMARY KEY,
    logbook_id INT NOT NULL,
    bulan VARCHAR(20) NOT NULL,
    content TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (logbook_id, bulan),
    CONSTRAINT fk_resume_logbook FOREIGN KEY (logbook_id) REFERENCES logbooks(id) ON DELETE CASCADE
);

CREATE TABLE logbook_signatures (
    id SERIAL PRIMARY KEY,
    logbook_id INT NOT NULL,
    bulan VARCHAR(20) NOT NULL,
    is_approved SMALLINT DEFAULT 0,
    approved_at TIMESTAMP DEFAULT NULL,
    UNIQUE (logbook_id, bulan),
    CONSTRAINT fk_sig_logbook FOREIGN KEY (logbook_id) REFERENCES logbooks(id) ON DELETE CASCADE
);

-- ==========================================================
-- 5. TAMBAHAN INDEX UNTUK PERFORMA QUERY
-- ==========================================================
CREATE INDEX idx_konselor_nim ON konselor_sessions(nim_id);
CREATE INDEX idx_konselor_tanggal ON konselor_sessions(tanggal_sesi);
CREATE INDEX idx_payment_status ON payment_transactions(status);
CREATE INDEX idx_payment_user_created ON payment_transactions(user_id, created_at);



-- -- ==========================================================
-- -- 6. DATA DUMMY
-- -- ==========================================================
-- INSERT INTO konselor_jadwal (konselor_user_id, nim, nama, prodi, layanan_id, tanggal, jam, status) VALUES
-- (1, '23410100001', 'Budi Santoso', 'S1 Sistem Informasi', 1, CURRENT_DATE, '09:00', 'Menunggu'),
-- (1, '23410100002', 'Siti Aminah', 'S1 DKV', 2, CURRENT_DATE, '13:00', 'Menunggu'),
-- (1, '23410100003', 'Andi Wijaya', 'D3 Teknik Komputer', 1, CURRENT_DATE + INTERVAL '1 day', '10:00', 'Menunggu')
-- ON CONFLICT DO NOTHING;
