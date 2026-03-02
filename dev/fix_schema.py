import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from connection import get_connection

def fix_db():
    print("Connecting to database...")
    conn = get_connection()
    if not conn:
        print("Failed to connect to database")
        return

    cursor = conn.cursor(dictionary=True)
    try:
        # ============================================================
        # 1. CREATE TABLE: user_prayer_settings (Jadwal Sholat)
        # ============================================================
        print("Creating table 'user_prayer_settings'...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_prayer_settings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT UNSIGNED NOT NULL,
                preference ENUM('muhammadiyah', 'nu') DEFAULT 'nu',
                city VARCHAR(100) DEFAULT 'Surabaya',
                state VARCHAR(100) DEFAULT NULL,
                country VARCHAR(100) DEFAULT 'Indonesia',
                hijri_adj INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY unique_user (user_id),
                CONSTRAINT fk_prayer_settings_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        print("✅ Tabel 'user_prayer_settings' ready.")

        # Migrate: tambah kolom state jika belum ada
        try:
            cursor.execute("ALTER TABLE user_prayer_settings ADD COLUMN state VARCHAR(100) DEFAULT NULL AFTER city")
            print("[OK] Kolom 'state' ditambahkan.")
        except Exception:
            print("[INFO] Kolom 'state' sudah ada, skip.")

        # ============================================================
        # 2. CREATE TABLE: ramadan_config (Admin-only Ramadhan dates)
        # ============================================================
        print("Creating table 'ramadan_config'...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ramadan_config (
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
            )
        """)
        print("✅ Tabel 'ramadan_config' ready.")

        # ============================================================
        # 3. SEED: Ramadhan 1447 H (2026)
        # ============================================================
        print("Seeding Ramadhan 1447 config...")
        cursor.execute("""
            INSERT INTO ramadan_config (hijri_year, start_ramadan_muhammadiyah, start_ramadan_pemerintah, total_days)
            VALUES (1447, '2026-02-17', '2026-02-18', 30)
            ON DUPLICATE KEY UPDATE hijri_year = VALUES(hijri_year)
        """)
        print("✅ Ramadhan 1447 H (2026) config seeded.")

        # ============================================================
        # 4. MIGRATE: logbooks.ttd_mentor_path (Tanda Tangan Mentor)
        # ============================================================
        print("Migrating 'logbooks' table for TTD...")
        try:
            cursor.execute("ALTER TABLE logbooks ADD COLUMN ttd_mentor_path VARCHAR(255) NULL")
            print("[OK] Kolom 'ttd_mentor_path' ditambahkan ke 'logbooks'.")
        except Exception:
            print("[INFO] Kolom 'ttd_mentor_path' sudah ada, skip.")

        # ============================================================
        # 5. CREATE TABLE: logbook_signatures (TTD approval per bulan)
        # ============================================================
        print("Creating table 'logbook_signatures'...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS logbook_signatures (
                id INT AUTO_INCREMENT PRIMARY KEY,
                logbook_id INT NOT NULL,
                bulan VARCHAR(20) NOT NULL,
                is_approved TINYINT(1) DEFAULT 0,
                approved_at TIMESTAMP NULL,
                CONSTRAINT fk_sig_logbook FOREIGN KEY (logbook_id) REFERENCES logbooks(id) ON DELETE CASCADE,
                UNIQUE KEY unique_logbook_month (logbook_id, bulan)
            )
        """)
        print("✅ Tabel 'logbook_signatures' ready.")

        conn.commit()
        print("\n✅ SEMUA MIGRASI SELESAI!")
        
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    fix_db()
