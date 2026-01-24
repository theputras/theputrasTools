/*
 * SSKM RFID Reader - Arduino Mega 2560 + RC522
 * 
 * Deskripsi:
 * - Membaca kartu RFID RC522
 * - Mengirim UID via Serial ke browser
 * - Auto-enter (browser langsung proses tanpa klik)
 * 
 * Library Required:
 * - MFRC522 by GithubCommunity (Install via Library Manager)
 * 
 * Wiring RC522 ke Arduino Mega 2560:
 * =======================================
 * RC522 Pin  ->  Arduino Mega Pin
 * ---------------------------------------
 * SDA (SS)   ->  Pin 53
 * SCK        ->  Pin 52
 * MOSI       ->  Pin 51
 * MISO       ->  Pin 50
 * IRQ        ->  (tidak digunakan)
 * GND        ->  GND
 * RST        ->  Pin 5
 * 3.3V       ->  3.3V (JANGAN 5V!)
 * =======================================
 */

#include <SPI.h>
#include <MFRC522.h>

// Pin definitions untuk Arduino Mega 2560
#define SS_PIN 53    // SDA/SS pin
#define RST_PIN 5    // Reset pin
#define BUZZER_PIN 8 // Pin Buzzer

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
   // Tampilkan info di Serial Monitor
//   Serial.println("=================================");
//   Serial.println("=================================");
//   Serial.println("SSKM RFID Reader - READY");
//   Serial.println("=================================");
//   Serial.println("Tempelkan kartu RFID...");
//   Serial.println();
    Serial.println("cekrfidd");
//   // Tampilkan versi firmware RC522
//   mfrc522.PCD_DumpVersionToSerial();
//   Serial.println();
  // Bunyi beep tanda ready
  tone(BUZZER_PIN, 2000, 200); // 2000Hz selama 200ms
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
  
  // Bunyi Beep SUKSES (Passive Buzzer)
  tone(BUZZER_PIN, 3000, 100); // 3000Hz selama 100ms

  
  // Optional: Feedback visual di Serial Monitor
//   Serial.print("[SENT] UID: ");
//   Serial.println(currentUID);
  
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

/**
 * Optional: Fungsi untuk LED feedback (jika mau tambah LED)
 * Uncomment jika mau pakai
 */
/*
#define LED_PIN 13

void blinkLED(int times) {
  for (int i = 0; i < times; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(100);
    digitalWrite(LED_PIN, LOW);
    delay(100);
  }
}
*/
