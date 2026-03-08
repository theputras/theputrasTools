# controller/PaymentController.py
# Business logic untuk pembayaran: QR Merchant (static QRIS) + iPaymu QRIS

import logging
from models.payment import QrisHelper, IPaymuClient, PaymentTransaction

# Singleton iPaymu client
_ipaymu_client = None


def _get_client() -> IPaymuClient:
    """Lazy-load iPaymu client instance."""
    global _ipaymu_client
    if _ipaymu_client is None:
        _ipaymu_client = IPaymuClient()
    return _ipaymu_client


def handle_generate_qr_merchant(data: dict) -> tuple:
    """
    Generate QR Merchant (QRIS statis → dinamis) dari QRIS_STATIC_STRING.
    Tidak butuh iPaymu API, langsung generate QR Code lokal.
    
    Returns:
        (response_dict, status_code)
    """
    amount = data.get('amount')

    if not amount:
        return {'success': False, 'error': 'Nominal pembayaran wajib diisi'}, 400

    try:
        amount = int(amount)
    except (ValueError, TypeError):
        return {'success': False, 'error': 'Nominal harus berupa angka'}, 400

    if amount <= 0:
        return {'success': False, 'error': 'Nominal harus lebih dari 0'}, 400

    if amount > 10000000:
        return {'success': False, 'error': 'Nominal maksimal Rp 10.000.000'}, 400

    try:
        result = QrisHelper.generate_dynamic_qris(amount)
        return {'success': True, 'data': result}, 200
    except ValueError as e:
        return {'success': False, 'error': str(e)}, 500
    except Exception as e:
        logging.error(f"[Payment] QR Merchant error: {e}")
        return {'success': False, 'error': f'Gagal generate QRIS: {str(e)}'}, 500


def handle_create_qris(user_id: int, data: dict) -> tuple:
    """
    Generate QRIS payment via iPaymu.
    
    Args:
        user_id: ID user yang login
        data: dict dengan keys: amount, name (optional), phone (opt), email (opt), comments (opt)
    
    Returns:
        (response_dict, status_code)
    """
    amount = data.get('amount')

    if not amount:
        return {'success': False, 'error': 'Nominal pembayaran wajib diisi'}, 400

    try:
        amount = int(amount)
    except (ValueError, TypeError):
        return {'success': False, 'error': 'Nominal harus berupa angka'}, 400

    if amount <= 0:
        return {'success': False, 'error': 'Nominal harus lebih dari 0'}, 400

    if amount > 10000000:
        return {'success': False, 'error': 'Nominal maksimal Rp 10.000.000'}, 400

    # Generate reference ID unik
    reference_id = PaymentTransaction.generate_reference_id()

    name = data.get('name', 'Customer')
    phone = data.get('phone', '')
    email = data.get('email', '')
    comments = data.get('comments', '')

    # Call iPaymu API
    client = _get_client()
    result = client.create_qris_payment(
        amount=amount,
        reference_id=reference_id,
        name=name,
        phone=phone,
        email=email,
        comments=comments
    )

    logging.info(f"[Payment] iPaymu response for {reference_id}: {result}")

    # iPaymu response format: { "Status": 200, "Message": "...", "Data": { ... } }
    if result.get('Status') == 200 and result.get('Data'):
        ipaymu_data = result['Data']

        # Simpan ke DB
        # controller/PaymentController.py (line 72)
        qr_data = (
            ipaymu_data.get('QrImage') or 
            ipaymu_data.get('QrString') or 
            ipaymu_data.get('QrTemplate') or 
            ipaymu_data.get('Url') or 
            ''
        )
        trx_id = ipaymu_data.get('TransactionId')

        PaymentTransaction.create(
            user_id=user_id,
            reference_id=reference_id,
            amount=amount,
            buyer_name=name,
            buyer_phone=phone,
            buyer_email=email,
            comments=comments,
            qr_data=qr_data,
            ipaymu_transaction_id=trx_id
        )

        return {
            'success': True,
            'data': {
                'reference_id': reference_id,
                'amount': amount,
                'amount_formatted': 'Rp ' + '{:,.0f}'.format(amount).replace(',', '.'),
                'qr_image': qr_data,
                'transaction_id': trx_id,
                'expired_in': 300,  # 5 menit
            }
        }, 200
    else:
        error_msg = result.get('Message', 'Gagal generate QRIS dari iPaymu')
        logging.error(f"[Payment] iPaymu error: {error_msg}")
        return {'success': False, 'error': error_msg}, 500


def handle_callback(data: dict) -> tuple:
    """
    Process callback/webhook dari iPaymu saat pembayaran berhasil.
    
    iPaymu callback biasanya mengirim:
    - trx_id: transaction ID
    - reference_id: dari kita
    - status: "berhasil" / "pending" / "expired"
    - status_code: 1 (berhasil), 0 (pending), -2 (expired)
    - via: method bayar (qris, va, dll)
    
    Returns:
        (response_dict, status_code)
    """
    logging.info(f"[Payment] Callback received: {data}")

    reference_id = data.get('reference_id') or data.get('referenceId')
    status_code = data.get('status_code')
    trx_id = data.get('trx_id') or data.get('sid')

    if not reference_id:
        logging.warning("[Payment] Callback tanpa reference_id")
        return {'status': 'error', 'message': 'reference_id required'}, 400

    # Map status
    try:
        status = int(status_code) if status_code is not None else 0
    except (ValueError, TypeError):
        status = 0

    # Tentukan paid_at
    paid_at = None
    if status == 1:
        from datetime import datetime
        paid_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Update DB
    updated = PaymentTransaction.update_status(
        reference_id=reference_id,
        status=status,
        callback_data=data,
        paid_at=paid_at,
        ipaymu_transaction_id=int(trx_id) if trx_id else None
    )

    if updated:
        logging.info(f"[Payment] Transaction {reference_id} updated to status {status}")
        return {'status': 'ok'}, 200
    else:
        logging.warning(f"[Payment] Transaction {reference_id} not found for callback update")
        return {'status': 'error', 'message': 'Transaction not found'}, 404


def handle_check_status(user_id: int, reference_id: str) -> tuple:
    """
    Cek status transaksi (dipanggil polling dari frontend).
    Jika ada ipaymu_transaction_id, cek juga ke iPaymu API.
    
    Returns:
        (response_dict, status_code)
    """
    txn = PaymentTransaction.get_by_reference(reference_id)

    if not txn:
        return {'success': False, 'error': 'Transaksi tidak ditemukan'}, 404

    # Pastikan user hanya bisa cek transaksi miliknya
    if txn['user_id'] != user_id:
        return {'success': False, 'error': 'Akses ditolak'}, 403

    # Jika masih pending dan ada ipaymu_transaction_id, cek ke iPaymu
    if txn['status'] == 0 and txn.get('ipaymu_transaction_id'):
        client = _get_client()
        result = client.check_transaction(txn['ipaymu_transaction_id'])

        if result.get('Status') == 200 and result.get('Data'):
            ipaymu_status = result['Data'].get('Status')
            if ipaymu_status is not None and int(ipaymu_status) != 0:
                # Status berubah di iPaymu, update DB lokal
                new_status = int(ipaymu_status)
                paid_at = None
                if new_status == 1:
                    from datetime import datetime
                    paid_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                PaymentTransaction.update_status(
                    reference_id=reference_id,
                    status=new_status,
                    callback_data=result.get('Data'),
                    paid_at=paid_at
                )
                txn['status'] = new_status
                if paid_at:
                    txn['paid_at'] = paid_at

    return {
        'success': True,
        'data': {
            'reference_id': txn['reference_id'],
            'amount': txn['amount'],
            'amount_formatted': 'Rp ' + '{:,.0f}'.format(txn['amount']).replace(',', '.'),
            'status': txn['status'],
            'status_label': _status_label(txn['status']),
            'paid_at': txn.get('paid_at'),
            'qr_image': txn.get('qr_data'),
        }
    }, 200


def handle_list_transactions(user_id: int, page: int = 1, per_page: int = 15,
                              status_filter: int = None) -> tuple:
    """
    Ambil list transaksi user (paginated).
    
    Returns:
        (response_dict, status_code)
    """
    result = PaymentTransaction.get_by_user(
        user_id=user_id,
        page=page,
        per_page=per_page,
        status_filter=status_filter
    )

    # Tambahkan status_label ke setiap row
    for row in result['data']:
        row['status_label'] = _status_label(row.get('status', 0))
        row['amount_formatted'] = 'Rp ' + '{:,.0f}'.format(row.get('amount', 0)).replace(',', '.')

    return {'success': True, **result}, 200


def _status_label(status: int) -> str:
    """Mapping status code ke label."""
    labels = {
        0: 'Pending',
        1: 'Berhasil',
        -2: 'Expired'
    }
    return labels.get(status, 'Unknown')
