#include "heltec.h"

#define BAND 868E6

void setup() {
  Heltec.begin(true, true, true, true, BAND);
  Serial.begin(115200);
  
  Serial.println("LoRa String Receiver Initialized...");
}

void loop() {
  int packetSize = LoRa.parsePacket();
  if (packetSize) {
    String incoming = "";

    // Read the packet character by character
    while (LoRa.available()) {
      incoming += (char)LoRa.read();
    }

    // Log the raw string to Serial
    Serial.println(incoming);

    // Update OLED
    Heltec.display->clear();
    Heltec.display->drawString(0, 0, "New Message:");
    // If the string is long, we split it manually or just show the whole thing
    Heltec.display->drawString(0, 15, incoming); 
    
    // Quick Logic: Check if the string contains "FULL"
    if (incoming.indexOf("FULL") >= 0) {
      Heltec.display->drawString(0, 35, "ALERT: BIN FULL");
    }

    Heltec.display->display();
  }
}