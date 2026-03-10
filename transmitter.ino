#include "heltec.h"
#include <Wire.h>

#define BAND 868E6
#define SLEEP_TIME 4
#define MPU_ADDR 0x68

const int trigPin = 13;
const int echoPin = 39;

float accX, accY, accZ;
bool mpuOK = false;

void initMPU() {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x6B);
  Wire.write(0);
  mpuOK = (Wire.endTransmission(true) == 0);
}

bool readMPU() {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(MPU_ADDR, 6, true) != 6) return false;

  int16_t rawX = Wire.read() << 8 | Wire.read();
  int16_t rawY = Wire.read() << 8 | Wire.read();
  int16_t rawZ = Wire.read() << 8 | Wire.read();


  accX = rawX / 16384.0;
  accY = rawY / 16384.0;
  accZ = rawZ / 16384.0;

  return true;
}

bool detectShake() {
  if (!readMPU()){ Serial.print("hii");return false;}

  float mag = sqrt(accX * accX + accY * accY + accZ * accZ);
  float dynamicAcc = abs(mag - 1.0);
  // Serial.println(dynamicAcc);

  if (dynamicAcc > 0.03) {  // 0.2g deviation = movement
    return true;
  }

  return false;
}

void setup() {
  Serial.begin(115200);
  Heltec.begin(false, true, true, true, BAND);

  Wire.begin();
  Wire.setClock(100000);
  initMPU();

  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);

  // -------- Distance Measurement --------
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  long duration = pulseIn(echoPin, HIGH, 30000);
  int distance = (duration > 0) ? (duration * 0.034 / 2.0) : 999;

  // -------- Percentage & Status --------
  float percentage = ((22.0f - distance) / 22.0f) * 100.0f;
  if (percentage < 0) percentage = 0;
  if (percentage > 100) percentage = 100;

  String status = (percentage >= 80) ? "FULL" : "EMPTY";
  Serial.print(distance);

  // -------- Movement Detection --------
  int mov = 0;

  if (mpuOK && detectShake()) {
    mov = 1;
  }
  // -------- Create LoRa Packet --------
  String dataToSend = "ID:1,STAT:" + status + ",Mov:" + String(mov)+",Percentage:"+String(percentage);

  LoRa.beginPacket();
  LoRa.print(dataToSend);
  LoRa.endPacket();

  Serial.println(dataToSend);

  // -------- Sleep --------
  Heltec.display->displayOff();
  digitalWrite(Vext, LOW);
  esp_sleep_enable_timer_wakeup(SLEEP_TIME * 1000000ULL);
  esp_deep_sleep_start();
}

void loop() {}