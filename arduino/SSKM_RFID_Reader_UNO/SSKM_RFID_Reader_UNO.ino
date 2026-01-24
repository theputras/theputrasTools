/*
 * SSKM RFID Reader - Arduino UNO Version
 * 
 * Deskripsi:
 * - Membaca kartu RFID RC522
 * - Mengirim UID via Serial ke browser (Web Serial API)
 * - Auto-enter support
 * - Passive Buzzer feedback
 * 
 * Library Required:
 * - MFRC522 by GithubCommunity
 * 
 * Wiring RC522 ke Arduino UNO:
 * =======================================
 * RC522 Pin  ->  Arduino UNO Pin
 * ---------------------------------------
 * SDA (SS)   ->  Pin 10
 * SCK        ->  Pin 13
 * MOSI       ->  Pin 11
 * MISO       ->  Pin 12
 * IRQ        ->  (tidak digunakan)
 * GND        ->  GND
 * RST        ->  Pin 9
 * 3.3V       ->  3.3V (JANGAN 5V!)
 * =======================================
 * 
 * Wiring Buzzer:
 * (+) Positif -> Pin 8
 * (-) Negatif -> GND
 */

#include <SPI.h>
#include <MFRC522.h>

// Pin definitions untuk Arduino UNO
#define SS_PIN 10    // SDA/SS pin (Beda dengan Mega)
#define RST_PIN 9    // Reset pin (Beda dengan Mega)
#define BUZZER_PIN 8 // Pin Buzzer (Sama)

// Inisialisasi MFRC522
MFRC522 mfrc522(SS_PIN, RST_PIN);

// Variabel untuk debouncing
String lastUID = "";
unsigned long lastReadTime = 0;
const unsigned long DEBOUNCE_DELAY = 2000; // 2 detik cooldown

void setup() {
  // Delay startup agar stabil
  delay(1000);
  
  // Setup Buzzer Output
  pinMode(BUZZER_PIN, OUTPUT);

  // Inisialisasi Serial
  Serial.begin(9600);
  
  // Inisialisasi SPI bus
  SPI.begin();
  
  // Inisialisasi MFRC522
  mfrc522.PCD_Init();
  
  // Delay kecil
  delay(100);
  
  // Bunyi beep tanda ready (2x beep pendek)
  tone(BUZZER_PIN, 2000, 100);
  delay(150);
  tone(BUZZER_PIN, 2500, 100);
  
  Serial.println("SSKM RFID Reader (UNO) - READY");
}

void loop() {
  // Cek apakah ada kartu baru
  if (!mfrc522.PICC_IsNewCardPresent()) {
    return;
  }

  // Cek apakah kartu bisa dibaca
  if (!mfrc522.PICC_ReadCardSerial()) {
    return;
  }

  // Baca UID dari kartu
  String currentUID = getUID();
  
  // Debouncing: cek apakah kartu yang sama dalam 2 detik terakhir
  unsigned long currentTime = millis();
  if (currentUID == lastUID && (currentTime - lastReadTime) < DEBOUNCE_DELAY) {
    // Kartu sama dalam waktu dekat, skip
    mfrc522.PICC_HaltA();
    return;
  }
  
  // Update last read info
  lastUID = currentUID;
  lastReadTime = currentTime;
  
  // Kirim UID ke browser via Serial
  Serial.println(currentUID);
  
  // Bunyi Beep SUKSES
  tone(BUZZER_PIN, 3000, 100); // 3000Hz selama 100ms
  
  // Halt PICC (stop communication with card)
  mfrc522.PICC_HaltA();
  
  // Stop encryption on PCD
  mfrc522.PCD_StopCrypto1();
}

/**
 * Membaca dan convert UID menjadi string
 * Untuk UUID (8 karakter) atau NIM (11 karakter)
 */
String getUID() {
  String uid = "";
  
  // Loop untuk setiap byte UID
  for (byte i = 0; i < mfrc522.uid.size; i++) {
    // Convert byte ke hex string (uppercase)
    if (mfrc522.uid.uidByte[i] < 0x10) {
      uid += "0"; // Tambah leading zero
    }
    uid += String(mfrc522.uid.uidByte[i], HEX);
  }
  
  // Convert ke uppercase
  uid.toUpperCase();
  
  // Potong jika lebih dari 11 karakter (untuk NIM)
  if (uid.length() > 11) {
    uid = uid.substring(0, 11);
  }
  
  return uid;
}
