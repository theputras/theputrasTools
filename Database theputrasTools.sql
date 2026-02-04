CREATE TABLE `users` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `username` varchar(100) NOT NULL,
  `password` varchar(255) NOT NULL,
  `email` varchar(150) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  UNIQUE KEY `email` (`email`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
-- Tabel untuk menyimpan kredensial Gate per User
CREATE TABLE gate_users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,      -- INI KUNCINYA (Link ke tabel users)
    gate_username VARCHAR(50) NOT NULL,    -- NIM/Username Sicyca
    gate_password VARCHAR(255) NOT NULL,   -- Password Sicyca (Terenkripsi Fernet)
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- Mencegah 1 user punya 2 akun gate (harus 1 lawan 1)
    UNIQUE KEY unique_user_gate (user_id),

    -- Relasi ke tabel users utama
    CONSTRAINT fk_gate_users_parent
        FOREIGN KEY (user_id) 
        REFERENCES users(id) 
        ON DELETE CASCADE
);

-- Tabel Session (Tetap butuh, tapi relasinya ke gate_users)
CREATE TABLE gate_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    gate_user_id INT NOT NULL,
    
    -- Kolom Cookie Terpisah
    xsrf_token TEXT,              -- Menyimpan value XSRF-TOKEN
    gate_session TEXT,            -- Menyimpan value gate_dinamika_session
    sso_token TEXT,               -- Menyimpan value SSO_TOKEN
    
    user_agent TEXT,
    is_valid TINYINT(1) DEFAULT 0,
    last_checked_at DATETIME NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_gate_session_user
        FOREIGN KEY (gate_user_id) 
        REFERENCES gate_users(id) 
        ON DELETE CASCADE
);

-- Tabel data ultah
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
-- Tabel token Google OAuth (simpan di DB, bukan file)
CREATE TABLE google_oauth_tokens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    token_data JSON NOT NULL,
    email VARCHAR(255) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_user (user_id)
);