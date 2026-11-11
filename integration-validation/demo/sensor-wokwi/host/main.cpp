#include "../firmware/sketch.ino"
int main(){
 selfTest();
 writes.clear(); suppliedPulse=580;
 bool ok=measureEcho()==580 && writes==std::vector<int>{50,51,50} && lastTimeout==25000;
 std::printf("[HOST] %s trigger_echo_api_contract\n",ok?"PASS":"FAIL");
 // Explicitly labelled synthetic clock/pulse fixture for JSON compatibility checks.
 sensor=Occupancy(); counter=0;
 for(uint32_t now=0;now<=12000;now+=100){
   clockMs=now;suppliedPulse=(now>=3500 && now<6500)?580:2030;
   int event=sensor.sample(suppliedPulse,now);
   if(event)emitState(event==1);
   else if(sensor.trusted && uint32_t(now-lastMessage)>=HEARTBEAT_MS)emitState(true);
 }
 return ok?0:1;
}
