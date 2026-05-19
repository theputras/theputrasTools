# middleware/konselor_guard.py
# Decorator untuk mengecek hak akses dinamis di Konselor App
# Cek user terdaftar di konselor_users, lalu cek permission berdasarkan role konselor

import logging
from functools import wraps
from flask import g, jsonify, redirect, url_for, request


def konselor_permission(page_identifier, action="can_view"):
    """
    Decorator untuk mengecek hak akses Konselor App secara dinamis.
    Harus diletakkan DI BAWAH @login_required.

    Flow:
    1. Cek apakah user terdaftar di tabel `konselor_users` (berdasarkan source_user_id)
    2. Ambil role_id khusus konselor dari `konselor_users`
    3. Cek permission role tersebut di `konselor_role_permissions`

    Args:
        page_identifier: ID halaman (e.g., 'dashboard', 'rekap_sesi', 'jadwal_konsul')
        action: Jenis aksi yang dicek (e.g., 'can_view', 'can_create', 'can_update', 'can_delete')

    Menyimpan ke g:
        g.konselor_user: dict data user dari konselor_users
        g.konselor_perms: dict permission halaman ini {can_view, can_create, ..., data_scope}
        g.konselor_data_scope: string scope data ('ALL', 'OWN', 'NONE')
        g.konselor_all_perms: dict semua permission user untuk semua halaman
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(*args, **kwargs):
            if not hasattr(g, 'user'):
                return _deny(view_func, "Unauthorized")

            main_user_id = g.user.get('sub')

            from models.konselor import konselor_user_model, konselor_role_permission_model

            # Step 1: Cek apakah user terdaftar di konselor_users
            konselor_user = konselor_user_model.get_by_source_user_id(main_user_id)
            if not konselor_user:
                # Auto-register user from the main table using their role_id
                main_role_id = g.user.get('role_id', 3)
                success, msg = konselor_user_model.add_from_main_user(main_user_id, main_role_id)
                if success:
                    logging.info(f"[KONSELOR GUARD] Auto-registered user {main_user_id} with role {main_role_id}")
                    konselor_user = konselor_user_model.get_by_source_user_id(main_user_id)
                else:
                    logging.warning(
                        f"[KONSELOR GUARD] Gagal auto-register user {main_user_id}: {msg}"
                    )
                    return _deny(view_func, "Anda belum terdaftar di Konselor App. Hubungi admin untuk mendapatkan akses.")

            # Step 2: Gunakan role_id dari konselor_users (bukan dari users utama)
            konselor_role_id = konselor_user.get('role_id')

            # Step 3: Cek permission berdasarkan role konselor
            allowed, data_scope = konselor_role_permission_model.check_permission(
                konselor_role_id, page_identifier, action
            )

            if not allowed:
                logging.warning(
                    f"[KONSELOR GUARD] Akses ditolak: user={konselor_user.get('username')}, "
                    f"role_id={konselor_role_id}, page={page_identifier}, action={action}"
                )
                return _deny(view_func, "Akses ditolak! Anda tidak memiliki izin untuk halaman ini.")

            # Simpan data ke g agar bisa dipakai di route handler
            all_perms = konselor_role_permission_model.get_permissions_by_role(konselor_role_id)
            g.konselor_user = konselor_user
            g.konselor_perms = all_perms.get(page_identifier, {})
            g.konselor_data_scope = data_scope
            g.konselor_all_perms = all_perms

            return view_func(*args, **kwargs)

        return wrapped_view
    return decorator


def _deny(view_func, message):
    """Helper: return 403 JSON untuk API, redirect untuk halaman."""
    # Jika endpoint mengharapkan JSON (biasanya POST atau explicit JSON request)
    if request.is_json or request.method in ("POST", "PUT", "DELETE", "PATCH"):
        return jsonify({"success": False, "message": message}), 403
    # Halaman biasa: redirect ke index
    return redirect(url_for("index"))


def has_permission(page_identifier, action="can_view"):
    """
    Helper function untuk memeriksa apakah user yang sedang login (g.user)
    memiliki izin untuk halaman dan aksi tertentu.
    Bisa digunakan langsung di dalam view function tanpa decorator.
    """
    if not hasattr(g, 'user') or not g.user:
        return False
    
    main_user_id = g.user.get('sub')
    if not main_user_id:
        return False

    from models.konselor import konselor_user_model, konselor_role_permission_model
    
    # Ambil user konselor
    konselor_user = konselor_user_model.get_by_source_user_id(main_user_id)
    if not konselor_user:
        # Coba auto-register
        main_role_id = g.user.get('role_id', 3)
        success, msg = konselor_user_model.add_from_main_user(main_user_id, main_role_id)
        if success:
            konselor_user = konselor_user_model.get_by_source_user_id(main_user_id)
        else:
            return False
            
    if not konselor_user:
        return False

    konselor_role_id = konselor_user.get('role_id')
    allowed, data_scope = konselor_role_permission_model.check_permission(
        konselor_role_id, page_identifier, action
    )
    return bool(allowed)
