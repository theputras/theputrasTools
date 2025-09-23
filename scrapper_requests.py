import os
import requests
from bs4 import BeautifulSoup
import pandas as pd
from dotenv import load_dotenv
from urllib.parse import urljoin
import urllib.parse as urlparse
import re
import time
import json
from datetime import datetime, timedelta


# Setup environment variables
load_dotenv()
USER = os.getenv("SICYCA_USER")
PASS = os.getenv("SICYCA_PASS")
if not USER or not PASS:
    raise SystemExit("Set SICYCA_USER dan SICYCA_PASS di .env")

TARGET_URL = "https://sicyca.dinamika.ac.id/akademik"
GATE_ROOT = "https://gate.dinamika.ac.id"
sess = requests.Session()
sess.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
})
def absolute(base, link):
    return urlparse.urljoin(base, link)

def dump_history(resp):
    print("Redirect chain:")
    for i, h in enumerate(resp.history):
        print(f"  {i}: {h.status_code} -> {h.url}")
    print(f" final: {resp.status_code} -> {resp.url}")
COOKIES_FILE = "cookies.json"

# Mengecek apakah cookies valid
def check_cookies_validity():
    if os.path.exists(COOKIES_FILE):
        try:
            with open(COOKIES_FILE, 'r') as f:
                cookies_data = json.load(f)
                last_access_time = datetime.strptime(cookies_data['last_access_time'], "%Y-%m-%d %H:%M:%S")
                current_time = datetime.now()
                time_diff = current_time - last_access_time
                if time_diff > timedelta(minutes=30):  # Ganti dengan interval yang diinginkan (misalnya 30 menit)
                    print("Cookies expired, removing cookies...")
                    os.remove(COOKIES_FILE)
                    return False
                else:
                    print("Cookies are valid, last access:", last_access_time)
                    return True
        except json.JSONDecodeError:
            print("Error reading cookies file. The file might be corrupted.")
            return False
    return False

# Menyimpan cookies ke file
def save_cookies_to_file():
    cookies = sess.cookies.get_dict()
    cookies_data = {
        'cookies': cookies,
        'last_access_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(COOKIES_FILE, 'w') as f:
        json.dump(cookies_data, f)
    print("Cookies saved to cookies.json")

# Memuat cookies dari file
def load_cookies_from_file():
    if os.path.exists(COOKIES_FILE):
        try:
            with open(COOKIES_FILE, 'r') as f:
                cookies_data = json.load(f)
                for cookie_name, cookie_value in cookies_data['cookies'].items():
                    sess.cookies.set(cookie_name, cookie_value)
                print("Cookies loaded successfully.")
        except json.JSONDecodeError:
            print("Error reading cookies file. The file might be corrupted.")
            return False
    return True


# def scrape_data():

#     # 1) Mulai dari gate root untuk dapat route /login
#     r = sess.get(GATE_ROOT, allow_redirects=True, timeout=30)
#     r.raise_for_status()

#     # 2) Ambil form login
#     soup = BeautifulSoup(r.text, "lxml")
#     form = soup.find("form")
#     if not form:
#         raise SystemExit("Gagal menemukan form login di gate.")

#     action_url = absolute(r.url, form.get("action"))
#     payload = {inp.get("name"): inp.get("value", "") for inp in form.find_all("input")}
#     payload["username"] = USER
#     payload["password"] = PASS

#     # Kirim form login ke gate
#     resp = sess.post(action_url, data=payload, allow_redirects=True, timeout=30)

#     # 3) Paksa akses halaman akademik
#     resp_ak1 = sess.get(TARGET_URL, allow_redirects=False, timeout=30, headers={"Referer": TARGET_URL})
#     if resp_ak1.is_redirect and "/sso_login.php" in resp_ak1.headers.get("Location",""):
#         resp_sso = sess.get(urljoin(TARGET_URL, resp_ak1.headers["Location"]), timeout=30)
#         resp_ak2 = sess.get(TARGET_URL, timeout=30, headers={"Referer": TARGET_URL})
#     else:
#         resp_ak2 = sess.get(TARGET_URL, timeout=30, headers={"Referer": TARGET_URL})

#     resp_ak2.raise_for_status()

#     # Parsing tabel 'JADWAL KEGIATAN MINGGU INI'
#     soup = BeautifulSoup(resp_ak2.text, "lxml")

#     target_div = None
#     for div in soup.select("div.tabletitle"):
#         txt = div.get_text(" ", strip=True).upper()
#         if "JADWAL KEGIATAN MINGGU INI" in txt:
#             target_div = div
#             break

#     if not target_div:
#         raise SystemExit("Tidak ketemu div.tabletitle 'JADWAL KEGIATAN MINGGU INI'")

#     table = target_div.find_next("table", class_=re.compile(r"\bsicycatable\b"))
#     if not table:
#         raise SystemExit("Tabel class 'sicycatable' tidak ketemu setelah title.")

#     headers = [th.get_text(strip=True) for th in table.find_all("th")]
#     rows = []
#     for tr in table.find_all("tr"):
#         cols = [td.get_text(strip=True) for td in tr.find_all("td")]
#         if cols:
#             rows.append(cols)

#     if headers and rows and len(headers) != len(rows[0]):
#         rows = [r[:len(headers)] if len(r) > len(headers) else r + [""]*(len(headers)-len(r)) for r in rows]

#     df = pd.DataFrame(rows, columns=headers if headers else None)
#     return df
    
    
def scrape_data():
    try:
    
        # 1) Mulai dari gate root untuk dapat route /login
        print("1) GET gate root:", GATE_ROOT)
        r = sess.get(GATE_ROOT, allow_redirects=True, timeout=30)
        r.raise_for_status()
        dump_history(r)
        
        # Jika sudah diarahkan langsung ke /login, pakai page itu.
        login_page_url = r.url
        print("Login page url:", login_page_url)
        
        # 2) Ambil form login (ambil semua input hidden juga)
        soup = BeautifulSoup(r.text, "lxml")
        form = soup.find("form")
        if not form:
            # coba akses explicit /login
            print("Form tidak ketemu. Coba /login langsung.")
            r = sess.get(absolute(login_page_url, "/login"), allow_redirects=True, timeout=30)
            r.raise_for_status()
            dump_history(r)
            soup = BeautifulSoup(r.text, "lxml")
            form = soup.find("form")
            if not form:
                raise SystemExit("Gagal menemukan form login di gate. Periksa manual via browser.")
        
        action = form.get("action") or r.url
        action_url = absolute(r.url, action)
        method = (form.get("method") or "post").lower()
        print("Form action:", action_url, "method:", method)
        
        # kumpulkan semua input (hidden + default)
        payload = {}
        for inp in form.find_all("input"):
            name = inp.get("name")
            if not name:
                continue
            payload[name] = inp.get("value", "")
        
        # heuristik: isi username/password ke nama field yang ada
        user_keys = ["username", "user", "email", "nim", "identity", "login"]
        pass_keys = ["password", "pass", "passwd", "pwd"]
        
        def try_set(keys, value):
            for k in keys:
                if k in payload:
                    payload[k] = value
                    return True
            return False
        
        # jika tidak ada nama user yang match, cari input text pertama
        if not any(k in payload for k in user_keys):
            # cari input text di form
            text_input = form.find("input", {"type": "text"})
            if text_input and text_input.get("name"):
                payload[text_input["name"]] = USER
            else:
                # fallback: tambahkan field dengan nama 'username'
                payload["username"] = USER
        else:
            try_set(user_keys, USER)
        
        if not any(k in payload for k in pass_keys):
            pw_input = form.find("input", {"type": "password"})
            if pw_input and pw_input.get("name"):
                payload[pw_input["name"]] = PASS
            else:
                payload["password"] = PASS
        else:
            try_set(pass_keys, PASS)
        
        print("Payload keys sent:", list(payload.keys()))
        
        # 3) Set header referer/origin
        origin = "{uri.scheme}://{uri.netloc}".format(uri=urlparse.urlparse(action_url))
        headers = {
            "Referer": r.url,
            "Origin": origin,
            # "Content-Type": "application/x-www-form-urlencoded"  # requests set otomatis
        }
        
        # 4) Submit form (POST atau GET sesuai form)
        print("Mengirim kredensial ke gate...")
        if method == "post":
            resp = sess.post(action_url, data=payload, allow_redirects=True, timeout=30, headers=headers)
        else:
            resp = sess.get(action_url, params=payload, allow_redirects=True, timeout=30, headers=headers)
        resp.raise_for_status()
        dump_history(resp)
        
        # 5) Jika ada intermediate auto-post forms (SAML), coba loop untuk max 5 lompatan
        html = resp.text
        cur_url = resp.url
        for i in range(5):
            soup = BeautifulSoup(html, "lxml")
            form = soup.find("form")
            if not form:
                break
            action = form.get("action") or cur_url
            action_url = absolute(cur_url, action)
            method = (form.get("method") or "post").lower()
            payload2 = {}
            for inp in form.find_all("input"):
                name = inp.get("name")
                if not name:
                    continue
                payload2[name] = inp.get("value", "")
            print(f"Auto-post form detected. Submitting to {action_url} (method={method}) keys={list(payload2.keys())}")
            if method == "post":
                r2 = sess.post(action_url, data=payload2, allow_redirects=True, timeout=30, headers={"Referer": cur_url})
            else:
                r2 = sess.get(action_url, params=payload2, allow_redirects=True, timeout=30, headers={"Referer": cur_url})
            r2.raise_for_status()
            dump_history(r2)
            html = r2.text
            cur_url = r2.url
        
        # 6) setelah submit login dan auto-redirect
        print("Final URL:", resp.url)
        
        
        # 7) HANYA di sicyca: force GET /akademik, cek redirect, lalu parse
        
        
        AK_URL = "https://sicyca.dinamika.ac.id/akademik"
        
        # a) GET pertama ke /akademik TANPA follow redirect (biar ketahuan kalau masih mau lari ke gate atau dashboard)
        resp_ak1 = sess.get(AK_URL, allow_redirects=False, timeout=30, headers={"Referer": "https://sicyca.dinamika.ac.id/"})
        print("Step7.1:", resp_ak1.status_code, resp_ak1.url)
        if resp_ak1.is_redirect:
            loc = resp_ak1.headers.get("Location","")
            print("Redirect ->", loc)
        
        # b) Kalau 302 ke /sso_login.php, ikuti sekali, lalu PAKSA balik GET /akademik lagi
        if resp_ak1.is_redirect and "/sso_login.php" in resp_ak1.headers.get("Location",""):
            # follow sekali
            resp_sso = sess.get(urljoin(AK_URL, resp_ak1.headers["Location"]), timeout=30)
            print("Step7.2 after sso:", resp_sso.status_code, resp_sso.url)
            # paksa balik ke /akademik lagi
            resp_ak2 = sess.get(AK_URL, timeout=30, headers={"Referer": "https://sicyca.dinamika.ac.id/"})
        else:
            # kalau tidak redirect, langsung pakai resp_ak1 atau follow normal
            resp_ak2 = sess.get(AK_URL, timeout=30, headers={"Referer": "https://sicyca.dinamika.ac.id/"})
        
        resp_ak2.raise_for_status()
        print("Step7.3 final:", resp_ak2.status_code, resp_ak2.url)
        
        # c) Validasi domain HARUS sicyca
        if "sicyca.dinamika.ac.id" not in resp_ak2.url:
            print("Masih bukan halaman sicyca. Stop agar tidak balik ke gate.")
            raise SystemExit("Masih bukan halaman sicyca. Stop agar tidak balik ke gate.")
        
        # d) Parse tabel 'JADWAL KEGIATAN MINGGU INI' (div.tabletitle + table.sicycatable)
        soup = BeautifulSoup(resp_ak2.text, "lxml")
        
        # Loop semua title, cocokkan dengan get_text (karena ada span di dalamnya)
        target_div = None
        for div in soup.select("div.tabletitle"):
            txt = div.get_text(" ", strip=True).upper()
            if "JADWAL KEGIATAN MINGGU INI" in txt:
                target_div = div
                break
        
        if not target_div:
            # Simpan HTML untuk cek
            with open("debug_akademik.html", "w", encoding="utf-8") as f:
                f.write(resp_ak2.text)
            print("Tidak ketemu div.tabletitle 'JADWAL KEGIATAN MINGGU INI'. HTML disimpan ke debug_akademik.html")
            raise SystemExit("Tidak ketemu div.tabletitle 'JADWAL KEGIATAN MINGGU INI'. HTML disimpan ke debug_akademik.html")
        
        table = target_div.find_next("table", class_=re.compile(r"\bsicycatable\b"))
        if not table:
            with open("debug_akademik.html", "w", encoding="utf-8") as f:
                f.write(resp_ak2.text)
            print("Tabel class 'sicycatable' tidak ketemu setelah title. Cek debug_akademik.html")
            raise SystemExit("Tabel class 'sicycatable' tidak ketemu setelah title. Cek debug_akademik.html")
        
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        rows = []
        for tr in table.find_all("tr"):
            cols = [td.get_text(strip=True) for td in tr.find_all("td")]
            if cols:
                rows.append(cols)
        
        # Amankan mismatch kolom
        if headers and rows and len(headers) != len(rows[0]):
            rows = [r[:len(headers)] if len(r) > len(headers) else r + [""]*(len(headers)-len(r)) for r in rows]

        df = pd.DataFrame(rows, columns=headers if headers else None)
        
        # Logout setelah mendapatkan data
        logout()
        # Print column names to check if 'Nama Mata Kuliah' is present
        print("Columns in DataFrame:", df.columns)

        # Clean column names to ensure no extra spaces or hidden characters
        df.columns = df.columns.str.strip()

         # Check if 'Nama Matakuliah' column exists
        if 'Nama Matakuliah' not in df.columns:
            raise ValueError("Column 'Nama Matakuliah' is missing from the DataFrame")

        # Convert DataFrame to list of dictionaries for ICS generation
        events = []
        for index, row in df.iterrows():
            # Remove the weekday name (e.g., "Selasa, ") from the start of the date string
            start_time_str = re.sub(r"^\w+, ", "", row['Hari, Tanggal']) + ' ' + row['Jam'].split('-')[0]
            end_time_str = re.sub(r"^\w+, ", "", row['Hari, Tanggal']) + ' ' + row['Jam'].split('-')[1]

            # Parse the date and time
            start_time = datetime.strptime(start_time_str, "%d %B %Y %H:%M")
            end_time = datetime.strptime(end_time_str, "%d %B %Y %H:%M")

            # Check if 'Nama Matakuliah' is missing for any row
            if pd.isna(row['Nama Matakuliah']):
                raise ValueError(f"Missing 'Nama Matakuliah' at row {index + 1}")
                
            event = {
                'start_time': start_time.strftime("%d %B %Y %H:%M"),
                'end_time': end_time.strftime("%d %B %Y %H:%M"),
                'summary': row['Nama Matakuliah'],
                'location': row['Ruangan'],
                'description': row['Nama Matakuliah'],  # Adjust this as needed
                'status': row['Status Kuliah']
            }
            events.append(event)
        
        return events
        
        return events
    except Exception as e:
        print(f"Error scraping: {e}")
        raise

# Fungsi untuk logout
def logout():
    print("Logging out...")
    logout_url = "https://gate.dinamika.ac.id/logout"  # Sesuaikan dengan URL logout yang benar
    resp = sess.get(logout_url, timeout=30)
    resp.raise_for_status()
    print("Successfully logged out.")

def absolute(base, link):
    return urljoin(base, link)
