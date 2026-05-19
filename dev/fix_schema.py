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
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from connection import get_connection

# Path ke file SQL
BASE_DIR = os.path.join(os.path.dirname(__file__), '..')
SCHEMA_FILE = os.path.join(BASE_DIR, 'Database theputrasTools.sql')
SEED_FILE = os.path.join(BASE_DIR, 'Seed theputrasTools.sql')


def get_existing_tables(cursor):
    """Ambil list semua tabel yang sudah ada di database."""
    cursor.execute("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public'")
    return {row[0] if isinstance(row, tuple) else list(row.values())[0] for row in cursor.fetchall()}


def get_existing_columns(cursor, table_name):
    """Ambil list semua kolom dari tabel tertentu."""
    try:
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s", (table_name,))
        return {row[0] if isinstance(row, tuple) else row.get('column_name', row[0]) for row in cursor.fetchall()}
    except Exception:
        return set()


def get_existing_columns_with_types(cursor, table_name):
    """Ambil kolom beserta tipe datanya dari tabel tertentu."""
    try:
        cursor.execute("""
            SELECT column_name, udt_name, character_maximum_length, column_default
            FROM information_schema.columns
            WHERE table_name = %s AND table_schema = 'public'
            ORDER BY ordinal_position
        """, (table_name,))
        cols = {}
        for row in cursor.fetchall():
            if isinstance(row, dict):
                cols[row['column_name']] = row
            else:
                cols[row[0]] = {
                    'column_name': row[0], 'udt_name': row[1],
                    'character_maximum_length': row[2], 'column_default': row[3]
                }
        return cols
    except Exception:
        return {}


def get_existing_constraints(cursor, table_name):
    """Ambil set nama constraint yang sudah ada di tabel."""
    try:
        cursor.execute("""
            SELECT constraint_name FROM information_schema.table_constraints
            WHERE table_name = %s AND table_schema = 'public'
        """, (table_name,))
        return {row[0] if isinstance(row, tuple) else row['constraint_name'] for row in cursor.fetchall()}
    except Exception:
        return set()


def normalize_sql_type_to_pg(raw_type):
    """Normalize tipe data SQL ke format udt_name PostgreSQL.
    Returns: (udt_name, max_length atau None)
    """
    t = raw_type.upper().strip()
    for kw in ['DEFAULT', 'NOT NULL', 'CHECK(', 'CHECK (', 'REFERENCES', 'UNIQUE', 'PRIMARY']:
        idx = t.find(kw)
        if idx > 0:
            t = t[:idx].strip()
    if t.endswith(' NULL'):
        t = t[:-5].strip()

    m = re.match(r'VARCHAR\s*\(\s*(\d+)\s*\)', t)
    if m:
        return 'varchar', int(m.group(1))
    if t.startswith('TIMESTAMP'):
        return 'timestamp', None

    mapping = {
        'SERIAL': ('int4', None), 'BIGSERIAL': ('int8', None),
        'BIGINT': ('int8', None), 'INT': ('int4', None), 'INTEGER': ('int4', None),
        'SMALLINT': ('int2', None), 'TEXT': ('text', None),
        'JSONB': ('jsonb', None), 'JSON': ('json', None),
        'BOOLEAN': ('bool', None), 'REAL': ('float4', None),
        'DOUBLE PRECISION': ('float8', None), 'DATE': ('date', None),
    }
    return mapping.get(t, (t.lower(), None))


def build_pg_type_string(udt_name, max_length=None):
    """Konversi udt_name ke SQL type string untuk ALTER COLUMN."""
    type_map = {
        'int4': 'INTEGER', 'int8': 'BIGINT', 'int2': 'SMALLINT',
        'varchar': f'VARCHAR({max_length})' if max_length else 'TEXT',
        'text': 'TEXT', 'timestamp': 'TIMESTAMP', 'jsonb': 'JSONB',
        'json': 'JSON', 'bool': 'BOOLEAN', 'float4': 'REAL',
        'float8': 'DOUBLE PRECISION', 'date': 'DATE',
    }
    return type_map.get(udt_name, udt_name.upper())


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


def run_schema_migration(cursor, existing_tables, replace=False):
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

            if table_name in existing_tables and not replace:
                print(f"  ⏭️  Tabel '{table_name}' sudah ada → Pengecekan kolom, tipe data & constraint...")
                
                match_content = re.search(r'\((.*)\)', stmt, flags=re.IGNORECASE | re.DOTALL)
                if match_content:
                    columns_content = match_content.group(1)
                    col_defs = [c.strip() for c in columns_content.split('\n') if c.strip()]
                    
                    existing_cols_info = get_existing_columns_with_types(cursor, table_name)
                    existing_cols = set(existing_cols_info.keys())
                    existing_constraints = get_existing_constraints(cursor, table_name)
                    
                    for col_def in col_defs:
                        if col_def.endswith(','):
                            col_def = col_def[:-1].strip()
                        if not col_def:
                            continue

                        # --- CONSTRAINT: cek apakah sudah ada, tambahkan jika belum ---
                        if col_def.upper().startswith('CONSTRAINT'):
                            cmatch = re.match(r'CONSTRAINT\s+[`"]?(\w+)[`"]?\s+(.*)', col_def, re.IGNORECASE | re.DOTALL)
                            if cmatch:
                                cname = cmatch.group(1)
                                if cname not in existing_constraints:
                                    try:
                                        cursor.execute(f'ALTER TABLE "{table_name}" ADD {col_def}')
                                        print(f"  ✅ [CONSTRAINT] Ditambahkan '{cname}' pada '{table_name}'")
                                        created += 1
                                    except Exception as e:
                                        if 'already exists' not in str(e).lower():
                                            print(f"  ⚠️  [CONSTRAINT] Skip '{cname}': {e}")
                            continue
                            
                        # Skip non-column definitions lainnya
                        if col_def.upper().startswith(('PRIMARY', 'FOREIGN', 'UNIQUE(', 'UNIQUE ', 'INDEX', 'KEY', 'FULLTEXT')):
                            continue
                            
                        # --- COLUMN: cek ada/tidaknya dan tipe datanya ---
                        parts = col_def.split(maxsplit=1)
                        if not parts:
                            continue
                        col_name = parts[0].strip('`"')
                        
                        if col_name and col_name not in existing_cols:
                            # Kolom belum ada → ADD COLUMN
                            try:
                                cursor.execute(f'ALTER TABLE "{table_name}" ADD COLUMN {col_def}')
                                print(f"  ✅ [ADD COLUMN] '{col_name}' ke '{table_name}'")
                                created += 1
                            except Exception as e:
                                if 'already exists' not in str(e).lower():
                                    print(f"  ❌ [ADD COLUMN] Gagal '{col_name}': {e}")
                        elif col_name and len(parts) > 1 and col_name in existing_cols_info:
                            # Kolom sudah ada → Cek apakah tipe data berubah
                            info = existing_cols_info[col_name]
                            # Skip kolom auto-increment (SERIAL/BIGSERIAL)
                            if 'nextval' in str(info.get('column_default') or ''):
                                continue
                            expected_udt, expected_len = normalize_sql_type_to_pg(parts[1])
                            actual_udt = info['udt_name']
                            actual_len = info.get('character_maximum_length')
                            
                            type_changed = (expected_udt != actual_udt)
                            len_changed = (expected_udt == 'varchar' and expected_len and actual_len and expected_len != actual_len)
                            
                            if type_changed or len_changed:
                                pg_type = build_pg_type_string(expected_udt, expected_len)
                                if actual_udt == 'varchar' and expected_udt in ('int4', 'int8', 'int2'):
                                    using = f'USING NULLIF("{col_name}", \'\')::{pg_type}'
                                else:
                                    using = f'USING "{col_name}"::{pg_type}'
                                try:
                                    cursor.execute(f'ALTER TABLE "{table_name}" ALTER COLUMN "{col_name}" TYPE {pg_type} {using}')
                                    print(f"  ✅ [ALTER TYPE] '{table_name}.{col_name}': {actual_udt} → {expected_udt}")
                                    created += 1
                                except Exception as e:
                                    print(f"  ⚠️  [ALTER TYPE] Skip '{col_name}': {e}")
                
            else:
                if replace and table_name in existing_tables:
                    try:
                        cursor.execute(f"DROP TABLE IF EXISTS \"{table_name}\" CASCADE")
                        existing_tables.remove(table_name)
                        print(f"  🗑️  [REPLACE] Tabel '{table_name}' di-drop.")
                    except Exception as e:
                        print(f"  ❌ Gagal drop tabel '{table_name}': {e}")

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


def fix_db(replace=False):
    """Main entry point: jalankan schema migration + seed data."""
    print("=" * 60)
    print("🔧 Smart Database Migration Runner")
    if replace:
        print("⚠️  Mode REPLACE AKTIF: Tabel yang sudah ada akan dihapus dan dibuat ulang!")
    print("=" * 60)
    
    print("\n🔌 Connecting to database...")
    conn = get_connection()
    if not conn:
        print("❌ Gagal konek ke database!")
        return

    conn.autocommit = True
    # Pakai dictionary=False supaya SHOW TABLES return tuple
    cursor = conn.cursor()
    
    try:
        # 1. Ambil tabel yang sudah ada
        existing_tables = get_existing_tables(cursor)
        print(f"📊 Tabel yang sudah ada: {len(existing_tables)} tabel")

        # 2. Jalankan schema migration
        schema_created, schema_skipped = run_schema_migration(cursor, existing_tables, replace)

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
    parser = argparse.ArgumentParser(description="Smart Database Migration Runner")
    parser.add_argument('--replace', action='store_true', help="Drop dan jalankan ulang semua CREATE TABLE")
    args = parser.parse_args()

    if sys.stdout.encoding.lower() != 'utf-8':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    fix_db(replace=args.replace)
