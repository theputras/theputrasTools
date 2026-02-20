from connection import get_connection

def fix_db():
    print("Connecting to database...")
    conn = get_connection()
    if not conn:
        print("Failed to connect to database")
        return

    cursor = conn.cursor()
    try:
        print("Adding google_doc_id column...")
        cursor.execute("ALTER TABLE logbooks ADD COLUMN google_doc_id VARCHAR(255) DEFAULT NULL")
        print("Adding google_doc_name column...")
        cursor.execute("ALTER TABLE logbooks ADD COLUMN google_doc_name VARCHAR(255) DEFAULT NULL")
        conn.commit()
        print("Columns added successfully!")
    except Exception as e:
        print(f"Error executing schema update: {e}")
        # Possibly already exists, which is fine
    finally:
        conn.close()

if __name__ == "__main__":
    fix_db()
