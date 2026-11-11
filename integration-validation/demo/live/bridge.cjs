const fs=require('node:fs');const path=require('node:path');const readline=require('node:readline');
const {spawn}=require('node:child_process');
const {chromium}=require('../browser/node_modules/playwright');
const pythonDefault='python';
class SerialCursor{
 constructor(){this.seen=[];}
 extract(body){
  const rendered=body.split(/\r?\n/);
  const lines=[];
  for(let i=0;i<rendered.length;i++){
   const line=rendered[i];if(!line.startsWith('{"spot_id"'))continue;
   if(!line.endsWith('}')){
    if(rendered.slice(i+1).some(next=>next.startsWith('[SENSOR]')))
     throw new Error('Malformed completed Serial frame; refusing to drop a sensor event');
    continue; // UART text can render in fragments. Wait for the closing brace before forwarding.
   }
   lines.push(line);
  }
  if(lines.length<this.seen.length||this.seen.some((line,i)=>lines[i]!==line))
   throw new Error('Wokwi Serial reset/truncated: stop and start a NEW stream; refusing silent replay');
  return lines.slice(this.seen.length).map((raw,i)=>({raw,serial_index:this.seen.length+i}));
 }
 commit(record){
  if(record.serial_index!==this.seen.length)throw new Error('Out-of-order bridge commit');
  this.seen.push(record.raw);
 }
}
class LiveBridge{
 constructor({mqttPort,output,headed=false,python=process.env.PARKING_PYTHON||pythonDefault,firmwareDirectory=null,workerScript=null,workerExtraArgs=[],captureTrace=false}){
  Object.assign(this,{mqttPort,output,headed,python});this.cursor=new SerialCursor();this.queue=[];this.lines=[];
  this.stopping=false;this.observations=[];this.status='starting';this.busy=false;
  this.lastDiagnostic=null;this.lastDiagnosticWall=Date.now();this.lastHealthWall=0;
  Object.assign(this,{firmwareDirectory,workerScript,workerExtraArgs,captureTrace});
  fs.mkdirSync(output,{recursive:true});
 }
 log(event,fields={}){fs.appendFileSync(path.join(this.output,'bridge.jsonl'),JSON.stringify({at:new Date().toISOString(),event,...fields})+'\n');}
 receive(){return this.lines.length?Promise.resolve(this.lines.shift()):new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>reject(new Error('Live MQTT worker timeout')),40000);
  this.queue.push(value=>{clearTimeout(timer);resolve(value);});
 });}
 async start(){
  this.worker=spawn(this.python,[this.workerScript||path.join(__dirname,'mqtt_worker.py'),'--mqtt-port',String(this.mqttPort),'--journal',path.join(this.output,'publisher.jsonl'),...this.workerExtraArgs],{windowsHide:true});
  this.worker.stderr.on('data',chunk=>fs.appendFileSync(path.join(this.output,'worker-errors.txt'),chunk));
  readline.createInterface({input:this.worker.stdout}).on('line',line=>{
   const value=JSON.parse(line);if(this.queue.length)this.queue.shift()(value);else this.lines.push(value);
  });
  const ready=await this.receive();if(!ready.ready)throw new Error('Worker not ready');
  this.browser=await chromium.launch({channel:'msedge',headless:!this.headed});
  this.context=await this.browser.newContext({viewport:{width:1500,height:1000}});
  if(this.captureTrace)await this.context.tracing.start({screenshots:true,snapshots:true,sources:true});
  this.page=await this.context.newPage();
  await this.page.goto('https://wokwi.com/projects/new/esp32',{waitUntil:'domcontentloaded',timeout:45000});
  await this.page.waitForFunction(()=>window.monaco?.editor.getModels().some(m=>String(m.uri)==='vfs:sketch.ino'));
  const firmware=this.firmwareDirectory||path.join(__dirname,'../sensor-wokwi/firmware');
  for(const name of ['sketch.ino','diagram.json']){
   if(name==='diagram.json')await this.page.getByText(name,{exact:true}).click();
   await this.page.waitForFunction(name=>window.monaco.editor.getModels().some(m=>String(m.uri)==='vfs:'+name),name);
   const source=fs.readFileSync(path.join(firmware,name),'utf8');
   fs.writeFileSync(path.join(this.output,name),source);
   await this.page.evaluate(({name,source})=>window.monaco.editor.getModels().find(m=>String(m.uri)==='vfs:'+name).setValue(source),{name,source});
  }
  await this.page.getByText('sketch.ino',{exact:true}).click();await this.page.waitForTimeout(750);
  await this.page.getByRole('button',{name:'Start the simulation',exact:true}).click();
  this.status='waiting_for_wokwi_build';
  const deadline=Date.now()+600000;let lastNotice=0;
  while(Date.now()<deadline){
   if(this.stopping||fs.existsSync(path.join(this.output,'stop.request')))throw new Error('Live bridge stopped during Wokwi startup');
   const body=await this.page.locator('body').innerText();
   if(/^\[SENSOR\]/m.test(body)){this.status='streaming';break;}
   if(body.includes('Compilation error'))throw new Error('Wokwi compilation failed');
   if(Date.now()-lastNotice>30000){console.log('LIVE bridge waiting for Wokwi build; no replay input');lastNotice=Date.now();}
   await this.page.waitForTimeout(1000);
  }
  if(this.status!=='streaming')throw new Error('Wokwi build/simulation timeout');
  this.log('live_source_ready',{mode:'LIVE_WOKWI_SERIAL',replay:false});
  this.loop=this.pump();
 }
 async pump(){
  try{
   while(!this.stopping){
    const body=await this.page.locator('body').innerText();
    const diagnostic=body.split(/\r?\n/).filter(line=>line.startsWith('[SENSOR]')).at(-1);
    if(diagnostic!==this.lastDiagnostic){this.lastDiagnostic=diagnostic;this.lastDiagnosticWall=Date.now();}
    const health=Date.now()-this.lastDiagnosticWall>5000?'source_stalled':
        diagnostic?.includes('trusted=1')?'streaming':'sensor_untrusted';
    if(Date.now()-this.lastHealthWall>2000||health!==this.lastHealth){
     this.worker.stdin.write(JSON.stringify({kind:'health',state:health})+'\n');
     const ack=await this.receive();if(!ack.ok)throw new Error(ack.error);
     this.lastHealth=health;this.lastHealthWall=Date.now();
    }
    const pending=this.cursor.extract(body);
    if(pending.length>256)throw new Error('Live queue limit exceeded; refusing to drop sensor events');
    for(const record of pending){
     const observation={...record,observed_at:Date.now(),monotonic_observed_ms:performance.now()};
     this.log('observed_live_serial',observation);
     this.worker.stdin.write(JSON.stringify(observation)+'\n');
     const result=await this.receive();if(!result.ok)throw new Error(result.error);
     this.cursor.commit(record);this.observations.push(observation);
    }
    await new Promise(resolve=>setTimeout(resolve,100));
   }
  }catch(error){if(!this.stopping){this.error=error;this.status='failed';this.log('bridge_failed',{error:error.message});}}
 }
 async setDistance(cm){
  const slider=this.page.locator('input[type=range]');
  if(!await slider.count())await this.page.locator('wokwi-hc-sr04').click();
  await slider.evaluate((el,value)=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,String(value));el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));},cm);
  this.log('virtual_distance_changed',{distance_cm:cm,wall_time:Date.now()});
 }
 async stopSource(){
  this.stopping=true;
  if(this.loop)await this.loop;
  if(this.worker){this.worker.stdin.end();await new Promise(resolve=>{if(this.worker.exitCode!==null)return resolve();this.worker.once('exit',resolve);});this.worker=null;}
 }
 async stop(){
  await this.stopSource();
  if(this.context){
   await this.page.screenshot({path:path.join(this.output,'final-wokwi.png'),fullPage:true}).catch(()=>{});
   if(this.captureTrace)await this.context.tracing.stop({path:path.join(this.output,'wokwi-trace.zip')}).catch(()=>{});
   await this.context.close();await this.browser.close();
  }
  this.status='stopped';
 }
}
module.exports={LiveBridge,SerialCursor};
