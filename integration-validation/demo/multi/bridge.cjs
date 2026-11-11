const path=require('node:path');const fs=require('node:fs');const {LiveBridge}=require('../live/bridge.cjs');
class MultiBridge extends LiveBridge{
 constructor(options){super({...options,firmwareDirectory:path.join(__dirname,'firmware'),workerScript:path.join(__dirname,'outbox.py'),workerExtraArgs:['--session',options.session]});this.diagnostics={};this.actions=[];}
 async pump(){
  try{
   while(!this.stopping){
    const body=await this.page.locator('body').innerText();const now=Date.now();
    for(const line of body.split(/\r?\n/)){
     const match=line.match(/^\[SENSOR\] spot_id=(100[123]) t_ms=(\d+) echo_us=(\d+) distance_mm=(\d+) valid=(\d) trusted=(\d) occupied=(\d)$/);
     if(match){const id=match[1];if(this.diagnostics[id]?.line!==line){
      const old=this.diagnostics[id];if(old&&Number(match[2])<=old.sim_t_ms)continue;
      this.diagnostics[id]={line,at:now,sim_t_ms:Number(match[2]),state:match[6]==='1'?'online':'untrusted',distance_mm:Number(match[4]),echo_us:Number(match[3])};
      if(!old||old.distance_mm!==Number(match[4]))this.log('sensor_distance_observed',{spot_id:Number(id),distance_mm:Number(match[4]),sim_t_ms:Number(match[2]),observed_wall_ms:now});
     }}
    }
    if(now-this.lastHealthWall>500){
     const sources={};for(const id of [1001,1002,1003]){
      const d=this.diagnostics[id];sources[id]={state:!d?'untrusted':now-d.at>5000?'stalled':d.state,
       distance_mm:d?.distance_mm??null,echo_us:d?.echo_us??null,observed_at:d?new Date(d.at).toISOString():null};
     }
     this.worker.stdin.write(JSON.stringify({kind:'health',sources})+'\n');const ack=await this.receive();if(!ack.ok)throw new Error(ack.error);this.lastHealthWall=now;
    }
    const markers=[...body.matchAll(/^\[EVENT\] spot_id=(\d+) t_ms=(\d+) ctr=(\d+) heartbeat=(\d)$/gm)];
    const pending=this.cursor.extract(body);if(pending.length>512)throw new Error('Live Serial backlog exceeded 512; refusing silent loss');
    for(const record of pending){
     const marker=markers[record.serial_index];
     const observation={...record,observed_at:Date.now(),monotonic_observed_ms:performance.now(),firmware_confirmed_sim_ms:marker?Number(marker[2]):null};
     this.log('observed_live_multi_serial',observation);this.worker.stdin.write(JSON.stringify(observation)+'\n');
     const ack=await this.receive();if(!ack.ok)throw new Error(ack.error);
     this.cursor.commit(record);this.observations.push({...observation,delivery_key:ack.delivery_key});
    }
    await new Promise(r=>setTimeout(r,100));
   }
  }catch(error){if(!this.stopping){this.error=error;this.status='failed';this.log('bridge_failed',{error:error.message});}}
 }
 async setBayDistance(spot,cm){
  const part=this.page.locator('#ultrasonic'+(spot-1000));await part.click();await this.page.waitForTimeout(100);const slider=this.page.locator('input[type=range]');
  if(!await slider.count()){await part.click();await this.page.waitForTimeout(100);}
  const action={spot_id:spot,distance_cm:cm,wall_start:Date.now(),monotonic_start:performance.now()};
  await slider.evaluate((el,v)=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,String(v));el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));},cm);
  this.actions.push(action);this.log('virtual_distance_changed',action);return action;
 }
 pause(ids){const file=path.join(this.output,'control.json');fs.writeFileSync(file+'.tmp',JSON.stringify({paused_ids:ids}));fs.renameSync(file+'.tmp',file);this.log('forwarding_fault_injection',{paused_ids:ids});}
 async toggleEchoFault(spot){await this.page.locator('#fault'+(spot-1000)).click();this.log('virtual_echo_switch_toggled',{spot_id:spot,at:Date.now()});}
}
module.exports={MultiBridge};
