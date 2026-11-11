// Three independent Wokwi HC-SR04 instances on ONE simulated ESP32.
// No physical accuracy, magnetic fusion, measured battery or direct MQTT claim.
#include <Arduino.h>
const uint32_t ECHO_TIMEOUT_US=25000;
struct Reading { bool valid; uint32_t mm; };
Reading distanceFromEcho(uint32_t pulse) {
  if (pulse == 0 || pulse >= ECHO_TIMEOUT_US) return {false, 0};
  uint32_t mm = (pulse * 10U + 29U) / 58U;
  // 58 us/cm is approximate: Wokwi's nominal 400cm can calculate about 4056mm.
  return {mm >= 20 && mm <= 4100, mm};
}

class Occupancy {
 public:
  bool known = false, occupied = false, trusted = false, fault = true;
  int candidate = -1;
  uint32_t since = 0;
  // 1 = initial/recovered same-state baseline (heartbeat); 2 = actual transition.
  int sample(uint32_t pulse, uint32_t now) {
    Reading value = distanceFromEcho(pulse);
    if (!value.valid) { trusted = false; fault = true; candidate = -1; return 0; }
    int target = value.mm <= 120 ? 1 : value.mm >= 220 ? 0 : -1;
    if (target < 0) { candidate = -1; return 0; } // hysteresis band never invents initial state
    if (trusted && target == int(occupied)) { candidate = -1; return 0; }
    if (candidate != target) { candidate = target; since = now; return 0; }
    uint32_t confirm = target ? 1500 : 2500;
    if (uint32_t(now - since) < confirm) return 0;
    bool changed = known && occupied != bool(target);
    known = true; occupied = bool(target); trusted = true; fault = false; candidate = -1;
    return changed ? 2 : 1;
  }
};

struct BayNode { uint32_t id; int trig; int echo; Occupancy sensor; uint8_t ctr=0; uint32_t lastSent=0; };
void emit(BayNode &bay,bool heartbeat); // prevent Arduino's prototype generator moving the type reference
BayNode bays[]={{1001,5,18},{1002,19,21},{1003,22,23}};
void emit(BayNode &bay,bool heartbeat){
 if(!bay.sensor.known||!bay.sensor.trusted)return;
 Serial.printf("[EVENT] spot_id=%lu t_ms=%lu ctr=%u heartbeat=%d\n",(unsigned long)bay.id,(unsigned long)millis(),bay.ctr,heartbeat);
 Serial.printf("{\"spot_id\":%lu,\"occupied\":%s,\"batt_mv\":3600,\"status\":%u,\"ctr\":%u,\"heartbeat\":%s}\n",
  (unsigned long)bay.id,bay.sensor.occupied?"true":"false",bay.sensor.occupied?1:0,bay.ctr++,heartbeat?"true":"false");
 bay.lastSent=millis();
}
void setup(){
 Serial.begin(115200);delay(300);
 Serial.println("[BOOT] MULTI HC-SR04: 3 virtual sensors; battery placeholder; Serial only");
 for(auto &bay:bays){pinMode(bay.trig,OUTPUT);pinMode(bay.echo,INPUT);digitalWrite(bay.trig,LOW);}
}
void loop(){
 for(auto &bay:bays){
  digitalWrite(bay.trig,LOW);delayMicroseconds(2);digitalWrite(bay.trig,HIGH);delayMicroseconds(10);digitalWrite(bay.trig,LOW);
  uint32_t pulse=pulseIn(bay.echo,HIGH,ECHO_TIMEOUT_US);uint32_t now=millis();
  int event=bay.sensor.sample(pulse,now);Reading value=distanceFromEcho(pulse);
  Serial.printf("[SENSOR] spot_id=%lu t_ms=%lu echo_us=%lu distance_mm=%lu valid=%d trusted=%d occupied=%d\n",
   (unsigned long)bay.id,(unsigned long)now,(unsigned long)pulse,(unsigned long)value.mm,value.valid,bay.sensor.trusted,bay.sensor.occupied);
  if(event)emit(bay,event==1);else if(bay.sensor.trusted&&uint32_t(now-bay.lastSent)>=5000)emit(bay,true);
 }
 delay(100);
}
