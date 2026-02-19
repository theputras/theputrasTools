# debug_gate_login.py (REVISI)
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import logging
from models.gate import GateUser

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def debug_login():
    print("\n" + "="*50)
    print("   DIAGNOSA LOGIN GATE DINAMIKA (REVISI)   ")
    print("="*50 + "\n")

    # 1. AMBIL KREDENSIAL DARI DB
    print("[1] Mengambil kredensial dari Database...")
    model = GateUser()
    user_id_db = 1 
    
    gate_id, g_user, g_pass = model.get_credentials_by_user_id(user_id_db)

    if not g_user:
        print("❌ GAGAL: User ID 1 tidak ditemukan.")
        return

    # === CEK INI BAIK-BAIK ===
    print(f"✅ User    : {g_user}")
    print(f"🔑 Pass    : {g_pass}") # <--- SAYA TAMPILKAN PASS ASLI BIAR JELAS
    print(f"   (Panjang: {len(g_pass)} karakter)")
    
    # 2. PERSIAPAN SESSION
    print("\n[2] Menyiapkan Session...")
    s = requests.Session()
    # Header lengkap seperti browser asli Chrome
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    })

    # 3. GET HALAMAN LOGIN (AMBIL TOKEN)
    print("\n[3] Mengakses halaman Login...")
    url_login = "https://gate.dinamika.ac.id/login"
    try:
        r = s.get(url_login, timeout=20)
        
        # Cek apakah sudah login (redirect ke dashboard)
        if r.url.rstrip('/') == "https://gate.dinamika.ac.id" and "login" not in r.text.lower():
             print("🎉 SUKSES: Ternyata sudah login (Session aktif)!")
             return
    except Exception as e:
        print(f"❌ Error Koneksi: {e}")
        return

    # 4. ANALISA FORM & TOKEN
    soup = BeautifulSoup(r.text, "html.parser")
    form = soup.find("form", id="gate-login-form")
    if not form: form = soup.find("form", id="gate-login-form-2")
    
    if not form:
        print("❌ FATAL: Form login tidak ditemukan.")
        return

    print("\n[4] Menyusun Payload...")
    payload = {}
    inputs = form.find_all("input")
    
    for inp in inputs:
        name = inp.get("name")
        val = inp.get("value", "")
        if name: payload[name] = val

    # INPUT KREDENSIAL
    payload['userid'] = g_user
    payload['password'] = g_pass
    
    print(f"   Payload Akhir: {payload}")

    # 5. EKSEKUSI LOGIN (DENGAN HEADER KHUSUS)
    print("\n[5] Mengirim POST Login...")
    action = form.get("action") or url_login
    full_action = urljoin(r.url, action)
    
    # Header Origin & Referer WAJIB ADA untuk login Laravel/PHP modern
    headers_post = {
        "Origin": "https://gate.dinamika.ac.id",
        "Referer": url_login,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    try:
        r_post = s.post(full_action, data=payload, headers=headers_post, allow_redirects=True)
        print(f"   Status POST: {r_post.status_code}")
        print(f"   URL Akhir  : {r_post.url}")
    except Exception as e:
        print(f"❌ Error POST: {e}")
        return

    # 6. ANALISA HASIL
    print("\n[6] Hasil Akhir:")
    
    # Cek Indikator Kegagalan
    if "login" in r_post.url:
        print("❌ LOGIN GAGAL: Masih di URL login.")
    elif "sicyca.dinamika.ac.id" in r_post.url:
        print("🎉 LOGIN SUKSES: Masuk Sicyca!")
    elif r_post.url.rstrip('/') == "https://gate.dinamika.ac.id":
        # Cek konten halamannya, apakah ada tombol login?
        if 'id="login-dropdown"' in r_post.text:
             print("❌ LOGIN GAGAL: Masih ada tombol LOGIN di homepage.")
        else:
             print("🎉 LOGIN SUKSES: Masuk Dashboard Gate!")
    else:
        print("⚠️ STATUS TIDAK JELAS.")

    # Simpan file buat cek manual
    with open("debug_result_v2.html", "w", encoding="utf-8") as f:
        f.write(r_post.text)
    print("   (HTML hasil login disimpan ke debug_result_v2.html)")

if __name__ == "__main__":
    debug_login()