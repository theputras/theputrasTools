# daily_scraper.py

from scrapper_requests import scrape_data
from datetime import datetime

CSV_FILE = "jadwal.csv"

def run_and_save():
    """
    Menjalankan scraper dan menyimpan hasilnya ke file CSV.
    """
    print(f"[{datetime.now()}] Memulai tugas scraping harian...")
    
    df = scrape_data()
    
    if not df.empty:
        df.to_csv(CSV_FILE, index=False)
        print(f"[{datetime.now()}] Data berhasil disimpan ke {CSV_FILE}. Total: {len(df)} jadwal.")
    else:
        print(f"[{datetime.now()}] Gagal mengambil data atau tidak ada jadwal. File CSV tidak diubah.")

if __name__ == "__main__":
    run_and_save()