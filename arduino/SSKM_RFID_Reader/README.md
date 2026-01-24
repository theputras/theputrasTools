# 📡 SSKM RFID Reader - Arduino Setup Guide

## 📦 Hardware Requirements

- ✅ **Arduino Mega 2560**
- ✅ **MFRC522 RFID Module** (RC522)
- ✅ **Kabel Jumper** (Female-to-Male)
- ✅ **Kartu RFID** / Key Fob (13.56MHz)
- ✅ **Kabel USB** (Arduino ke PC)

---

## 🔌 Wiring Diagram

Hubungkan RC522 ke Arduino Mega 2560:

| RC522 Pin | Arduino Mega Pin | Keterangan |
|-----------|------------------|------------|
| **SDA (SS)** | Pin **53** | Slave Select |
| **SCK** | Pin **52** | Serial Clock |
| **MOSI** | Pin **51** | Master Out Slave In |
| **MISO** | Pin **50** | Master In Slave Out |
| **IRQ** | *Tidak dipakai* | - |
| **GND** | **GND** | Ground |
| **RST** | Pin **5** | Reset |
| **3.3V** | **3.3V** | Power ⚠️ **JANGAN 5V!** |

### ⚠️ PENTING:
- RC522 **hanya support 3.3V**
- Jangan colok ke pin 5V, bisa rusak!

---

## 📚 Library Installation

1. Buka **Arduino IDE**
2. Go to: `Sketch` → `Include Library` → `Manage Libraries...`
3. Search: `MFRC522`
4. Install: **MFRC522 by GithubCommunity**
5. Klik **Install**

---

## 🚀 Upload ke Arduino

### Step 1: Buka Sketch
1. Buka file `SSKM_RFID_Reader.ino` di Arduino IDE
2. Atau copy-paste code dari file

### Step 2: Setup Board
1. Tools → Board → **Arduino Mega or Mega 2560**
2. Tools → Port → Pilih port Arduino (biasanya COM3, COM4, dll)
3. Tools → Processor → **ATmega2560**

### Step 3: Upload
1. Klik tombol **Upload** (→)
2. Tunggu sampai selesai: `Done uploading`

### Step 4: Test
1. Buka **Serial Monitor** (Ctrl + Shift + M)
2. Set baud rate: **9600**
3. Tempelkan kartu RFID
4. Harusnya muncul: `[SENT] UID: XXXXXXXX`

---

## 🌐 Koneksi ke Web App

### Step 1: Buka Browser
1. Navigate ke: `http://localhost:5000/sskm_record`
2. Klik tombol **"RFID Settings"** (⚙️ biru)

### Step 2: Scan Device
1. Klik **"Scan Perangkat"**
2. Browser akan minta pilih port Serial
3. Pilih: **Arduino Mega 2560** (atau USB Serial Port)
4. Klik **"Connect"** / **"Hubungkan"**

### Step 3: Test Auto-Enter
1. Status indicator berubah **hijau** = Connected ✅
2. Tempelkan kartu RFID ke reader
3. UID otomatis muncul dan **auto-submit**!
4. Data langsung masuk ke tabel 🎉

---

## 🎯 Cara Kerja

```
┌─────────────┐
│ Kartu RFID  │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   RC522     │  Baca UID
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Arduino   │  Kirim via Serial
└──────┬──────┘
       │ USB
       ▼
┌─────────────┐
│   Browser   │  Web Serial API
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Auto-Enter! │  Data masuk otomatis
└─────────────┘
```

---

## ⚙️ Konfigurasi

### Debounce Time (Cooldown)
Default: **2 detik** (mencegah double-scan)

Untuk ubah, edit di Arduino code:
```cpp
const unsigned long DEBOUNCE_DELAY = 2000; // 2000ms = 2 detik
```

### Baud Rate
Default: **9600** (harus sama dengan browser)

Jangan ubah kecuali tahu apa yang dilakukan!

---

## 🔧 Troubleshooting

### ❌ Browser tidak detect Arduino
**Solusi:**
- Pastikan Arduino sudah upload code
- Coba cabut-colok USB
- Restart browser (Chrome/Edge terbaru)
- Check Device Manager (Windows) apakah port terdeteksi

### ❌ UID tidak terbaca
**Solusi:**
- Check wiring (pastikan sesuai tabel)
- Pastikan RC522 dapat 3.3V (bukan 5V!)
- Buka Serial Monitor, lihat apakah ada output
- Tempelkan kartu lebih dekat ke reader

### ❌ Data tidak auto-enter
**Solusi:**
- Pastikan browser sudah connect (status hijau)
- Check Serial Monitor: apakah Arduino kirim data dengan `\n` (newline)?
- Restart koneksi Serial di browser

### ❌ Kartu detect berkali-kali
**Solusi:**
- Increase debounce delay di code Arduino
- Jangan tahan kartu terlalu lama di reader

---

## 🎛️ Optional: LED Feedback

Mau tambah LED indicator? Uncomment code ini di Arduino:

```cpp
#define LED_PIN 13

void setup() {
  pinMode(LED_PIN, OUTPUT);
  // ... existing code
}

void loop() {
  // ... setelah berhasil baca kartu
  blinkLED(2); // Kedip 2x
}
```

---

## 📝 Format Data

### UUID (8 karakter):
```
Contoh: A1B2C3D4
Auto-detect: UUID mode
```

### NIM (11 karakter):
```
Contoh: 42016100521
Auto-detect: NIM mode
```

Arduino akan otomatis potong UID jadi max 11 karakter.

---

## ✅ Checklist

- [ ] Hardware terhubung benar
- [ ] Library MFRC522 terinstall
- [ ] Code berhasil di-upload
- [ ] Serial Monitor test OK
- [ ] Browser detect Arduino
- [ ] Auto-enter works!

---

## 🎉 Success!

Sekarang lu punya RFID attendance system yang **fully automated**:
1. Tempel kartu → Langsung masuk data
2. Real-time counter update
3. No click needed!

**Happy coding! 🚀**
