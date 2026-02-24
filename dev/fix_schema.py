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
        # 0. INSERT role baru "Manajemen Ultah" ke tabel roles
        # ============================================================
        print("Inserting role 'Manajemen Ultah'...")
        cursor.execute("""
            INSERT INTO roles (nama_role, deskripsi) 
            VALUES ('Manajemen Ultah', 'Role khusus untuk akses fitur manajemen ulang tahun')
            ON DUPLICATE KEY UPDATE deskripsi = VALUES(deskripsi)
        """)
        cursor.execute("SELECT id FROM roles WHERE nama_role = 'Manajemen Ultah'")
        new_role = cursor.fetchone()
        print(f"✅ Role 'Manajemen Ultah' -> ID: {new_role['id']}")

        # ============================================================
        # 1. INSERT tool "Manajemen Ultah" ke tabel tools
        # ============================================================
        print("Inserting tool 'Manajemen Ultah'...")
        cursor.execute("""
            INSERT INTO tools (nama_tool, route_name, deskripsi) 
            VALUES ('Manajemen Ultah', 'manajemen_ultah', 'Kelola data ulang tahun & sync ke Google Calendar')
            ON DUPLICATE KEY UPDATE nama_tool = VALUES(nama_tool), deskripsi = VALUES(deskripsi)
        """)
        
        # Ambil ID tool yang baru diinsert / yang sudah ada
        cursor.execute("SELECT id FROM tools WHERE route_name = 'manajemen_ultah'")
        tool_row = cursor.fetchone()
        if not tool_row:
            print("ERROR: Tool tidak ditemukan setelah insert!")
            return
        tool_id = tool_row['id']
        print(f"Tool ID: {tool_id}")

        # ============================================================
        # 2. INSERT role_permissions untuk semua role yang ada
        #    - Super Admin (1) tidak perlu karena sudah bypass di tools_page()
        #    - Role 2 (Admin/Staff) -> allowed (1)
        #    - Role 3 (Mahasiswa) -> allowed (1)
        #    - Role 4 (Mahasiswa Non-Sicyca) -> not allowed (0)
        # ============================================================
        print("Setting role permissions...")
        
        # Ambil semua role kecuali Super Admin (id=1)
        cursor.execute("SELECT id, nama_role FROM roles WHERE id != 1")
        roles = cursor.fetchall()
        
        for role in roles:
            role_id = role['id']
            # Default: role 2 & 3 allowed, role 4 not allowed
            is_allowed = 1 if role_id in (2, 3) else 0
            
            cursor.execute("""
                INSERT INTO role_permissions (role_id, tool_id, is_allowed)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE is_allowed = VALUES(is_allowed)
            """, (role_id, tool_id, is_allowed))
            
            status = "✅ ALLOWED" if is_allowed else "❌ NOT ALLOWED"
            print(f"  Role '{role['nama_role']}' (id={role_id}): {status}")

        conn.commit()
        print("\n✅ Semua data berhasil dimasukkan!")
        
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    fix_db()
