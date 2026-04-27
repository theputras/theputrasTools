# controller/KonselorController.py
# Controller untuk fitur Pencatatan Sesi Konseling
# NIM disimpan mentah, nama disensor saat display

import logging

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

        nama = str(p.get("nama", "")).strip()
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


def create_jadwal(konselor_user_id, form_data):
    nim = form_data.get("nim", "").strip()
    nama = form_data.get("nama", "").strip()
    prodi = form_data.get("prodi", "").strip()
    dosen_wali = form_data.get("dosen_wali", "").strip()
    role = form_data.get("role", "mahasiswa")
    layanan_id = form_data.get("layanan_id")
    tanggal = form_data.get("tanggal")
    jam = form_data.get("jam")

    if not nim or not layanan_id or not tanggal or not jam:
        return False, "Data tidak lengkap."

    # Validasi jam bentrok
    existing = get_jadwal_by_date(konselor_user_id, tanggal)
    for j in existing:
        if j["status"] in ("Menunggu", "Berlangsung") and j["jam"] == jam:
            return False, f"Jadwal pada jam {jam} sudah terisi."

    # Upsert ke tabel data klien untuk sinkronisasi dan dapatkan ID
    klien_data = {
        "id_civitas": nim,
        "nama": nama,
        "prodi": prodi,
        "dosen_wali": dosen_wali,
        "status_civitas": role
    }
    id_klien = klien_model.upsert(klien_data)
    if not id_klien:
        return False, "Gagal memproses data klien."

    data = {
        "konselor_user_id": konselor_user_id,
        "id_klien": id_klien,
        "layanan_id": int(layanan_id),
        "tanggal": tanggal,
        "jam": jam,
        "status": "Menunggu",
    }

    return konselor_jadwal_model.create(data)


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


def update_status_jadwal(jadwal_id, konselor_user_id, status):
    if status not in ("Menunggu", "Berlangsung", "Jeda", "Selesai", "Dibatalkan"):
        return False, "Status tidak valid."
    return konselor_jadwal_model.update_status(jadwal_id, konselor_user_id, status)


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


def get_available_slots(konselor_user_id, tanggal):
    """Return only booked slots for the given date, with censored names."""
    booked_slots_query = konselor_jadwal_model.get_by_konselor_and_date_range(
        konselor_user_id, tanggal, tanggal
    )

    slots = []
    for j in booked_slots_query:
        jam_str = str(j["jam"])
        if len(jam_str) > 5:
            jam_str = jam_str[:5]
        slots.append(
            {
                "jam": jam_str,
                "nama": censor_name(j.get("nama")),
                "status": j.get("status", "Menunggu"),
            }
        )
    return slots


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


def download_template_excel():
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
