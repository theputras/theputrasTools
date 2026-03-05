"""
fix_schema.py — Smart Database Migration Runner
=================================================
Script ini membaca 'Database theputrasTools.sql' dan 'Seed theputrasTools.sql',
lalu menjalankannya secara cerdas:
- CREATE TABLE → Skip jika tabel sudah ada
- CREATE INDEX → Skip jika index sudah ada
- INSERT ... ON DUPLICATE KEY → Selalu jalankan (safe idempotent)
- ALTER TABLE → Coba jalankan, skip jika error (misal kolom sudah ada)

Usage:
    python dev/fix_schema.py
"""

import sys
import os
import re
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from connection import get_connection

# Path ke file SQL
BASE_DIR = os.path.join(os.path.dirname(__file__), '..')
SCHEMA_FILE = os.path.join(BASE_DIR, 'Database theputrasTools.sql')
SEED_FILE = os.path.join(BASE_DIR, 'Seed theputrasTools.sql')


def get_existing_tables(cursor):
    """Ambil list semua tabel yang sudah ada di database."""
    cursor.execute("SHOW TABLES")
    return {row[0] if isinstance(row, tuple) else list(row.values())[0] for row in cursor.fetchall()}


def get_existing_columns(cursor, table_name):
    """Ambil list semua kolom dari tabel tertentu."""
    try:
        cursor.execute(f"SHOW COLUMNS FROM `{table_name}`")
        return {row[0] if isinstance(row, tuple) else row['Field'] for row in cursor.fetchall()}
    except Exception:
        return set()


def parse_sql_statements(sql_content):
    """Parse SQL content menjadi individual statements."""
    # Hapus komentar single line (-- ... )
    lines = []
    for line in sql_content.split('\n'):
        stripped = line.strip()
        if stripped.startswith('--'):
            continue
        # Hapus inline comment
        comment_idx = line.find('--')
        if comment_idx > 0:
            line = line[:comment_idx]
        lines.append(line)

    sql_text = '\n'.join(lines).strip()
    
    # Split by semicolon (tapi hati-hati dengan semicolon di dalam string)
    statements = []
    current = []
    in_string = False
    string_char = None
    
    for char in sql_text:
        if in_string:
            current.append(char)
            if char == string_char:
                in_string = False
        elif char in ('"', "'"):
            in_string = True
            string_char = char
            current.append(char)
        elif char == ';':
            stmt = ''.join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
        else:
            current.append(char)
    
    # Sisa terakhir
    last = ''.join(current).strip()
    if last:
        statements.append(last)
    
    return statements


def extract_table_name_from_create(statement):
    """Extract nama tabel dari CREATE TABLE statement."""
    match = re.search(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`"]?(\w+)[`"]?', statement, re.IGNORECASE)
    return match.group(1) if match else None


def run_schema_migration(cursor, existing_tables):
    """Jalankan migration dari Database theputrasTools.sql."""
    if not os.path.exists(SCHEMA_FILE):
        print(f"⚠️  File '{SCHEMA_FILE}' tidak ditemukan. Skip.")
        return 0, 0

    print(f"\n📂 Membaca: {os.path.basename(SCHEMA_FILE)}")
    with open(SCHEMA_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    statements = parse_sql_statements(content)
    created = 0
    skipped = 0

    for stmt in statements:
        stmt_upper = stmt.upper().strip()

        # === CREATE TABLE ===
        if stmt_upper.startswith('CREATE TABLE'):
            table_name = extract_table_name_from_create(stmt)
            if not table_name:
                print(f"  ⚠️  Gagal parse nama tabel dari: {stmt[:60]}...")
                continue

            if table_name in existing_tables:
                print(f"  ⏭️  Tabel '{table_name}' sudah ada → skip")
                skipped += 1
            else:
                try:
                    cursor.execute(stmt)
                    existing_tables.add(table_name)
                    print(f"  ✅ Tabel '{table_name}' berhasil dibuat")
                    created += 1
                except Exception as e:
                    print(f"  ❌ Gagal buat tabel '{table_name}': {e}")

        # === ALTER TABLE ===
        elif stmt_upper.startswith('ALTER TABLE'):
            try:
                cursor.execute(stmt)
                print(f"  ✅ ALTER berhasil: {stmt[:80]}...")
                created += 1
            except Exception as e:
                err_str = str(e)
                if 'Duplicate column' in err_str or 'already exists' in err_str:
                    print(f"  ⏭️  ALTER skip (sudah ada): {stmt[:60]}...")
                    skipped += 1
                else:
                    print(f"  ❌ ALTER gagal: {e}")

        # === INSERT (dari schema, jarang tapi bisa ada) ===
        elif stmt_upper.startswith('INSERT'):
            try:
                cursor.execute(stmt)
                print(f"  ✅ INSERT berhasil: {stmt[:60]}...")
                created += 1
            except Exception as e:
                print(f"  ⏭️  INSERT skip: {e}")
                skipped += 1

        # === Lainnya (DROP, dsb) ===
        else:
            if stmt.strip():
                try:
                    cursor.execute(stmt)
                    print(f"  ✅ Executed: {stmt[:60]}...")
                    created += 1
                except Exception as e:
                    print(f"  ⚠️  Skip: {str(e)[:80]}")
                    skipped += 1

    return created, skipped


def run_seed_data(cursor):
    """Jalankan seed data dari Seed theputrasTools.sql."""
    if not os.path.exists(SEED_FILE):
        print(f"\n⚠️  File '{os.path.basename(SEED_FILE)}' tidak ditemukan. Skip seed.")
        return 0, 0

    print(f"\n📂 Membaca: {os.path.basename(SEED_FILE)}")
    with open(SEED_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    statements = parse_sql_statements(content)
    seeded = 0
    skipped = 0

    for stmt in statements:
        if not stmt.strip():
            continue
        try:
            cursor.execute(stmt)
            affected = cursor.rowcount
            label = stmt[:60].replace('\n', ' ')
            if affected > 0:
                print(f"  🌱 Seeded ({affected} row): {label}...")
                seeded += 1
            else:
                print(f"  ⏭️  Sudah ada: {label}...")
                skipped += 1
        except Exception as e:
            print(f"  ❌ Seed gagal: {e}")

    return seeded, skipped


def fix_db():
    """Main entry point: jalankan schema migration + seed data."""
    print("=" * 60)
    print("🔧 Smart Database Migration Runner")
    print("=" * 60)
    
    print("\n🔌 Connecting to database...")
    conn = get_connection()
    if not conn:
        print("❌ Gagal konek ke database!")
        return

    # Pakai dictionary=False supaya SHOW TABLES return tuple
    cursor = conn.cursor()
    
    try:
        # 1. Ambil tabel yang sudah ada
        existing_tables = get_existing_tables(cursor)
        print(f"📊 Tabel yang sudah ada: {len(existing_tables)} tabel")

        # 2. Jalankan schema migration
        schema_created, schema_skipped = run_schema_migration(cursor, existing_tables)

        # 3. Jalankan seed data
        seed_created, seed_skipped = run_seed_data(cursor)

        # 4. Commit
        conn.commit()

        # 5. Summary
        print("\n" + "=" * 60)
        print("📋 SUMMARY")
        print("=" * 60)
        print(f"  Schema: {schema_created} created, {schema_skipped} skipped")
        print(f"  Seed:   {seed_created} seeded, {seed_skipped} skipped")
        print("\n✅ MIGRASI SELESAI!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        conn.rollback()
        logging.error(f"[fix_schema] Error: {e}")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    fix_db()
