"""Generate an isolated three-sensor sketch, reusing the verified occupancy implementation."""
from pathlib import Path
import json
HERE=Path(__file__).resolve().parent
source=(HERE.parent/'sensor-wokwi/firmware/sketch.ino').read_text()
logic=source[source.index('struct Reading'):source.index('\nOccupancy sensor;')]
sketch='''// Three independent Wokwi HC-SR04 instances on ONE simulated ESP32.
// No physical accuracy, magnetic fusion, measured battery or direct MQTT claim.
#include <Arduino.h>
const uint32_t ECHO_TIMEOUT_US=25000;
'''+logic+'''
struct BayNode { uint32_t id; int trig; int echo; Occupancy sensor; uint8_t ctr=0; uint32_t lastSent=0; };
void emit(BayNode &bay,bool heartbeat); // prevent Arduino's prototype generator moving the type reference
BayNode bays[]={{1001,5,18},{1002,19,21},{1003,22,23}};
void emit(BayNode &bay,bool heartbeat){
 if(!bay.sensor.known||!bay.sensor.trusted)return;
 Serial.printf("[EVENT] spot_id=%lu t_ms=%lu ctr=%u heartbeat=%d\\n",(unsigned long)bay.id,(unsigned long)millis(),bay.ctr,heartbeat);
 Serial.printf("{\\"spot_id\\":%lu,\\"occupied\\":%s,\\"batt_mv\\":3600,\\"status\\":%u,\\"ctr\\":%u,\\"heartbeat\\":%s}\\n",
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
  Serial.printf("[SENSOR] spot_id=%lu t_ms=%lu echo_us=%lu distance_mm=%lu valid=%d trusted=%d occupied=%d\\n",
   (unsigned long)bay.id,(unsigned long)now,(unsigned long)pulse,(unsigned long)value.mm,value.valid,bay.sensor.trusted,bay.sensor.occupied);
  if(event)emit(bay,event==1);else if(bay.sensor.trusted&&uint32_t(now-bay.lastSent)>=5000)emit(bay,true);
 }
 delay(100);
}
'''
folder=HERE/'firmware';folder.mkdir(exist_ok=True)
(folder/'sketch.ino').write_text(sketch)
parts=[dict(type='board-esp32-devkit-c-v4',id='esp',top=180,left=90,attrs={})]
wires=[['esp:TX','$serialMonitor:RX','',[]],['esp:RX','$serialMonitor:TX','',[]]]
for i,(trig,echo,distance) in enumerate([(5,18,350),(19,21,10),(22,23,350)],1):
    part='ultrasonic'+str(i)
    positions=[(-160,-50),(-160,170),(-20,60)]
    top,left=positions[i-1]
    parts.append(dict(type='wokwi-hc-sr04',id=part,top=top,left=left,attrs=dict(distance=str(distance))))
    switch='fault'+str(i)
    parts.append(dict(type='wokwi-slide-switch',id=switch,top=top+90,left=left+30,attrs=dict(value='',bounce='0')))
    wires.extend([[part+':VCC','esp:5V','red',[]],[part+':GND','esp:GND.1','black',[]],
                  [part+':TRIG','esp:'+str(trig),'green',[]],[part+':ECHO',switch+':1','blue',[]],
                  [switch+':2','esp:'+str(echo),'blue',[]],[switch+':3','esp:GND.1','black',[]]])
(folder/'diagram.json').write_text(json.dumps(dict(version=1,author='Isolated three-bay integration',editor='wokwi',parts=parts,connections=wires),indent=2))
