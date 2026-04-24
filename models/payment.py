# models/payment.py
# QRIS Static Helper + iPaymu Payment Gateway + DB Model

import os
import io
import json
import hashlib
import hmac
import logging
import requests
import uuid
import base64
from datetime import datetime
from connection import get_connection
from dotenv import load_dotenv

load_dotenv()

# QR Code generation (opsional, untuk QR Merchant statis)
try:
    import qrcode
    import qrcode.image.svg
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False


class QrisHelper:
    """
    QRIS Helper untuk generate QRIS dinamis dari QRIS statis.
    Membaca QRIS_STATIC_STRING dari .env, lalu menambahkan nominal.
    
    Format EMV QRIS:
    - 00: Payload Format Indicator
    - 01: Point of Initiation Method (11=static, 12=dynamic)
    - 26-45: Merchant Account Information
    - 52: Merchant Category Code  
    - 53: Transaction Currency (360 = IDR)
    - 54: Transaction Amount (HANYA ADA DI DYNAMIC QRIS)
    - 58: Country Code
    - 59: Merchant Name
    - 60: Merchant City
    - 63: CRC (Checksum)
    """

    _static_qris_base = None

    @classmethod
    def parse_qris(cls, qris: str) -> dict:
        """Parse QRIS EMV string ke dictionary TLV."""
        data = {}
        pos = 0
        length = len(qris)

        while pos < length:
            if pos + 4 > length:
                break
            tag_id = qris[pos:pos + 2]
            tag_length = int(qris[pos + 2:pos + 4])
            if pos + 4 + tag_length > length:
                break
            value = qris[pos + 4:pos + 4 + tag_length]
            data[tag_id] = value
            pos += 4 + tag_length

        return data

    @classmethod
    def build_qris(cls, data: dict) -> str:
        """Build QRIS string dari dictionary TLV."""
        qris = ''
        for key in sorted(data.keys()):
            if key == '63':  # <--- TAMBAHKAN INI UNTUK MENCEGAH DUPLIKASI CRC
                continue
            value = data[key]
            length = str(len(value)).zfill(2)
            qris += key + length + value

        qris += '6304'
        crc = cls.calculate_crc16(qris)
        qris += format(crc, '04X').upper()
        return qris

    @classmethod
    def calculate_crc16(cls, data: str) -> int:
        """Calculate CRC16-CCITT untuk QRIS."""
        crc = 0xFFFF
        for char in data:
            crc ^= ord(char) << 8
            for _ in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ 0x1021
                else:
                    crc <<= 1
                crc &= 0xFFFF
        return crc

    @classmethod
    def add_amount(cls, amount: int) -> str:
        """
        Convert QRIS statis ke dinamis dengan menambahkan nominal.
        Membaca QRIS_STATIC_STRING dari .env.
        """
        if cls._static_qris_base is None:
            cls._static_qris_base = os.getenv('QRIS_STATIC_STRING', '')
            if not cls._static_qris_base:
                raise ValueError('QRIS_STATIC_STRING is missing in .env')

        data = cls.parse_qris(cls._static_qris_base)
        data['01'] = '12'  # Dynamic
        data['54'] = str(amount)  # Transaction Amount
        return cls.build_qris(data)

    @classmethod
    def generate_qr_code(cls, qris_string: str) -> str:
        """Generate QR Code SVG dari QRIS string."""
        if not QRCODE_AVAILABLE:
            raise ImportError('qrcode library is not installed. Run: pip install qrcode[pil]')

        factory = qrcode.image.svg.SvgPathImage
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(qris_string)
        qr.make(fit=True)

        img = qr.make_image(image_factory=factory)
        buffer = io.BytesIO()
        img.save(buffer)
        return buffer.getvalue().decode('utf-8')

    @classmethod
    def generate_dynamic_qris(cls, amount: int) -> dict:
        """
        Generate QRIS Dinamis dari string statis + nominal.
        Return dict dengan qris_string, qr_svg, qr_data_uri, amount, amount_formatted.
        """
        qris_string = cls.add_amount(amount)
        qr_svg = cls.generate_qr_code(qris_string)

        return {
            'qris_string': qris_string,
            'qr_svg': qr_svg,
            'qr_data_uri': 'data:image/svg+xml;base64,' + base64.b64encode(qr_svg.encode()).decode(),
            'amount': amount,
            'amount_formatted': 'Rp ' + '{:,.0f}'.format(amount).replace(',', '.')
        }


class IPaymuClient:
    """
    Wrapper untuk iPaymu Payment API v2.
    Docs: https://ipaymu.com/api-documentation/
    """

    def __init__(self):
        self.va = os.getenv('IPAYMU_VA', '')
        self.api_key = os.getenv('IPAYMU_API_KEY', '')
        self.base_url = os.getenv('IPAYMU_URL', 'https://sandbox.ipaymu.com')
        self.callback_url = os.getenv('IPAYMU_CALLBACK_URL', '')

        if not self.va or not self.api_key:
            logging.warning("[IPaymu] IPAYMU_VA atau IPAYMU_API_KEY belum diset di .env")

    def _generate_signature(self, body_json: str) -> str:
        """Generate HMAC-SHA256 signature sesuai spesifikasi iPaymu v2."""
        encrypt_body = hashlib.sha256(body_json.encode()).hexdigest()
        string_to_sign = "POST:{}:{}:{}".format(self.va, encrypt_body, self.api_key)
        signature = hmac.new(
            self.api_key.encode(),
            string_to_sign.encode(),
            hashlib.sha256
        ).hexdigest().lower()
        return signature

    def _make_request(self, endpoint: str, body: dict) -> dict:
        """Buat request ke iPaymu API dengan signature."""
        url = f"{self.base_url}{endpoint}"
        body_json = json.dumps(body, separators=(',', ':'))
        signature = self._generate_signature(body_json)
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'signature': signature,
            'va': self.va,
            'timestamp': timestamp
        }

        try:
            response = requests.post(url, headers=headers, data=body_json, timeout=30)
            result = response.json()
            logging.info(f"[IPaymu] {endpoint} -> Status: {response.status_code}")
            return result
        except requests.exceptions.Timeout:
            logging.error(f"[IPaymu] Timeout saat request ke {endpoint}")
            return {'Status': -1, 'Message': 'Request timeout'}
        except Exception as e:
            logging.error(f"[IPaymu] Error request {endpoint}: {e}")
            return {'Status': -1, 'Message': str(e)}

    def create_qris_payment(self, amount: int, reference_id: str,
                            name: str = '', phone: str = '', email: str = '',
                            comments: str = '') -> dict:
        """
        Generate QRIS payment via iPaymu Direct Payment API.
        
        Returns:
            dict with Status, Data (QrImage, TransactionId, etc.)
        """
        body = {
            'name': name or 'Customer',
            'phone': phone or '08000000000',
            'email': email or 'customer@mail.com',
            'amount': str(amount),
            'notifyUrl': self.callback_url,
            'comments': comments or f'Payment {reference_id}',
            'referenceId': reference_id,
            'paymentMethod': 'qris',
            'paymentChannel': 'qris'
        }

        return self._make_request('/api/v2/payment/direct', body)

    def check_transaction(self, transaction_id: int) -> dict:
        """Cek status transaksi di iPaymu."""
        body = {
            'transactionId': transaction_id
        }
        return self._make_request('/api/v2/transaction', body)

    def get_transaction_history(self, page: int = 1, status: int = None,
                                date: str = None) -> dict:
        """Ambil history transaksi dari iPaymu."""
        body = {}
        if status is not None:
            body['status'] = status
        if date:
            body['date'] = date
        return self._make_request('/api/v2/history', body)


class PaymentTransaction:
    """DB Model untuk tabel payment_transactions."""

    @staticmethod
    def _get_connection():
        return get_connection()

    @staticmethod
    def generate_reference_id() -> str:
        """Generate reference ID unik: TPT-{timestamp}-{random}"""
        ts = datetime.now().strftime('%Y%m%d%H%M%S')
        rand = uuid.uuid4().hex[:6].upper()
        return f"TPT-{ts}-{rand}"

    @staticmethod
    def create(user_id: int, reference_id: str, amount: float,
               buyer_name: str = None, buyer_phone: str = None,
               buyer_email: str = None, comments: str = None,
               qr_data: str = None, ipaymu_transaction_id: int = None) -> int:
        """Insert transaksi baru. Return ID atau None."""
        conn = PaymentTransaction._get_connection()
        if not conn:
            return None

        cursor = conn.cursor()
        try:
            query = """
                INSERT INTO payment_transactions 
                (user_id, reference_id, amount, buyer_name, buyer_phone, 
                 buyer_email, comments, qr_data, ipaymu_transaction_id, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
                RETURNING id
            """
            cursor.execute(query, (
                user_id, reference_id, amount, buyer_name, buyer_phone,
                buyer_email, comments, qr_data, ipaymu_transaction_id
            ))
            conn.commit()
            return cursor.fetchone()[0] if cursor.rowcount > 0 else None
        except Exception as e:
            logging.error(f"[PaymentTransaction] Create error: {e}")
            conn.rollback()
            return None
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def update_status(reference_id: str, status: int, 
                      callback_data: dict = None, paid_at: str = None,
                      ipaymu_transaction_id: int = None) -> bool:
        """Update status transaksi (dari callback atau manual check)."""
        conn = PaymentTransaction._get_connection()
        if not conn:
            return False

        cursor = conn.cursor()
        try:
            sets = ["status = %s"]
            params = [status]

            if callback_data:
                sets.append("callback_data = %s")
                params.append(json.dumps(callback_data))

            if paid_at:
                sets.append("paid_at = %s")
                params.append(paid_at)

            if ipaymu_transaction_id:
                sets.append("ipaymu_transaction_id = %s")
                params.append(ipaymu_transaction_id)

            params.append(reference_id)

            query = f"""
                UPDATE payment_transactions 
                SET {', '.join(sets)}
                WHERE reference_id = %s
            """
            cursor.execute(query, params)
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logging.error(f"[PaymentTransaction] Update status error: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def get_by_reference(reference_id: str) -> dict:
        """Ambil transaksi by reference_id."""
        conn = PaymentTransaction._get_connection()
        if not conn:
            return None

        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT * FROM payment_transactions WHERE reference_id = %s",
                (reference_id,)
            )
            result = cursor.fetchone()
            if result:
                # Serialize decimal & datetime
                result = PaymentTransaction._serialize_row(result)
            return result
        except Exception as e:
            logging.error(f"[PaymentTransaction] get_by_reference error: {e}")
            return None
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def get_by_user(user_id: int, page: int = 1, per_page: int = 15,
                    status_filter: int = None) -> dict:
        """Ambil list transaksi per user (paginated)."""
        conn = PaymentTransaction._get_connection()
        if not conn:
            return {'data': [], 'total': 0, 'page': page, 'per_page': per_page}

        cursor = conn.cursor(dictionary=True)
        try:
            where = "WHERE user_id = %s"
            params = [user_id]

            if status_filter is not None:
                where += " AND status = %s"
                params.append(status_filter)

            # Count total
            cursor.execute(f"SELECT COUNT(*) as total FROM payment_transactions {where}", params)
            total = cursor.fetchone()['total']

            # Fetch paginated
            offset = (page - 1) * per_page
            query = f"""
                SELECT * FROM payment_transactions 
                {where}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """
            cursor.execute(query, params + [per_page, offset])
            rows = cursor.fetchall()

            # Serialize
            rows = [PaymentTransaction._serialize_row(r) for r in rows]

            return {
                'data': rows,
                'total': total,
                'page': page,
                'per_page': per_page,
                'total_pages': (total + per_page - 1) // per_page if per_page > 0 else 0
            }
        except Exception as e:
            logging.error(f"[PaymentTransaction] get_by_user error: {e}")
            return {'data': [], 'total': 0, 'page': page, 'per_page': per_page}
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def _serialize_row(row: dict) -> dict:
        """Serialize Decimal, datetime, etc. agar JSON-safe."""
        from decimal import Decimal
        for key, val in row.items():
            if isinstance(val, Decimal):
                row[key] = float(val)
            elif isinstance(val, datetime):
                row[key] = val.strftime('%Y-%m-%d %H:%M:%S')
        return row
