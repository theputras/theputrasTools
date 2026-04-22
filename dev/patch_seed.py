import re
import os
import sys

sys.path.append(os.getcwd())
from controller.KonselorController import encrypt_nim
from dotenv import load_dotenv

load_dotenv()

seed_path = "Seed theputrasTools.sql"
with open(seed_path, "r", encoding="utf-8") as f:
    sql_content = f.read()

# We want to replace TO_BASE64(AES_ENCRYPT('NIM', 'secret_key')) 
# with the ACTUAL string value: 'encrypt_nim("NIM")'

def replacer(match):
    nim = match.group(1)
    encrypted_str = encrypt_nim(nim)
    return f"'{encrypted_str}'"

# regex pattern to match TO_BASE64(AES_ENCRYPT('12345', 'secret_key'))
pattern = r"TO_BASE64\(AES_ENCRYPT\('(\d+)',\s*'secret_key'\)\)"

new_sql_content = re.sub(pattern, replacer, sql_content)

with open(seed_path, "w", encoding="utf-8") as f:
    f.write(new_sql_content)

print("Seed file updated with Fernet tokens!")
