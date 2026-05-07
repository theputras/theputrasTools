# controller/KonselorController.py
# Controller untuk fitur Pencatatan Sesi Konseling
# NIM disimpan mentah, nama disensor saat display

import logging, zipfile
from datetime import datetime

from models.konselor import (
    jenis_layanan_model,
    kategori_masalah_model,
    konselor_session_model,
    tindak_lanjut_model,
    klien_model,
)


# Global store for import progress
import_progress = {}


def get_import_progress(user_id):
    """Ambil persentase progress import untuk user tertentu."""
    return import_progress.get(str(user_id), 0)


def censor_name(nama):
    """
    Sensor nama mahasiswa untuk ditampilkan di frontend.
    Option B: karakter pertama tiap kata tetap, sisanya '*'
    Contoh: "BUDI SANTOSO" → "B*** S******"
    """
    if not nama:
        return "-"
    words = nama.strip().split()
    censored = []
    for word in words:
        if len(word) <= 1:
            censored.append(word)
        else:
            censored.append(word[0] + "*" * (len(word) - 1))
    return " ".join(censored)


def create_sesi(konselor_user_id, form_data):
    """
    Proses pembuatan sesi baru:
    1. Validasi input
    2. Simpan NIM mentah, nama (plain text), dosen wali ke database
    """
    # 1. Validasi
    nim_raw = form_data.get("nim", "").strip()
    nama = form_data.get("nama", "").strip()
    dosen_wali = form_data.get("dosen_wali", "").strip()

    # Auto-lookup dosen wali jika kosong
    if not dosen_wali and nim_raw and len(nim_raw) == 11:
        try:
            from scrapper_requests import search_mahasiswa

            df_mhs = search_mahasiswa(nim_raw, user_id=konselor_user_id)
            if not df_mhs.empty:
                mhs_data = df_mhs.iloc[0]
                mhs_dict = {str(k).lower(): v for k, v in mhs_data.items()}
                dosen_wali = mhs_dict.get("dosen wali", "")
        except Exception as e:
            logging.error(
                f"[Konselor] Auto-lookup dosen wali gagal untuk {nim_raw}: {e}"
            )

    prodi = form_data.get("prodi", "").strip()
    jenis_layanan_id = form_data.get("jenis_layanan_id")
    kategori_masalah_ids_str = form_data.get("kategori_masalah_ids", "[]")
    try:
        import json

        kategori_masalah_ids = json.loads(kategori_masalah_ids_str)
    except:
        kategori_masalah_ids = []
    topik = form_data.get("topik", "").strip()
    tanggal_sesi = form_data.get("tanggal_sesi")
    tindak_lanjut = form_data.get("tindak_lanjut", "").strip()
    catatan_kesimpulan = form_data.get("catatan_kesimpulan", "").strip()

    if not nim_raw:
        return False, "NIM wajib diisi."
    if not jenis_layanan_id:
        return False, "Jenis layanan wajib dipilih."
    if not kategori_masalah_ids:
        return False, "Kategori masalah wajib dipilih minimal 1."
    if not topik:
        return False, "Topik permasalahan wajib diisi."
    if not tanggal_sesi:
        return False, "Tanggal sesi wajib diisi."

    # 2. Upsert ke tabel data klien untuk sinkronisasi dan dapatkan ID
    klien_data = {
        "id_civitas": nim_raw,
        "nama": nama,
        "prodi": prodi,
        "dosen_wali": dosen_wali,
        "status_civitas": "Mahasiswa"
    }
    id_klien = klien_model.upsert(klien_data)
    if not id_klien:
        return False, "Gagal memproses data klien."

    # 3. Simpan ke database sesi
    data = {
        "konselor_user_id": konselor_user_id,
        "id_klien": id_klien,
        "jenis_layanan_id": int(jenis_layanan_id),
        "kategori_masalah_ids": kategori_masalah_ids,
        "topik": topik,
        "tanggal_sesi": tanggal_sesi,
        "tindak_lanjut_id": int(tindak_lanjut) if tindak_lanjut else None,
        "catatan_kesimpulan": catatan_kesimpulan if catatan_kesimpulan else None,
        "waktu_mulai": form_data.get("waktu_mulai"),
        "waktu_selesai": form_data.get("waktu_selesai"),
    }

    success, message = konselor_session_model.create_session(data)
    return success, message


def create_sesi_bulk(konselor_user_id, form_data):
    """
    Buat sesi konseling untuk MULTIPLE NIM/NIK sekaligus.
    Konsep: kasus yang sama, hari yang sama, peserta lebih dari satu.
    Setiap peserta mendapat 1 record sesi dengan data sesi yang identik
    (topik, kategori, jenis_layanan, tanggal) namun prodi & dosen_wali bisa berbeda per peserta.

    Mengembalikan (success: bool, message: str).
    """
    import json

    # --- Baca daftar peserta ---
    # Format baru: JSON array [{nim, nama, prodi, dosen_wali, role}, ...]
    participants_str = form_data.get("participants", "[]")
    try:
        participants = json.loads(participants_str)
    except Exception:
        participants = []

    # Fallback format lama: nims/names arrays (backward-compat)
    if not participants:
        nims_str = form_data.get("nims", "[]")
        names_str = form_data.get("names", "[]")
        try:
            nims = json.loads(nims_str)
            names = json.loads(names_str)
        except Exception:
            nims, names = [], []

        # Fallback ke single nim/nama
        if not nims:
            single_nim = form_data.get("nim", "").strip()
            single_nama = form_data.get("nama", "").strip()
            if single_nim:
                nims = [single_nim]
                names = [single_nama]

        while len(names) < len(nims):
            names.append("")

        # Baca prodi/dosen_wali session-level sebagai fallback
        old_prodi = form_data.get("prodi", "").strip()
        old_dosen_wali = form_data.get("dosen_wali", "").strip()

        participants = [
            {
                "nim": str(nims[i]).strip(),
                "nama": str(names[i]).strip() if i < len(names) else "",
                "prodi": old_prodi,
                "dosen_wali": old_dosen_wali,
                "role": "mahasiswa" if len(str(nims[i]).strip()) == 11 else "staff",
            }
            for i in range(len(nims))
            if str(nims[i]).strip()
        ]

    if not participants:
        return False, "NIM/NIK wajib diisi."

    # --- Validasi field sesi (sama untuk semua peserta) ---
    jenis_layanan_id = form_data.get("jenis_layanan_id")
    kategori_masalah_ids_str = form_data.get("kategori_masalah_ids", "[]")
    try:
        kategori_masalah_ids = json.loads(kategori_masalah_ids_str)
    except Exception:
        kategori_masalah_ids = []

    topik = form_data.get("topik", "").strip()
    tanggal_sesi = form_data.get("tanggal_sesi")
    tindak_lanjut = form_data.get("tindak_lanjut", "").strip()
    catatan_kesimpulan = form_data.get("catatan_kesimpulan", "").strip()

    if not jenis_layanan_id:
        return False, "Jenis layanan wajib dipilih."
    if not kategori_masalah_ids:
        return False, "Kategori masalah wajib dipilih minimal 1."
    if not topik:
        return False, "Topik permasalahan wajib diisi."
    if not tanggal_sesi:
        return False, "Tanggal sesi wajib diisi."

    # --- Simpan satu record per peserta ---
    success_count = 0
    failed_nims = []

    for p in participants:
        nim_raw = str(p.get("nim", "")).strip()
        if not nim_raw:
            continue

        nama = str(p.get("nama") or p.get("nama_raw", "")).strip()
        # Prodi & dosen_wali diambil per peserta dari participants array
        prodi = str(p.get("prodi", "")).strip()
        dosen_wali = str(p.get("dosen_wali", "")).strip()

        # Auto-lookup dosen_wali jika kosong dan peserta adalah mahasiswa (11 digit)
        if not dosen_wali and len(nim_raw) == 11:
            try:
                from scrapper_requests import search_mahasiswa

                df_mhs = search_mahasiswa(nim_raw, user_id=konselor_user_id)
                if not df_mhs.empty:
                    mhs_dict = {str(k).lower(): v for k, v in df_mhs.iloc[0].items()}
                    dosen_wali = mhs_dict.get("dosen wali", "")
            except Exception as e:
                logging.error(
                    f"[Konselor Bulk] Auto-lookup dosen wali gagal untuk {nim_raw}: {e}"
                )

        # Upsert ke tabel data klien untuk sinkronisasi dan dapatkan ID
        kd = {
            "id_civitas": nim_raw,
            "nama": nama,
            "prodi": prodi,
            "dosen_wali": dosen_wali,
            "status_civitas": p.get("role", "Mahasiswa")
        }
        id_klien = klien_model.upsert(kd)
        if not id_klien:
            failed_nims.append(nim_raw)
            continue

        data = {
            "konselor_user_id": konselor_user_id,
            "id_klien": id_klien,
            "jenis_layanan_id": int(jenis_layanan_id),
            "kategori_masalah_ids": kategori_masalah_ids,
            "topik": topik,
            "tanggal_sesi": tanggal_sesi,
            "tindak_lanjut_id": int(tindak_lanjut) if tindak_lanjut else None,
            "catatan_kesimpulan": catatan_kesimpulan if catatan_kesimpulan else None,
            "waktu_mulai": form_data.get("waktu_mulai"),
            "waktu_selesai": form_data.get("waktu_selesai"),
        }

        ok, msg = konselor_session_model.create_session(data)
        if ok:
            success_count += 1
        else:
            failed_nims.append(nim_raw)
            logging.error(f"[Konselor Bulk] Gagal simpan sesi untuk {nim_raw}: {msg}")

    # --- Hasil ---
    total = len(participants)
    if success_count == 0:
        return False, f"Gagal menyimpan semua sesi ({', '.join(failed_nims)})."
    if failed_nims:
        return True, (
            f"{success_count} dari {total} sesi berhasil disimpan. "
            f"Gagal: {', '.join(failed_nims)}."
        )
    if success_count == 1:
        return True, "Sesi konseling berhasil disimpan."
    return True, f"{success_count} sesi konseling berhasil disimpan."


def get_rekap(konselor_user_id, tahun=None):
    """
    Ambil data rekap untuk dashboard konselor.
    Return dict dengan stats + distribusi kategori untuk pie chart.
    """
    stats = konselor_session_model.get_rekap_stats(konselor_user_id, tahun=tahun)
    if not stats:
        return {
            "total_sesi": 0,
            "klien_unik": 0,
            "sesi_bulan_ini": 0,
            "kategori_distribusi": [],
            "layanan_distribusi": [],
        }
    return stats


def get_riwayat_sesi(konselor_user_id, bulan=None, tahun=None):
    """Ambil riwayat sesi konseling, sensor nama untuk frontend."""
    sessions = konselor_session_model.get_sessions_by_konselor(
        konselor_user_id, bulan=bulan, tahun=tahun
    )
    for s in sessions:
        # NIM sudah mentah di nim_id
        s["nim_asli"] = s.get("nim_id", "-")
        # Sensor nama untuk display
        s["nama_sensor"] = censor_name(s.get("nama"))
        # dosen_wali sudah ada di record dari query
    return sessions


def delete_sesi(session_id, konselor_user_id):
    """Hapus sesi konseling (ownership check)."""
    return konselor_session_model.delete_session(session_id, konselor_user_id)


def update_sesi(session_id, konselor_user_id, form_data):
    """Update sesi konseling (NIM tidak bisa diubah)."""
    prodi = form_data.get("prodi", "").strip()
    jenis_layanan_id = form_data.get("jenis_layanan_id")
    kategori_masalah_ids_str = form_data.get("kategori_masalah_ids", "[]")
    try:
        import json

        kategori_masalah_ids = json.loads(kategori_masalah_ids_str)
    except:
        kategori_masalah_ids = []
    topik = form_data.get("topik", "").strip()
    tanggal_sesi = form_data.get("tanggal_sesi")
    tindak_lanjut = form_data.get("tindak_lanjut", "").strip()
    catatan_kesimpulan = form_data.get("catatan_kesimpulan", "").strip()

    if not jenis_layanan_id:
        return False, "Jenis layanan wajib dipilih."
    if not kategori_masalah_ids:
        return False, "Kategori masalah wajib dipilih minimal 1."
    if not topik:
        return False, "Topik permasalahan wajib diisi."
    if not tanggal_sesi:
        return False, "Tanggal sesi wajib diisi."

    data = {
        "jenis_layanan_id": int(jenis_layanan_id),
        "kategori_masalah_ids": kategori_masalah_ids,
        "topik": topik,
        "tanggal_sesi": tanggal_sesi,
        "tindak_lanjut_id": int(tindak_lanjut) if tindak_lanjut else None,
        "catatan_kesimpulan": catatan_kesimpulan if catatan_kesimpulan else None,
    }

    return konselor_session_model.update_session(session_id, konselor_user_id, data)


# === Penjadwalan ===
from models.konselor import konselor_jadwal_model


def create_jadwal_bulk(konselor_user_id, form_data):
    """
    Buat jadwal konseling untuk MULTIPLE NIM/NIK sekaligus.
    Satu record per peserta.
    """
    import json
    participants_str = form_data.get("participants", "[]")
    try:
        participants = json.loads(participants_str)
    except Exception:
        participants = []

    # Fallback ke single nim/nama jika participants kosong
    if not participants:
        single_nim = form_data.get("nim", "").strip()
        single_nama = form_data.get("nama", "").strip()
        if single_nim:
            participants = [{
                "nim": single_nim,
                "nama": single_nama,
                "prodi": form_data.get("prodi", ""),
                "dosen_wali": form_data.get("dosen_wali", ""),
                "role": form_data.get("role", "mahasiswa")
            }]

    if not participants:
        return False, "Data peserta tidak lengkap."

    layanan_id = form_data.get("layanan_id")
    tanggal = form_data.get("tanggal")
    jam = form_data.get("jam")

    if not layanan_id or not tanggal or not jam:
        return False, "Data layanan, tanggal, atau jam tidak lengkap."

    # Validasi jam bentrok: hanya block jika ada sesi LAIN (layanan_id berbeda) di jam yang sama.
    # Sesi kelompok (layanan_id sama) boleh punya beberapa peserta di jam yang sama.
    existing = get_jadwal_by_date(konselor_user_id, tanggal)
    for j in existing:
        if j["status"] in ("Menunggu", "Berlangsung") and j["jam"] == jam:
            if str(j.get("layanan_id")) != str(layanan_id):
                return False, f"Jadwal pada jam {jam} sudah terisi dengan layanan lain."

    success_count = 0
    failed_nims = []

    for p in participants:
        nim_raw = str(p.get("nim", "")).strip()
        if not nim_raw: continue

        nama = str(p.get("nama") or p.get("nama_raw", "")).strip()
        prodi = str(p.get("prodi", "")).strip()
        dosen_wali = str(p.get("dosen_wali", "")).strip()
        role = p.get("role", "mahasiswa")

        # Auto-lookup dosen wali jika kosong
        if not dosen_wali and len(nim_raw) == 11:
            try:
                from scrapper_requests import search_mahasiswa
                df_mhs = search_mahasiswa(nim_raw, user_id=konselor_user_id)
                if not df_mhs.empty:
                    mhs_dict = {str(k).lower(): v for k, v in df_mhs.iloc[0].items()}
                    dosen_wali = mhs_dict.get("dosen wali", "")
            except Exception as e:
                logging.error(f"[Konselor Jadwal Bulk] Auto-lookup gagal untuk {nim_raw}: {e}")

        # Upsert klien
        kd = {
            "id_civitas": nim_raw,
            "nama": nama,
            "prodi": prodi,
            "dosen_wali": dosen_wali,
            "status_civitas": role
        }
        id_klien = klien_model.upsert(kd)
        if not id_klien:
            failed_nims.append(nim_raw)
            continue

        data = {
            "konselor_user_id": konselor_user_id,
            "id_klien": id_klien,
            "layanan_id": int(layanan_id),
            "tanggal": tanggal,
            "jam": jam,
            "status": "Menunggu",
        }

        ok, msg = konselor_jadwal_model.create(data)
        if ok:
            success_count += 1
        else:
            failed_nims.append(nim_raw)

    total = len(participants)
    if success_count == 0:
        return False, f"Gagal menyimpan semua jadwal ({', '.join(failed_nims)})."
    if failed_nims:
        return True, f"{success_count} dari {total} jadwal berhasil disimpan. Gagal: {', '.join(failed_nims)}."
    
    if success_count == 1:
        return True, "Jadwal berhasil disimpan."
    return True, f"{success_count} jadwal berhasil disimpan."


def get_jadwal_by_date(konselor_user_id, start_date, end_date=None):
    jadwals = konselor_jadwal_model.get_by_konselor_and_date_range(
        konselor_user_id, start_date, end_date
    )
    # Format jam for display and censor nama for frontend
    for j in jadwals:
        # Check if jam has seconds like "09:00:00", truncate to "09:00"
        jam_str = str(j["jam"])
        if len(jam_str) > 5:
            j["jam"] = jam_str[:5]
        j["tanggal"] = str(j["tanggal"])
        # Sensor nama untuk frontend, DB tetap simpan asli
        j["nama_sensor"] = censor_name(j.get("nama"))
    return jadwals


def group_jadwal_entries(jadwals):
    """Group jadwal entries with same tanggal+jam+layanan_id into a single item."""
    grouped = {}
    for j in jadwals:
        # Normalize tanggal and jam for grouping key
        tgl = str(j.get("tanggal"))
        jam_str = str(j.get("jam", ""))
        if len(jam_str) > 5: jam_str = jam_str[:5]
        
        key = (tgl, jam_str, j.get("layanan_id"))
        if key not in grouped:
            j["jam"] = jam_str
            j["tanggal"] = tgl
            grouped[key] = {
                **j,
                "ids": [j["id"]],
                "participants": [{
                    "id": j["id"],
                    "nim": j.get("nim"),
                    "nama": j.get("nama"),
                    "nama_sensor": censor_name(j.get("nama")),
                    "prodi": j.get("prodi"),
                    "status": j.get("status"),
                }],
                "is_group": False,
            }
        else:
            grouped[key]["ids"].append(j["id"])
            grouped[key]["participants"].append({
                "id": j["id"],
                "nim": j.get("nim"),
                "nama": j.get("nama"),
                "nama_sensor": censor_name(j.get("nama")),
                "prodi": j.get("prodi"),
                "status": j.get("status"),
            })

    result = []
    for g_item in grouped.values():
        pcount = len(g_item["participants"])
        if pcount > 1:
            g_item["is_group"] = True
            names = [p["nama_sensor"] for p in g_item["participants"]]
            g_item["nama_sensor"] = ", ".join(names[:2]) + (f", +{pcount-2}" if pcount > 2 else "")
        else:
            g_item["nama_sensor"] = censor_name(g_item.get("nama"))
        result.append(g_item)
    return result


def reschedule_jadwal(jadwal_id, konselor_user_id, form_data):
    tanggal = form_data.get("tanggalBaru")
    jam = form_data.get("jamBaru")
    if not tanggal or not jam:
        return False, "Tanggal dan jam baru wajib diisi."

    # Validasi jam bentrok (kecuali dengan dirinya sendiri)
    existing = get_jadwal_by_date(konselor_user_id, tanggal)
    for j in existing:
        if (
            str(j["id"]) != str(jadwal_id)
            and j["status"] in ("Menunggu", "Berlangsung")
            and j["jam"] == jam
        ):
            return False, f"Jadwal pada jam {jam} sudah terisi."

    return konselor_jadwal_model.update_waktu(jadwal_id, konselor_user_id, tanggal, jam)


def update_status_jadwal(jadwal_id, konselor_user_id, status, token=None):
    if status not in ("Menunggu", "Berlangsung", "Jeda", "Selesai", "Dibatalkan"):
        return False, "Status tidak valid."
    return konselor_jadwal_model.update_status(jadwal_id, konselor_user_id, status, token)

def get_jadwal_detail(jadwal_id):
    jadwal = konselor_jadwal_model.get_by_id(jadwal_id)
    if jadwal:
        jam_str = str(jadwal["jam"])
        if len(jam_str) > 5:
            jadwal["jam"] = jam_str[:5]
        jadwal["tanggal"] = str(jadwal["tanggal"])
        # Sensor nama untuk frontend display
        jadwal["nama_sensor"] = censor_name(jadwal.get("nama"))
    return jadwal

def get_grouped_jadwal_detail(jadwal_id, konselor_user_id):
    jadwals = konselor_jadwal_model.get_grouped_jadwal(jadwal_id, konselor_user_id)
    for jadwal in jadwals:
        jam_str = str(jadwal["jam"])
        if len(jam_str) > 5:
            jadwal["jam"] = jam_str[:5]
        jadwal["tanggal"] = str(jadwal["tanggal"])
        jadwal["nama_sensor"] = censor_name(jadwal.get("nama"))
    return jadwals

def takeover_live_session_jadwal(jadwal_id, konselor_user_id):
    return konselor_jadwal_model.takeover_live_session(jadwal_id, konselor_user_id)


def get_available_slots(konselor_user_id, tanggal):
    """Return only booked slots for the given date, grouped by time/service."""
    booked_slots_query = konselor_jadwal_model.get_by_konselor_and_date_range(
        konselor_user_id, tanggal, tanggal
    )
    return group_jadwal_entries(booked_slots_query)


# === CRUD Master Data ===


def get_all_kategori():
    return kategori_masalah_model.get_all()


def create_kategori(nama):
    return kategori_masalah_model.create(nama)


def update_kategori(kategori_id, nama):
    return kategori_masalah_model.update(kategori_id, nama)


def delete_kategori(kategori_id):
    return kategori_masalah_model.delete(kategori_id)


def get_all_layanan():
    return jenis_layanan_model.get_all()


def create_layanan(nama):
    return jenis_layanan_model.create(nama)


def update_layanan(layanan_id, nama):
    return jenis_layanan_model.update(layanan_id, nama)


def delete_layanan(layanan_id):
    return jenis_layanan_model.delete(layanan_id)


def get_all_tindak_lanjut():
    return tindak_lanjut_model.get_all()


def create_tindak_lanjut(nama):
    return tindak_lanjut_model.create(nama)


def update_tindak_lanjut(tl_id, nama):
    return tindak_lanjut_model.update(tl_id, nama)


def delete_tindak_lanjut(tl_id):
    return tindak_lanjut_model.delete(tl_id)


from io import BytesIO

import pandas as pd
from flask import jsonify, send_file

from scrapper_requests import search_mahasiswa


def download_template_excel(mode="month"):
    from datetime import datetime

    df = pd.DataFrame(
        columns=[
            "NIM/NIK/Kode",
            "Tanggal Sesi (YYYY-MM-DD)",
            "Topik Permasalahan",
            "Jenis Layanan",
            "Kategori Masalah (Pisahkan dengan koma)",
            "Tindak Lanjut",
            "Nama (Opsional)",
        ]
    )

    if mode == "year":
        sheet_name = datetime.now().strftime("%Y")
    else:
        sheet_name = datetime.now().strftime("%B %Y")

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)

    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name="Template_Import_Sesi_Konseling.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def import_sesi_excel(request, user_id):
    if "file" not in request.files:
        return jsonify({"success": False, "message": "Tidak ada file yang diunggah"})

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"success": False, "message": "File tidak valid"})

    try:
        # Baca semua sheet sekaligus
        all_sheets = pd.read_excel(file, sheet_name=None)
        df_list = []
        
        # Iterasi tiap sheet
        for sheet_name, sheet_df in all_sheets.items():
            # Cek apakah sheet ini punya kolom minimal (NIM/NIK/Kode)
            cols = [str(c).strip().lower() for c in sheet_df.columns]
            if "nim/nik/kode" in cols or "nim" in cols:
                sheet_df = sheet_df.fillna("")
                df_list.append(sheet_df)
        
        if not df_list:
            return jsonify({"success": False, "message": "Tidak ada data valid ditemukan di sheet manapun (Pastikan header sesuai template)"})
        
        df = pd.concat(df_list, ignore_index=True)

        success_count = 0
        error_count = 0
        skipped_count = 0

        from app import majorID
        from models.konselor import konselor_session_model

        layanan_map = {v["nama"].lower().strip(): v["id"] for v in get_all_layanan()}
        kategori_map = {
            v["nama"].lower().replace(" ", ""): v["id"] for v in get_all_kategori()
        }
        tl_map = {v["nama"].lower().strip(): v["id"] for v in get_all_tindak_lanjut()}

        # Ambil sesi yang sudah ada untuk pengecekan duplikat
        existing_sessions = konselor_session_model.get_sessions_by_konselor(user_id)
        existing_keys = set()
        for s in existing_sessions:
            e_nim = str(s.get("nim_id", "")).strip()
            e_tgl_val = s.get("tanggal_sesi")
            if hasattr(e_tgl_val, "strftime"):
                e_tgl = e_tgl_val.strftime("%Y-%m-%d")
            else:
                e_tgl = str(e_tgl_val).strip()
                if " " in e_tgl:
                    e_tgl = e_tgl.split(" ")[0]
            e_topik = str(s.get("topik", "")).strip().lower()
            existing_keys.add((e_nim, e_tgl, e_topik))

        total_rows = len(df)
        import_progress[str(user_id)] = 0

        for index, row in df.iterrows():
            # Helper untuk ambil value kolom secara case-insensitive
            def get_col(names):
                for name in names:
                    for c in row.index:
                        if str(c).strip().lower() == name.lower():
                            return str(row[c]).strip()
                return ""

            # Update progress
            if total_rows > 0:
                import_progress[str(user_id)] = int(((index + 1) / total_rows) * 100)
            
            nim = get_col(["NIM/NIK/Kode", "NIM", "NIK"])
            if nim.startswith("'"):
                nim = nim[1:]
            if nim.endswith(".0"):
                nim = nim[:-2]
            
            # Normalisasi kode khusus (misal '2' dari CSV jadi '002')
            if nim.isdigit() and len(nim) < 3 and int(nim) in [1, 2]:
                nim = nim.zfill(3)

            tanggal_raw = get_col(["Tanggal Sesi (YYYY-MM-DD)", "Tanggal Sesi", "Tanggal"])
            if " " in tanggal_raw:
                tanggal_raw = tanggal_raw.split(" ")[0]
            try:
                parsed_date = pd.to_datetime(tanggal_raw, dayfirst=True)
                tanggal = parsed_date.strftime("%Y-%m-%d")
            except Exception:
                tanggal = tanggal_raw
            
            topik = get_col(["Topik Permasalahan", "Topik"])

            if (nim, tanggal, topik.lower()) in existing_keys:
                skipped_count += 1
                logging.info(f"[Konselor Import] Skip duplikat NIM {nim} pada {tanggal}")
                continue

            jenis_layanan_val = get_col(["Jenis Layanan", "Jenis Layanan ID", "Layanan"])
            jenis_layanan_id = None
            if jenis_layanan_val:
                if jenis_layanan_val.isdigit():
                    jenis_layanan_id = int(jenis_layanan_val)
                elif jenis_layanan_val.endswith(".0") and jenis_layanan_val[:-2].isdigit():
                    jenis_layanan_id = int(jenis_layanan_val[:-2])
                else:
                    jl_lower = jenis_layanan_val.lower()
                    if jl_lower in layanan_map:
                        jenis_layanan_id = layanan_map[jl_lower]
                    else:
                        create_layanan(jenis_layanan_val)
                        layanan_map = {v["nama"].lower().strip(): v["id"] for v in get_all_layanan()}
                        jenis_layanan_id = layanan_map.get(jl_lower)

            tl_val = get_col(["Tindak Lanjut", "Tindak Lanjut ID", "Status"])
            tindak_lanjut_id = None
            if tl_val:
                if tl_val.isdigit():
                    tindak_lanjut_id = int(tl_val)
                elif tl_val.endswith(".0") and tl_val[:-2].isdigit():
                    tindak_lanjut_id = int(tl_val[:-2])
                else:
                    tl_lower = tl_val.lower()
                    if tl_lower in tl_map:
                        tindak_lanjut_id = tl_map[tl_lower]
                    else:
                        create_tindak_lanjut(tl_val)
                        tl_map = {v["nama"].lower().strip(): v["id"] for v in get_all_tindak_lanjut()}
                        tindak_lanjut_id = tl_map.get(tl_lower)
            kategori_raw = get_col(["Kategori Masalah (Pisahkan dengan koma)", "Kategori Masalah", "Kategori"])
            prodi = get_col(["Prodi (Opsional)", "Prodi", "Bagian"])
            nama = get_col(["Nama (Opsional)", "Nama"])
            dosen_wali = get_col(["Dosen Wali (Opsional)", "Dosen Wali", "Dosen"])

            if (
                not nim
                or not tanggal
                or not topik
                or not jenis_layanan_id
                or not kategori_raw
            ):
                error_count += 1
                logging.error(f"[Konselor Import] Data tidak lengkap untuk NIM {nim}")
                continue

            kategori_ids = []
            for k in kategori_raw.split(","):
                k = k.strip()
                if not k:
                    continue
                if k.isdigit():
                    kategori_ids.append(int(k))
                elif k.endswith(".0") and k[:-2].isdigit():
                    kategori_ids.append(int(k[:-2]))
                else:
                    k_norm = k.lower().replace(" ", "")
                    if k_norm in kategori_map:
                        kategori_ids.append(kategori_map[k_norm])
                    else:
                        create_kategori(k)
                        kategori_map = {v["nama"].lower().replace(" ", ""): v["id"] for v in get_all_kategori()}
                        if k_norm in kategori_map:
                            kategori_ids.append(kategori_map[k_norm])

            if not kategori_ids:
                error_count += 1
                logging.error(
                    f"[Konselor Import] Kategori tidak valid untuk NIM {nim}: {kategori_raw}"
                )
                continue

            if nim in ["001", "002"]:
                # Kode khusus: 001 (Manual), 002 (Dummy)
                if nim == "002" and not nama:
                    nama = "Mahasiswa Dummy"
                    prodi = "S1 Sistem Informasi"
                    dosen_wali = "Dosen Dummy"
            elif not nama or not dosen_wali or not prodi:
                try:
                    df_mhs = search_mahasiswa(nim, user_id=user_id)
                    if not df_mhs.empty:
                        mhs_data = df_mhs.iloc[0]
                        mhs_dict = {str(k).lower(): v for k, v in mhs_data.items()}
                        if not nama:
                            nama = mhs_dict.get("nama", "")
                        if not dosen_wali:
                            dosen_wali = mhs_dict.get("dosen wali", "")
                        if not prodi:
                            if nim and len(nim) >= 7:
                                prodi = majorID.get(nim[2:7], "")
                except Exception as e:
                    logging.error(f"[Konselor] Auto-fill gagal untuk NIM {nim}: {e}")

            # Upsert ke tabel data klien untuk sinkronisasi dan dapatkan ID
            kd = {
                "id_civitas": nim,
                "nama": nama,
                "prodi": prodi,
                "dosen_wali": dosen_wali,
                "status_civitas": "Mahasiswa"
            }
            id_klien = klien_model.upsert(kd)
            if not id_klien:
                error_count += 1
                logging.error(f"[Konselor Import] Gagal upsert klien {nim}")
                continue

            data = {
                "konselor_user_id": user_id,
                "id_klien": id_klien,
                "jenis_layanan_id": jenis_layanan_id,
                "kategori_masalah_ids": kategori_ids,
                "topik": topik,
                "tanggal_sesi": tanggal,
                "tindak_lanjut_id": tindak_lanjut_id,
            }

            success, msg = konselor_session_model.create_session(data)
            if success:
                success_count += 1
                existing_keys.add((nim, tanggal, topik.lower()))
            else:
                error_count += 1
                logging.error(f"[Konselor Import] Gagal simpan sesi {nim}: {msg}")

        msg_parts = [f"Import selesai. {success_count} berhasil."]
        if skipped_count > 0:
            msg_parts.append(f"{skipped_count} dilewati (duplikat).")
        if error_count > 0:
            msg_parts.append(f"{error_count} gagal/tidak lengkap.")

        # Clean up progress after finish
        if str(user_id) in import_progress:
            del import_progress[str(user_id)]

        return jsonify(
            {
                "success": True,
                "message": " ".join(msg_parts),
            }
        )

    except Exception as e:
        logging.error(f"[Konselor Import] Error: {e}")
        return jsonify({"success": False, "message": f"Gagal membaca file: {str(e)}"})

def get_all_klien_data():
    """Ambil semua data klien untuk dashboard."""
    return klien_model.get_all()


def update_klien_metadata(id_civitas, form_data):
    """Update metadata mbti/abk dari klien."""
    metadata = {}
    if "mbti" in form_data:
        metadata["mbti"] = form_data.get("mbti")
    if "status_abk" in form_data:
        metadata["status_abk"] = form_data.get("status_abk")
    
    if not metadata:
        return False, "Tidak ada data untuk diupdate"
    
    nama = form_data.get("nama")
    success = klien_model.update_metadata(id_civitas, nama, metadata)
    return success, "Data berhasil diperbarui" if success else "Gagal memperbarui data"


def get_available_periods(user_id):
    """Return distinct year-month pairs (with counts) and dosen_wali list from sessions."""
    from connection import get_connection
    conn = get_connection()
    if not conn:
        return {"success": False, "months": [], "years": [], "dosen_wali_list": []}

    cursor = conn.cursor(dictionary=True)
    try:
        # 1. Distinct months with count
        cursor.execute("""
            SELECT EXTRACT(YEAR FROM s.tanggal_sesi)::int as tahun,
                   EXTRACT(MONTH FROM s.tanggal_sesi)::int as bulan,
                   COUNT(*) as jumlah
            FROM konselor_sessions s
            WHERE s.konselor_user_id = %s
            GROUP BY tahun, bulan
            ORDER BY tahun DESC, bulan ASC
        """, (user_id,))
        months = cursor.fetchall()

        # 2. Distinct years with count
        cursor.execute("""
            SELECT EXTRACT(YEAR FROM s.tanggal_sesi)::int as tahun,
                   COUNT(*) as jumlah
            FROM konselor_sessions s
            WHERE s.konselor_user_id = %s
            GROUP BY tahun
            ORDER BY tahun DESC
        """, (user_id,))
        years = cursor.fetchall()

        # 3. Distinct dosen_wali with count of sessions
        cursor.execute("""
            SELECT dk.dosen_wali, COUNT(*) as jumlah
            FROM konselor_sessions s
            JOIN konselor_data_klien dk ON s.id_klien = dk.id
            WHERE s.konselor_user_id = %s
              AND dk.dosen_wali IS NOT NULL
              AND dk.dosen_wali != ''
            GROUP BY dk.dosen_wali
            ORDER BY dk.dosen_wali ASC
        """, (user_id,))
        dosen_list = cursor.fetchall()

        return {
            "success": True,
            "months": months,
            "years": years,
            "dosen_wali_list": dosen_list,
        }
    except Exception as e:
        logging.error(f"[Konselor] Error get_available_periods: {e}")
        return {"success": False, "months": [], "years": [], "dosen_wali_list": []}
    finally:
        cursor.close()
        conn.close()


import io
import base64
from flask import send_file, jsonify
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib.enums import TA_CENTER

def _generate_konselor_pdf_buffer(user_id, mode, bulan, tahun, dosen_wali, filter_waktu, chart_data):
    nama_bulan_list = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", 
                       "Juli", "Agustus", "September", "Oktober", "November", "Desember"]

    # Get data
    from connection import get_connection
    conn = get_connection()
    if not conn:
        raise Exception("Database connection failed")

    cursor = conn.cursor(dictionary=True)
    
    # 1. Base Query for Sessions
    query = """
        SELECT dk.id_civitas as nim, dk.prodi, jl.nama as jenis_layanan,
               s.topik as topik_permasalahan, s.tanggal_sesi, tl.nama as tindak_lanjut, dk.dosen_wali
        FROM konselor_sessions s
        JOIN konselor_data_klien dk ON s.id_klien = dk.id
        LEFT JOIN konselor_jenis_layanan jl ON s.jenis_layanan_id = jl.id
        LEFT JOIN konselor_tindak_lanjut tl ON s.tindak_lanjut_id = tl.id
        WHERE s.konselor_user_id = %s
    """
    params = [user_id]

    if mode == "bulan" and bulan and tahun:
        query += " AND EXTRACT(MONTH FROM s.tanggal_sesi) = %s AND EXTRACT(YEAR FROM s.tanggal_sesi) = %s"
        params.extend([bulan, tahun])
    elif mode == "tahun" and tahun:
        query += " AND EXTRACT(YEAR FROM s.tanggal_sesi) = %s"
        params.extend([tahun])
    elif mode == "dosen":
        if dosen_wali:
            query += " AND dk.dosen_wali ILIKE %s"
            params.append(f"%{dosen_wali}%")
        
        if filter_waktu == "bulan" and bulan and tahun:
            query += " AND EXTRACT(MONTH FROM s.tanggal_sesi) = %s AND EXTRACT(YEAR FROM s.tanggal_sesi) = %s"
            params.extend([bulan, tahun])
        elif filter_waktu == "tahun" and tahun:
            query += " AND EXTRACT(YEAR FROM s.tanggal_sesi) = %s"
            params.extend([tahun])
            
    query += " ORDER BY s.tanggal_sesi ASC"
    
    cursor.execute(query, tuple(params))
    sessions = cursor.fetchall()
    
    # Rekapitulasi Data
    rekap_layanan = {}
    total_klien_set = set()
    klien_per_layanan = {}
    
    for s in sessions:
        layanan = s['jenis_layanan'] or '-'
        nim = s['nim']
        
        if layanan not in rekap_layanan:
            rekap_layanan[layanan] = 0
            klien_per_layanan[layanan] = set()
            
        rekap_layanan[layanan] += 1
        klien_per_layanan[layanan].add(nim)
        total_klien_set.add(nim)
        
    # Ambil nama konselor
    cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
    konselor_info = cursor.fetchone()
    nama_konselor = konselor_info['username'] if konselor_info else "Konselor"
    
    cursor.close()
    conn.close()

    # Generate PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], alignment=TA_CENTER, fontSize=14)
    elements.append(Paragraph("<b>REKAP LAPORAN BIMBINGAN DAN KONSELING</b>", title_style))
    elements.append(Spacer(1, 12))
    
    # Subheader info
    info_style = ParagraphStyle('InfoStyle', parent=styles['Normal'], fontSize=11, spaceAfter=2)
    
    # Menentukan teks keterangan waktu
    teks_waktu = ""
    if mode == "bulan" or (mode == "dosen" and filter_waktu == "bulan"):
        nama_bulan = nama_bulan_list[int(bulan)] if bulan and str(bulan).isdigit() and int(bulan) in range(1, 13) else ""
        teks_waktu = f"Bulan: {nama_bulan} {tahun}"
    else:
        teks_waktu = f"Keseluruhan Tahun {tahun}"
        
    elements.append(Paragraph(f"<b>{teks_waktu}</b>", info_style))
    
    if mode == "dosen" and dosen_wali:
        elements.append(Paragraph(f"Nama Konselor: <b>{nama_konselor}</b>", info_style))
        elements.append(Paragraph(f"Dosen Wali: <b>{dosen_wali}</b>", info_style))
    else:
        elements.append(Paragraph(f"Nama Konselor: <b>{nama_konselor}</b>", info_style))
        
    elements.append(Paragraph("Unit/Lembaga: <b>Universitas Dinamika Surabaya</b>", info_style))
    elements.append(Spacer(1, 12))
    
    # Table 1: Data Layanan
    elements.append(Paragraph("<b>Data Layanan Konseling</b>", styles['Heading3']))
    elements.append(Spacer(1, 6))
    
    table_data = [['No', 'NIM', 'Prodi', 'Jenis Layanan', 'Topik Permasalahan', 'Tanggal Sesi', 'Tindak Lanjut']]
    
    for idx, s in enumerate(sessions, 1):
        tgl = s['tanggal_sesi'].strftime("%d/%m/%y") if hasattr(s['tanggal_sesi'], 'strftime') else s['tanggal_sesi']
        table_data.append([
            str(idx) + ".",
            s['nim'],
            Paragraph(s['prodi'] or '-', styles['Normal']),
            Paragraph(s['jenis_layanan'] or '-', styles['Normal']),
            Paragraph(s['topik_permasalahan'] or '-', styles['Normal']),
            tgl,
            Paragraph(s['tindak_lanjut'] or '-', styles['Normal'])
        ])
        
    col_widths = [30, 80, 150, 100, 200, 80, 140]
    
    t1 = Table(table_data, colWidths=col_widths, repeatRows=1)
    t1.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e2e8f0')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.black),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('ALIGN', (0,0), (0,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 10),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('TOPPADDING', (0,0), (-1,0), 8),
        ('BACKGROUND', (0,1), (-1,-1), colors.white),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    
    elements.append(t1)
    elements.append(Spacer(1, 20))
    
    # Table 2: Rekapitulasi
    elements.append(Paragraph("<b>Rekapitulasi Jumlah Layanan</b>", styles['Heading3']))
    elements.append(Spacer(1, 6))
    
    rekap_data = [['Jenis Layanan', 'Jumlah Sesi', 'Jumlah Klien']]
    total_sesi = len(sessions)
    total_klien = len(total_klien_set)
    
    for layanan, count in rekap_layanan.items():
        klien_count = len(klien_per_layanan[layanan])
        rekap_data.append([layanan, str(count), str(klien_count)])
        
    rekap_data.append(['Total', str(total_sesi), str(total_klien)])
    
    t2 = Table(rekap_data, colWidths=[200, 100, 100], repeatRows=1)
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e2e8f0')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.black),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('ALIGN', (1,0), (2,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    
    elements.append(t2)
    
    # Charts
    chart_kategori = chart_data.get("chart_kategori")
    chart_layanan = chart_data.get("chart_layanan")
    chart_prodi = chart_data.get("chart_prodi")
    
    import tempfile
    import os
    
    try:
        def add_chart(b64str):
            if b64str and ',' in b64str:
                try:
                    img_data = base64.b64decode(b64str.split(',')[1])
                    fd, temp_path = tempfile.mkstemp(suffix=".png")
                    with os.fdopen(fd, 'wb') as f:
                        f.write(img_data)
                    img = RLImage(temp_path, width=3.5*inch, height=2.5*inch)
                    return img
                except Exception as e:
                    logging.error(f"Error decoding chart: {e}")
            return None

        img1 = add_chart(chart_kategori)
        img2 = add_chart(chart_layanan)
        img3 = add_chart(chart_prodi)
        
        charts_to_display = []
        if img1: charts_to_display.append(img1)
        if img2: charts_to_display.append(img2)
        if img3 and mode != "dosen": charts_to_display.append(img3) # Prodi hidden for Dosen Wali
        
        if charts_to_display:
            elements.append(Spacer(1, 20))
            elements.append(Paragraph("<b>Grafik Layanan Konseling</b>", styles['Heading3']))
            elements.append(Spacer(1, 10))
            
            rows = []
            for i in range(0, len(charts_to_display), 2):
                chunk = charts_to_display[i:i+2]
                if len(chunk) < 2:
                    chunk.append('') 
                rows.append(chunk)
                
            chart_table = Table(rows, colWidths=[4*inch, 4*inch])
            chart_table.setStyle(TableStyle([
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ]))
            elements.append(chart_table)
            
    except Exception as e:
        logging.error(f"[Konselor PDF] Error appending charts: {e}")
        
    doc.build(elements)
    buffer.seek(0)
    
    bulan_str = ""
    try:
        if bulan and int(bulan) in range(1, 13):
            bulan_str = nama_bulan_list[int(bulan)]
    except:
        pass

    filename = f"Rekap_Laporan_Konseling.pdf"
    if mode == "bulan":
        filename = f"Rekap_Bulanan_{bulan_str}_{tahun}.pdf"
    elif mode == "tahun":
        filename = f"Rekap_Tahunan_{tahun}.pdf"
    elif mode == "dosen":
        if filter_waktu == "tahun":
            filename = f"Rekap_Tahunan_Dosen_Wali_{dosen_wali}_{tahun}.pdf"
        else:
            filename = f"Rekap_Bulanan_Dosen_Wali_{dosen_wali}_{bulan_str}_{tahun}.pdf"

    return buffer, filename

def download_laporan_pdf(user_id, request):
    mode = request.values.get("mode", "bulan")
    bulan = request.values.get("bulan", "")
    tahun = request.values.get("tahun", "")
    dosen_wali = request.values.get("dosen_wali", "")
    filter_waktu = request.values.get("filter_waktu", "bulan")
    
    chart_data = {
        "chart_kategori": request.values.get("chart_kategori"),
        "chart_layanan": request.values.get("chart_layanan"),
        "chart_prodi": request.values.get("chart_prodi")
    }

    try:
        buffer, filename = _generate_konselor_pdf_buffer(
            user_id, mode, bulan, tahun, dosen_wali, filter_waktu, chart_data
        )
        return send_file(
            buffer,
            as_attachment=True,
            download_name=filename,
            mimetype="application/pdf"
        )
    except Exception as e:
        logging.error(f"[Konselor PDF] Error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

def download_laporan_zip(user_id, request):
    bulan = request.values.get("bulan", "")
    tahun = request.values.get("tahun", "")
    filter_waktu = request.values.get("filter_waktu", "bulan")
    
    chart_data = {
        "chart_kategori": request.values.get("chart_kategori"),
        "chart_layanan": request.values.get("chart_layanan"),
        "chart_prodi": request.values.get("chart_prodi")
    }

    from connection import get_connection
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    query = """
        SELECT DISTINCT dk.dosen_wali
        FROM konselor_sessions s
        JOIN konselor_data_klien dk ON s.id_klien = dk.id
        WHERE s.konselor_user_id = %s
          AND dk.dosen_wali IS NOT NULL AND dk.dosen_wali != ''
    """
    params = [user_id]
    
    if filter_waktu == "bulan" and bulan and tahun:
        query += " AND EXTRACT(MONTH FROM s.tanggal_sesi) = %s AND EXTRACT(YEAR FROM s.tanggal_sesi) = %s"
        params.extend([bulan, tahun])
    elif filter_waktu == "tahun" and tahun:
        query += " AND EXTRACT(YEAR FROM s.tanggal_sesi) = %s"
        params.extend([tahun])
        
    cursor.execute(query, tuple(params))
    dosen_list = [row['dosen_wali'] for row in cursor.fetchall()]
    cursor.close()
    conn.close()

    if not dosen_list:
        return jsonify({"success": False, "message": "Tidak ada data dosen wali untuk periode ini"}), 404

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for dw in dosen_list:
            try:
                pdf_buffer, filename = _generate_konselor_pdf_buffer(
                    user_id, "dosen", bulan, tahun, dw, filter_waktu, chart_data
                )
                zf.writestr(filename, pdf_buffer.getvalue())
            except Exception as e:
                logging.error(f"Error generating PDF for {dw}: {e}")
            
    zip_buffer.seek(0)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nama_bulan_list = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", 
                       "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    bulan_str = nama_bulan_list[int(bulan)] if bulan and str(bulan).isdigit() and int(bulan) in range(1, 13) else ""
    
    if filter_waktu == "bulan":
        zip_name = f"Laporan_All_Dosen_Wali_{bulan_str}_{tahun}_{timestamp}.zip"
    else:
        zip_name = f"Laporan_All_Dosen_Wali_Tahunan_{tahun}_{timestamp}.zip"
    
    return send_file(
        zip_buffer,
        as_attachment=True,
        download_name=zip_name,
        mimetype="application/zip"
    )
