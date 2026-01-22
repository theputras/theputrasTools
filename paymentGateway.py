# paymentGateway.py
# QRIS Payment Gateway - Converted from QrisHelper.php

import os
import io
import base64
from flask import Blueprint, render_template, request, jsonify
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# QR Code generation
try:
    import qrcode
    import qrcode.image.svg
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False

# Blueprint untuk payment routes
payment_bp = Blueprint('payment', __name__)


class QrisHelper:
    """
    QRIS Helper untuk generate QRIS dinamis dari QRIS statis.
    Converted from PHP QrisHelper.php
    
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
        """Parse QRIS EMV string ke dictionary TLV"""
        data = {}
        pos = 0
        length = len(qris)
        
        while pos < length:
            # Minimal butuh 4 karakter (ID 2 + Length 2)
            if pos + 4 > length:
                break
            
            tag_id = qris[pos:pos + 2]
            tag_length = int(qris[pos + 2:pos + 4])
            
            # Pastikan value tidak melampaui string
            if pos + 4 + tag_length > length:
                break
            
            value = qris[pos + 4:pos + 4 + tag_length]
            data[tag_id] = value
            pos += 4 + tag_length
        
        return data
    
    @classmethod
    def build_qris(cls, data: dict) -> str:
        """Build QRIS string dari dictionary TLV"""
        qris = ''
        
        # Urutkan key secara ascending sesuai standar EMV (00, 01, ... 62)
        for key in sorted(data.keys()):
            value = data[key]
            length = str(len(value)).zfill(2)
            qris += key + length + value
        
        # Add CRC placeholder (6304)
        qris += '6304'
        
        # Calculate CRC16-CCITT
        crc = cls.calculate_crc16(qris)
        qris += format(crc, '04X').upper()
        
        return qris
    
    @classmethod
    def calculate_crc16(cls, data: str) -> int:
        """Calculate CRC16-CCITT untuk QRIS"""
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
        Convert QRIS statis ke dinamis dengan menambahkan nominal
        
        Args:
            amount: Nominal dalam rupiah (contoh: 15000)
        
        Returns:
            QRIS string dengan nominal
        """
        # Lazy load from env if None
        if cls._static_qris_base is None:
            cls._static_qris_base = os.getenv('QRIS_STATIC_STRING', '')
            if not cls._static_qris_base:
                raise ValueError('QRIS_STATIC_STRING is missing in .env')
        
        qris = cls._static_qris_base
        
        # Parse QRIS
        data = cls.parse_qris(qris)
        
        # Ubah Point of Initiation dari 11 (static) ke 12 (dynamic)
        data['01'] = '12'
        
        # Tambahkan Transaction Amount (field 54)
        data['54'] = str(amount)
        
        # Rebuild QRIS dengan CRC baru
        return cls.build_qris(data)
    
    @classmethod
    def generate_qr_code(cls, qris_string: str) -> str:
        """
        Generate QR Code SVG dari QRIS string
        
        Args:
            qris_string: QRIS EMV string
        
        Returns:
            SVG image string
        """
        if not QRCODE_AVAILABLE:
            raise ImportError('qrcode library is not installed. Run: pip install qrcode[pil]')
        
        # Create QR Code with SVG output
        factory = qrcode.image.svg.SvgPathImage
        qr = qrcode.QRCode(
            version=None,  # Auto version
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(qris_string)
        qr.make(fit=True)
        
        img = qr.make_image(image_factory=factory)
        
        # Convert to string
        buffer = io.BytesIO()
        img.save(buffer)
        svg_string = buffer.getvalue().decode('utf-8')
        
        return svg_string
    
    @classmethod
    def generate_dynamic_qris(cls, amount: int) -> dict:
        """
        Generate QRIS Dinamis dengan nominal dan return sebagai SVG
        
        Args:
            amount: Nominal dalam rupiah
        
        Returns:
            dict dengan qris_string, qr_svg, qr_data_uri, amount, amount_formatted
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
    
    @classmethod
    def set_static_qris(cls, qris: str) -> None:
        """Set QRIS string statis (jika ingin update dari source lain)"""
        cls._static_qris_base = qris
    
    @classmethod
    def get_static_qris(cls) -> str:
        """Get QRIS string statis saat ini"""
        return cls._static_qris_base


# ============== Flask Routes ==============
@payment_bp.route('/api/pembayaran/generate', methods=['POST'])
def generate_qris_api():
    """API untuk generate QRIS dinamis dengan nominal"""
    try:
        data = request.get_json()
        
        if not data or 'amount' not in data:
            return jsonify({
                'success': False,
                'error': 'Amount is required'
            }), 400
        
        amount = int(data['amount'])
        
        if amount <= 0:
            return jsonify({
                'success': False,
                'error': 'Amount must be greater than 0'
            }), 400
        
        if amount > 10000000:  # Max 10 juta
            return jsonify({
                'success': False,
                'error': 'Amount exceeds maximum limit (Rp 10.000.000)'
            }), 400
        
        result = QrisHelper.generate_dynamic_qris(amount)
        
        return jsonify({
            'success': True,
            'data': result
        })
        
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to generate QRIS: {str(e)}'
        }), 500
