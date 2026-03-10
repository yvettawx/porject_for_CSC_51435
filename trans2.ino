#include "heltec.h"

#define BAND 868E6
#define SLEEP_TIME 4   // seconds

// Persistent variables (survive deep sleep)
RTC_DATA_ATTR int fill2 = 0;
RTC_DATA_ATTR int fill3 = 0;
RTC_DATA_ATTR int fullCycles2 = 0;  // how many cycles bin stayed full
RTC_DATA_ATTR int fullCycles3 = 0;

void setup() {
  Serial.begin(115200);

  // Initialize Heltec (OLED off, LoRa on)
  Heltec.begin(false, true, true, true, BAND);

  // Seed random generator (ESP32 hardware randomness)
  randomSeed(esp_random());

  // -------- 1️⃣ Simulate Gradual Filling --------
  fill2 += random(0, 6);   // increase 0–5 %
  fill3 += random(0, 6);

  if (fill2 > 100) fill2 = 100;
  if (fill3 > 100) fill3 = 100;
  

  // -------- 2️⃣ Determine Status --------
  String stat2 = (fill2 > 80) ? "FULL" : "EMPTY";
  String stat3 = (fill3 > 80) ? "FULL" : "EMPTY";

  // -------- 3️⃣ Random Movement (10%) --------
  int mov2 = (random(0, 100) < 10) ? 1 : 0;
  int mov3 = (random(0, 100) < 10) ? 1 : 0;

  // -------- 4️⃣ Create Messages --------
  String msg2 = "ID:2,STAT:" + stat2 + ",Mov:" + String(mov2)+",Percentage:"+String(fill2);
  String msg3 = "ID:3,STAT:" + stat3 + ",Mov:" + String(mov3)+",Percentage:"+String(fill3);

  // -------- 5️⃣ Send via LoRa --------
  LoRa.beginPacket();
  LoRa.print(msg2);
  LoRa.endPacket();
  delay(100);
  LoRa.beginPacket();
  LoRa.print(msg3);
  LoRa.endPacket();
  Serial.println(msg2);
  Serial.println(msg3);

  // -------- 6️⃣ Simulate Collection (stay full for 3 cycles before reset) --------
  if (fill2 >= 100) {
    fullCycles2++;
    if (fullCycles2 >= 3) { fill2 = 0; fullCycles2 = 0; }
  }
  if (fill3 >= 100) {
    fullCycles3++;
    if (fullCycles3 >= 3) { fill3 = 0; fullCycles3 = 0; }
  }

  // -------- 7️⃣ Deep Sleep --------
  esp_sleep_enable_timer_wakeup(SLEEP_TIME * 1000000ULL);
  esp_deep_sleep_start();
}

void loop() {}