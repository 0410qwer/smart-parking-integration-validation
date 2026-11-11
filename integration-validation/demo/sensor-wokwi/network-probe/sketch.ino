// Connectivity probe ONLY. No MQTT publish and no public broker or tunnel.
#include <Arduino.h>
#include <WiFi.h>
void setup(){
 Serial.begin(115200); delay(300);
 Serial.println("[NETWORK] Joining Wokwi-GUEST; no source event publishing");
 WiFi.begin("Wokwi-GUEST","",6);
 uint32_t started=millis();
 while(WiFi.status()!=WL_CONNECTED && uint32_t(millis()-started)<20000)delay(100);
 if(WiFi.status()!=WL_CONNECTED){Serial.println("[NETWORK] WIFI_TIMEOUT");return;}
 Serial.printf("[NETWORK] wifi_ip=%s\n",WiFi.localIP().toString().c_str());
 WiFiClient client;client.setTimeout(2000);
 bool connected=client.connect("host.wokwi.internal",18884,3000);
 Serial.printf("[NETWORK] host=host.wokwi.internal port=18884 tcp_connected=%d\n",connected);
 client.stop();
 Serial.println("[NETWORK] DONE; no MQTT packets transmitted by this probe");
}
void loop(){delay(1000);}
