import os
import secrets
from cryptography.fernet import Fernet

def generate_and_update_env():
    print("--- Secret Key Generator ---")
    
    # 1. Generate Strong Keys
    # SECRET_KEY using Fernet (symmetric encryption key)
    secret_key = Fernet.generate_key().decode()
    
    # CSRF_SECRET_KEY using standard secrets module (hex token)
    csrf_secret_key = secrets.token_hex(32)
    
    print(f"\n[NEW] SECRET_KEY: {secret_key}")
    print(f"[NEW] CSRF_SECRET_KEY: {csrf_secret_key}")
    
    env_path = '.env'
    
    # 2. Read existing .env content
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    else:
        lines = []
        print(f"\nWarning: '{env_path}' not found. A new file will be created.")

    # 3. Prepare new content
    new_lines = []
    keys_updated = {'SECRET_KEY': False, 'CSRF_SECRET_KEY': False}
    
    # Parse existing lines and replace if key exists
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('SECRET_KEY='):
            new_lines.append(f'SECRET_KEY={secret_key}\n')
            keys_updated['SECRET_KEY'] = True
        elif stripped.startswith('CSRF_SECRET_KEY='):
            new_lines.append(f'CSRF_SECRET_KEY={csrf_secret_key}\n')
            keys_updated['CSRF_SECRET_KEY'] = True
        else:
            new_lines.append(line)
    
    # Ensure there is a newline at the end of existing content before appending
    if new_lines and not new_lines[-1].endswith('\n'):
        new_lines[-1] += '\n'
            
    # Append if keys didn't exist
    if not keys_updated['SECRET_KEY']:
        new_lines.append(f'SECRET_KEY={secret_key}\n')
    if not keys_updated['CSRF_SECRET_KEY']:
        new_lines.append(f'CSRF_SECRET_KEY={csrf_secret_key}\n')

    # 4. Confirm and Write
    print(f"\nPreparing to update '{env_path}'...")
    if keys_updated['SECRET_KEY']:
        print(" -> Existing SECRET_KEY will be REPLACED.")
    else:
        print(" -> SECRET_KEY will be APPENDED.")
        
    if keys_updated['CSRF_SECRET_KEY']:
        print(" -> Existing CSRF_SECRET_KEY will be REPLACED.")
    else:
        print(" -> CSRF_SECRET_KEY will be APPENDED.")
        
    confirm = input("\nProceed to write to .env? (y/N): ").strip().lower()
    
    if confirm == 'y':
        try:
            with open(env_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            print(f"\nSuccess! '{env_path}' has been updated.")
        except Exception as e:
            print(f"\nError writing to file: {e}")
    else:
        print("\nOperation cancelled by user.")

if __name__ == "__main__":
    generate_and_update_env()