# 📡 SSKM RFID Reader - Arduino UNO Version

## 📦 Hardware Requirements

- ✅ **Arduino UNO** (R3 atau kompatibel)
- ✅ **MFRC522 RFID Module** (RC522)
- ✅ **Passive Buzzer**
- ✅ **Kabel Jumper**
- ✅ **Kabel USB**

---

## 🔌 Wiring Diagram

Hubungkan RC522 dan Buzzer ke Arduino UNO:

| RC522 Pin | Arduino UNO Pin | Keterangan |
|-----------|------------------|------------|
| **SDA (SS)** | Pin **10** | Slave Select |
| **SCK** | Pin **13** | Serial Clock |
| **MOSI** | Pin **11** | Master Out Slave In |
| **MISO** | Pin **12** | Master In Slave Out |
| **IRQ** | *Tidak dipakai* | - |
| **GND** | **GND** | Ground |
| **RST** | Pin **9** | Reset |
| **3.3V** | **3.3V** | Power ⚠️ **JANGAN 5V!** |

### Wiring Buzzer
| Buzzer Pin | Arduino UNO Pin |
|------------|------------------|
| **(+) Positif** | Pin **8** |
| **(-) Negatif** | **GND** |

---

## 🚀 Setup Guide

1. **Install Library**:
   - Buka Arduino IDE
   - Sketch → Include Library → Manage Libraries
   - Cari dan Install: `MFRC522` by GithubCommunity

2. **Upload Code**:
   - Buka file `SSKM_RFID_Reader_UNO.ino`
   - Pilih Board: **Arduino Uno**
   - Upload!

3. **Test**:
   - Buka Serial Monitor (9600)
   - Tempel kartu → Bunyi **BEEP** + UID muncul di layar
   - Buka Browser → SSKM Record → Connect Device #UNO

---

## ⚠️ Bedanya sama Mega?
Hanya beda di wiring pin. Codingan logic-nya sama persis.
- **UNO**: SDA(10), SCK(13), MOSI(11), MISO(12), RST(9)
- **MEGA**: SDA(53), SCK(52), MOSI(51), MISO(50), RST(5)
