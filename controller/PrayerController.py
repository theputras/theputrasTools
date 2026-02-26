# controller/PrayerController.py
# Controller untuk fitur Jadwal Sholat, Kalender Hijriah, dan Ramadhan
# Menggunakan API Aladhan (https://aladhan.com/prayer-times-api)

import logging
import requests
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from models.prayer import prayer_settings_model, ramadan_config_model

JKT = ZoneInfo("Asia/Jakarta")

# Base URL Aladhan API
ALADHAN_BASE = "https://api.aladhan.com/v1"

# Default method: 11 = MUIS (Singapore) — terdekat ke standar Kemenag RI
DEFAULT_METHOD = 11

NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
NOMINATIM_HEADERS = {"User-Agent": "theputrasTools/1.0"}


# =============================================================
# LOCATION SEARCH FUNCTIONS (Nominatim proxy)
# =============================================================

def search_location(query, limit=8):
    """
    Cari lokasi via Nominatim search API.
    Return: list of {display, city, country} atau kosong.
    """
    if not query or len(query) < 2:
        return []

    try:
        resp = requests.get(f"{NOMINATIM_BASE}/search", params={
            "q": query,
            "format": "json",
            "addressdetails": 1,
            "limit": limit,
            "accept-language": "id,en"
        }, headers=NOMINATIM_HEADERS, timeout=5)
        resp.raise_for_status()
        results = resp.json()

        locations = []
        seen = set()
        for r in results:
            addr = r.get("address", {})
            city = addr.get("city") or addr.get("town") or addr.get("municipality") or addr.get("village") or addr.get("county") or ""
            state = addr.get("state") or ""
            country = addr.get("country") or ""

            if not city:
                continue

            # Build display text
            parts = [p for p in [city, state, country] if p]
            display = ", ".join(parts)

            # Deduplicate
            key = f"{city.lower()}|{country.lower()}"
            if key in seen:
                continue
            seen.add(key)

            locations.append({
                "display": display,
                "city": city,
                "state": state,
                "country": country
            })

        return locations

    except Exception as e:
        logging.error(f"[Location] Search error: {e}")
        return []


def reverse_geocode(lat, lon):
    """
    Reverse geocode dari koordinat GPS → city + country.
    Return: dict {city, state, country, display} atau None.
    """
    try:
        resp = requests.get(f"{NOMINATIM_BASE}/reverse", params={
            "lat": lat,
            "lon": lon,
            "format": "json",
            "accept-language": "id,en"
        }, headers=NOMINATIM_HEADERS, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        if data and data.get("address"):
            addr = data["address"]
            city = addr.get("city") or addr.get("town") or addr.get("municipality") or addr.get("village") or addr.get("county") or ""
            state = addr.get("state") or ""
            country = addr.get("country") or ""
            parts = [p for p in [city, state, country] if p]
            return {
                "city": city,
                "state": state,
                "country": country,
                "display": ", ".join(parts)
            }
        return None

    except Exception as e:
        logging.error(f"[Location] Reverse geocode error: {e}")
        return None


# =============================================================
# ALADHAN API FUNCTIONS
# =============================================================

def fetch_prayer_times(city, country, method=DEFAULT_METHOD, date_str=None):
    """
    Panggil Aladhan API untuk jadwal sholat hari tertentu.
    date_str format: DD-MM-YYYY (default: hari ini)
    Return: dict timings atau None jika error
    """
    if not date_str:
        now = datetime.now(JKT)
        date_str = now.strftime("%d-%m-%Y")

    try:
        url = f"{ALADHAN_BASE}/timingsByCity/{date_str}"
        params = {
            "city": city,
            "country": country,
            "method": method
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()

        data = resp.json()
        if data.get("code") == 200 and data.get("data"):
            result = data["data"]
            timings = result.get("timings", {})
            hijri_date = result.get("date", {}).get("hijri", {})
            gregorian_date = result.get("date", {}).get("gregorian", {})

            return {
                "timings": {
                    "Imsak": timings.get("Imsak"),
                    "Fajr": timings.get("Fajr"),       # Subuh
                    "Sunrise": timings.get("Sunrise"),   # Terbit
                    "Dhuhr": timings.get("Dhuhr"),       # Dzuhur
                    "Asr": timings.get("Asr"),           # Ashar
                    "Maghrib": timings.get("Maghrib"),   # Maghrib
                    "Isha": timings.get("Isha"),         # Isya
                },
                "hijri": hijri_date,
                "gregorian": gregorian_date,
                "meta": result.get("meta", {})
            }
        return None

    except requests.RequestException as e:
        logging.error(f"[Prayer] Aladhan API error (timings): {e}")
        return None
    except Exception as e:
        logging.error(f"[Prayer] Unexpected error fetch_prayer_times: {e}")
        return None


def fetch_monthly_calendar(city, country, month, year, method=DEFAULT_METHOD, adj=0):
    """
    Panggil Aladhan API untuk kalender sebulan (termasuk data Hijriah).
    Return: list of day data atau empty list
    """
    try:
        url = f"{ALADHAN_BASE}/calendarByCity/{year}/{month}"
        params = {
            "city": city,
            "country": country,
            "method": method
        }
        if adj != 0:
            params["adjustment"] = adj

        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()

        data = resp.json()
        if data.get("code") == 200 and data.get("data"):
            return data["data"]
        return []

    except requests.RequestException as e:
        logging.error(f"[Prayer] Aladhan API error (calendar): {e}")
        return []
    except Exception as e:
        logging.error(f"[Prayer] Unexpected error fetch_monthly_calendar: {e}")
        return []


# Hari-hari besar Islam (hijri month, hijri day) → label
ISLAMIC_HOLIDAYS = {
    (1, 1): "Tahun Baru Hijriah",
    (1, 10): "Hari Asyura",
    (3, 12): "Maulid Nabi Muhammad SAW",
    (7, 27): "Isra Mi'raj",
    (8, 15): "Nisfu Sya'ban",
    (9, 1): "1 Ramadhan",
    (9, 17): "Nuzulul Quran",
    (10, 1): "Idul Fitri",
    (10, 2): "Idul Fitri (Hari ke-2)",
    (12, 8): "Hari Tarwiyah",
    (12, 9): "Wukuf di Arafah",
    (12, 10): "Idul Adha",
    (12, 11): "Hari Tasyrik 1",
    (12, 12): "Hari Tasyrik 2",
    (12, 13): "Hari Tasyrik 3",
}


def fetch_global_hijri_calendar(month, year):
    """
    Ambil kalender Hijriah global (tanpa city/country).
    Mengunakan Aladhan gToHCalendar API.
    Return: list of formatted day data
    """
    try:
        url = f"{ALADHAN_BASE}/gToHCalendar/{month}/{year}"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()

        data = resp.json()
        if data.get("code") != 200 or not data.get("data"):
            return []

        formatted_days = []
        for day in data["data"]:
            hijri = day.get("hijri", {})
            gregorian = day.get("gregorian", {})

            h_month_num = int(hijri.get("month", {}).get("number", 0))
            h_day_num = int(hijri.get("day", "0"))

            # Check Islamic holidays
            holiday = ISLAMIC_HOLIDAYS.get((h_month_num, h_day_num), "")

            formatted_days.append({
                "gregorian_date": gregorian.get("date", ""),
                "gregorian_day": gregorian.get("day", ""),
                "gregorian_weekday": gregorian.get("weekday", {}).get("en", ""),
                "hijri_date": hijri.get("date", ""),
                "hijri_day": hijri.get("day", ""),
                "hijri_month": hijri.get("month", {}).get("en", ""),
                "hijri_month_ar": hijri.get("month", {}).get("ar", ""),
                "hijri_month_number": h_month_num,
                "hijri_year": hijri.get("year", ""),
                "holiday": holiday
            })

        return formatted_days

    except requests.RequestException as e:
        logging.error(f"[Prayer] Aladhan API error (global calendar): {e}")
        return []
    except Exception as e:
        logging.error(f"[Prayer] Unexpected error fetch_global_hijri_calendar: {e}")
        return []


# =============================================================
# USER-FACING FUNCTIONS (gabungkan settings + API)
# =============================================================

def get_prayer_schedule_for_user(user_id):
    """
    Ambil jadwal sholat hari ini untuk user tertentu.
    Logic: ambil settings user → panggil API → return formatted data.
    """
    settings = prayer_settings_model.get_by_user_id(user_id)

    city = settings.get("city", "Surabaya")
    country = settings.get("country", "Indonesia")
    preference = settings.get("preference", "nu")

    result = fetch_prayer_times(city, country, method=DEFAULT_METHOD)
    if not result:
        return {"success": False, "message": "Gagal mengambil jadwal sholat dari API."}

    # Format nama sholat ke bahasa Indonesia
    timings_indo = _format_timings_indo(result["timings"])

    return {
        "success": True,
        "timings": timings_indo,
        "timings_raw": result["timings"],
        "hijri": result.get("hijri", {}),
        "gregorian": result.get("gregorian", {}),
        "preference": preference,
        "city": city,
        "country": country
    }


def get_islamic_calendar_for_user(user_id, month=None, year=None):
    """
    Ambil kalender Hijriah sebulan untuk user tertentu.
    """
    settings = prayer_settings_model.get_by_user_id(user_id)

    city = settings.get("city", "Surabaya")
    country = settings.get("country", "Indonesia")
    preference = settings.get("preference", "nu")
    hijri_adj = settings.get("hijri_adj", 0)

    # Default bulan & tahun = sekarang
    if not month or not year:
        now = datetime.now(JKT)
        month = month or now.month
        year = year or now.year

    # Inject adj berdasarkan preferensi
    adj = hijri_adj
    if preference == "nu" and adj == 0:
        adj = -1  # Default NU/Pemerintah: mundur 1 hari dari kalender global

    calendar_data = fetch_monthly_calendar(city, country, month, year, adj=adj)

    if not calendar_data:
        return {"success": False, "message": "Gagal mengambil kalender dari API."}

    # Format ringkas untuk setiap hari
    formatted_days = []
    for day in calendar_data:
        day_date = day.get("date", {})
        timings = day.get("timings", {})
        hijri = day_date.get("hijri", {})
        gregorian = day_date.get("gregorian", {})

        formatted_days.append({
            "gregorian_date": gregorian.get("date", ""),
            "gregorian_day": gregorian.get("day", ""),
            "gregorian_weekday": gregorian.get("weekday", {}).get("en", ""),
            "hijri_date": hijri.get("date", ""),
            "hijri_day": hijri.get("day", ""),
            "hijri_month": hijri.get("month", {}).get("en", ""),
            "hijri_month_ar": hijri.get("month", {}).get("ar", ""),
            "hijri_month_number": hijri.get("month", {}).get("number", 0),
            "hijri_year": hijri.get("year", ""),
            "timings": {
                "Imsak": timings.get("Imsak", "").split(" ")[0],
                "Fajr": timings.get("Fajr", "").split(" ")[0],
                "Dhuhr": timings.get("Dhuhr", "").split(" ")[0],
                "Asr": timings.get("Asr", "").split(" ")[0],
                "Maghrib": timings.get("Maghrib", "").split(" ")[0],
                "Isha": timings.get("Isha", "").split(" ")[0],
            }
        })

    return {
        "success": True,
        "month": month,
        "year": year,
        "preference": preference,
        "city": city,
        "adj": adj,
        "days": formatted_days
    }


def get_ramadan_calendar_for_user(user_id):
    """
    Ambil kalender Ramadhan dengan label 'Hari ke-X'.
    Logic:
    1. Ambil ramadan_config (tanggal 1 Ramadhan)
    2. Ambil settings user (preference Muhammadiyah/NU)
    3. Hitung status setiap hari dan label
    """
    settings = prayer_settings_model.get_by_user_id(user_id)
    preference = settings.get("preference", "nu")
    city = settings.get("city", "Surabaya")
    country = settings.get("country", "Indonesia")

    # Ambil config Ramadhan terbaru
    ramadan_cfg = ramadan_config_model.get_current()
    if not ramadan_cfg:
        return {
            "success": False,
            "message": "Konfigurasi Ramadhan belum diatur oleh admin."
        }

    # Tentukan tanggal mulai berdasarkan preferensi
    if preference == "muhammadiyah":
        start_date = ramadan_cfg.get("start_ramadan_muhammadiyah")
    else:
        start_date = ramadan_cfg.get("start_ramadan_pemerintah")

    if not start_date:
        return {
            "success": False,
            "message": f"Tanggal 1 Ramadhan ({preference}) belum diatur."
        }

    # Parse tanggal mulai
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    elif isinstance(start_date, datetime):
        start_date = start_date.date()

    total_days = ramadan_cfg.get("total_days", 30)
    end_date = start_date + timedelta(days=total_days - 1)
    today = datetime.now(JKT).date()

    # Status Ramadhan
    if today < start_date:
        ramadan_status = "upcoming"
    elif today <= end_date:
        ramadan_status = "active"
    else:
        ramadan_status = "finished"

    # Generate daftar hari Ramadhan
    ramadan_days = []
    for i in range(total_days):
        day_date = start_date + timedelta(days=i)
        day_num = i + 1

        # Status per hari
        if day_date < today:
            day_status = "passed"       # Sudah lewat
        elif day_date == today:
            day_status = "today"        # Hari ini
        else:
            day_status = "upcoming"     # Akan datang

        ramadan_days.append({
            "day_number": day_num,
            "date": day_date.isoformat(),
            "date_display": day_date.strftime("%d %b %Y"),
            "weekday": day_date.strftime("%A"),
            "status": day_status
        })

    # Ambil jadwal sholat untuk hari ini (untuk imsak & buka puasa)
    today_timings = None
    if ramadan_status == "active":
        prayer_data = fetch_prayer_times(city, country)
        if prayer_data:
            today_timings = {
                "Imsak": prayer_data["timings"].get("Imsak", "").split(" ")[0],
                "Fajr": prayer_data["timings"].get("Fajr", "").split(" ")[0],
                "Maghrib": prayer_data["timings"].get("Maghrib", "").split(" ")[0],
            }

    # Hitung hari ke-X kalau Ramadhan aktif
    current_day = None
    if ramadan_status == "active":
        current_day = (today - start_date).days + 1

    return {
        "success": True,
        "hijri_year": ramadan_cfg.get("hijri_year"),
        "preference": preference,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total_days": total_days,
        "status": ramadan_status,
        "current_day": current_day,
        "today_timings": today_timings,
        "days": ramadan_days
    }


# =============================================================
# HELPER FUNCTIONS
# =============================================================

def _format_timings_indo(timings):
    """Format nama sholat ke bahasa Indonesia dengan label yang lebih friendly."""
    mapping = {
        "Imsak": "Imsak",
        "Fajr": "Subuh",
        "Sunrise": "Terbit",
        "Dhuhr": "Dzuhur",
        "Asr": "Ashar",
        "Maghrib": "Maghrib",
        "Isha": "Isya"
    }
    result = {}
    for key, label in mapping.items():
        time_val = timings.get(key, "")
        # Aladhan kadang return format "HH:MM (WIB)" — ambil HH:MM aja
        if time_val:
            time_val = time_val.split(" ")[0]
        result[label] = time_val
    return result


def calculate_ramadan_day(check_date, start_date):
    """
    Hitung hari ke-X Ramadhan dari tanggal Masehi.
    Return: nomor hari (1-based) atau None kalau di luar Ramadhan.
    """
    if isinstance(check_date, str):
        check_date = datetime.strptime(check_date, "%Y-%m-%d").date()
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()

    diff = (check_date - start_date).days
    if 0 <= diff < 30:
        return diff + 1
    return None
