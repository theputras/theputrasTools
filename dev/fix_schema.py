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
        import uuid
        
        # ============================================================
        # 1. ADD UUID TO LOGBOOKS
        # ============================================================
        print("Migrating 'logbooks' table for UUID...")
        try:
            # We add it as a string of length 36 (typical UUID size, or short UUID)
            cursor.execute("ALTER TABLE logbooks ADD COLUMN uuid VARCHAR(36) UNIQUE AFTER id")
            print("[OK] Kolom 'uuid' ditambahkan ke 'logbooks'.")
            
            # Backfill existing logbooks
            cursor.execute("SELECT id FROM logbooks WHERE uuid IS NULL")
            logbooks_to_update = cursor.fetchall()
            for lb in logbooks_to_update:
                new_uuid = str(uuid.uuid4())[:8] # pake 8 karakter aja biar pendek
                # pastikan unik
                while True:
                    cursor.execute("SELECT id FROM logbooks WHERE uuid = %s", (new_uuid,))
                    if not cursor.fetchone():
                        break
                    new_uuid = str(uuid.uuid4())[:8]
                cursor.execute("UPDATE logbooks SET uuid = %s WHERE id = %s", (new_uuid, lb['id']))
            print(f"[OK] Backfilled {len(logbooks_to_update)} logbooks with short UUIDs.")
        except Exception as e:
            print(f"[INFO] Kolom 'uuid' pada 'logbooks' mungkin sudah ada (Error: {e}).")

        # ============================================================
        # 2. ADD UUID TO LOGBOOK_ENTRIES
        # ============================================================
        print("Migrating 'logbook_entries' table for UUID...")
        try:
            cursor.execute("ALTER TABLE logbook_entries ADD COLUMN uuid VARCHAR(36) UNIQUE AFTER id")
            print("[OK] Kolom 'uuid' ditambahkan ke 'logbook_entries'.")
            
            # Backfill existing entries
            cursor.execute("SELECT id FROM logbook_entries WHERE uuid IS NULL")
            entries_to_update = cursor.fetchall()
            for entry in entries_to_update:
                new_uuid = str(uuid.uuid4())[:8]
                while True:
                    cursor.execute("SELECT id FROM logbook_entries WHERE uuid = %s", (new_uuid,))
                    if not cursor.fetchone():
                        break
                    new_uuid = str(uuid.uuid4())[:8]
                cursor.execute("UPDATE logbook_entries SET uuid = %s WHERE id = %s", (new_uuid, entry['id']))
            print(f"[OK] Backfilled {len(entries_to_update)} logbook entries with short UUIDs.")
        except Exception as e:
            print(f"[INFO] Kolom 'uuid' pada 'logbook_entries' mungkin sudah ada (Error: {e}).")

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
