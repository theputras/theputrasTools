# scrapper_requests.py

import os
import requests
from bs4 import BeautifulSoup
import pandas as pd
from dotenv import load_dotenv
from urllib.parse import urljoin, urlparse
import re

# Setup environment variables
load_dotenv()
USER = os.getenv("SICYCA_USER")
PASS = os.getenv("SICYCA_PASS")
if not USER or not PASS:
    raise SystemExit("Set SICYCA_USER dan SICYCA_PASS di .env")

TARGET_URL = "https://sicyca.dinamika.ac.id/akademik"
GATE_ROOT = "https://gate.dinamika.ac.id"

def scrape_data():
    # Bagian ini (TAHAP 1 s/d 5) sudah benar dan tidak diubah
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
    })

    def absolute(base, link):
        return urljoin(base, link)

    try:
        print("1. Mengakses Gate dan mencari form login...")
        r = sess.get(GATE_ROOT, allow_redirects=True, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        form = soup.find("form")
        if not form: raise SystemExit("Gagal menemukan form login di gate.")

        action_url = absolute(r.url, form.get("action"))
        payload = {inp.get("name"): inp.get("value", "") for inp in form.find_all("input") if inp.get("name")}
        
        user_keys = ["username", "user", "email", "nim", "identity", "login", "userid"]
        pass_keys = ["password", "pass", "passwd", "pwd"]
        for key in user_keys:
            if key in payload: payload[key] = USER
        for key in pass_keys:
            if key in payload: payload[key] = PASS
        
        headers = {"Referer": r.url, "Origin": f"{urlparse(r.url).scheme}://{urlparse(r.url).netloc}"}
        
        print("2. Mengirim kredensial ke gate...")
        resp = sess.post(action_url, data=payload, allow_redirects=True, timeout=30, headers=headers)
        resp.raise_for_status()

        print("3. Menangani alur redirect SSO...")
        html = resp.text
        cur_url = resp.url
        for i in range(5):
            soup = BeautifulSoup(html, "lxml")
            form = soup.find("form")
            if not form: break
            
            action = form.get("action") or cur_url
            action_url = absolute(cur_url, action)
            method = (form.get("method") or "post").lower()
            payload2 = {inp.get("name"): inp.get("value", "") for inp in form.find_all("input") if inp.get("name")}
            
            print(f"   --> Auto-post form terdeteksi, mengirim ke {action_url.split('?')[0]}")
            r2 = sess.post(action_url, data=payload2, allow_redirects=True, timeout=30, headers={"Referer": cur_url})
            r2.raise_for_status()
            html = r2.text
            cur_url = r2.url

        print("4. Mengakses halaman Sicyca Akademik...")
        resp_ak1 = sess.get(TARGET_URL, allow_redirects=False, timeout=30)
        if resp_ak1.is_redirect and "/sso_login.php" in resp_ak1.headers.get("Location", ""):
            print("   --> Mengikuti redirect sso_login.php...")
            sso_url = urljoin(TARGET_URL, resp_ak1.headers["Location"])
            sess.get(sso_url, timeout=30, headers={"Referer": TARGET_URL})
        
        resp_ak2 = sess.get(TARGET_URL, timeout=30)
        resp_ak2.raise_for_status()

        if "sicyca.dinamika.ac.id" not in resp_ak2.url:
            raise SystemExit("Gagal mendarat di halaman sicyca.")

        print("5. Parsing tabel jadwal...")
        soup = BeautifulSoup(resp_ak2.text, "lxml")
        target_div = None
        for div in soup.select("div.tabletitle"):
            if "JADWAL KEGIATAN MINGGU INI" in div.get_text(" ", strip=True).upper():
                target_div = div
                break
        
        if not target_div:
            with open("debug_gagal_scrape.html", "w", encoding="utf-8") as f: f.write(resp_ak2.text)
            raise SystemExit("Tidak ketemu div 'JADWAL KEGIATAN MINGGU INI'.")

        table = target_div.find_next("table", class_=re.compile(r"\bsicycatable\b"))
        if not table: raise SystemExit("Tabel sicycatable tidak ketemu.")

        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        rows = [[td.get_text(strip=True) for td in tr.find_all("td")] for tr in table.find_all("tr") if tr.find("td")]

        df_raw = pd.DataFrame(rows, columns=headers)
        df_raw.columns = df_raw.columns.str.strip()
        print(f"   --> Kolom yang terdeteksi di tabel: {df_raw.columns.tolist()}")
        
        # TAHAP 6: Membersihkan data dan Logout
        print("6. Membersihkan data dan melakukan logout...")
        sess.get(urljoin(GATE_ROOT, "/logout"), timeout=30)
        return df_raw
        
    except Exception as e:
        print(f"Error saat scraping: {e}")
        return pd.DataFrame()