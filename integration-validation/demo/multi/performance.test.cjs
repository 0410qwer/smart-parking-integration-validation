const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');
const {spawn}=require('node:child_process');const readline=require('node:readline');const {MultiBridge}=require('./bridge.cjs');
const {chromium}=require('../browser/node_modules/playwright');const output=process.env.MULTI_BROWSER_OUTPUT;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));const read=file=>fs.existsSync(file)?fs.readFileSync(file,'utf8').trim().split('\n').filter(Boolean).map(JSON.parse):[];
test('controlled occupied/free timings and extended three-source stability in real Edge',{timeout:1700000},async()=>{
 const fixture=spawn(process.env.PARKING_PYTHON,[path.join(__dirname,'browser_fixture.py')],{env:{...process.env,MQTT_TEST_EVIDENCE:output},windowsHide:true});
 fixture.stderr.on('data',b=>fs.appendFileSync(path.join(output,'fixture.txt'),b));let queued=[],lines=[],bridge,browser,ui;
 readline.createInterface({input:fixture.stdout}).on('line',line=>{const r=JSON.parse(line);if(queued.length)queued.shift()(r);else lines.push(r);});
 const receive=()=>lines.length?Promise.resolve(lines.shift()):new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Fixture timeout')),30000);queued.push(r=>{clearTimeout(timer);resolve(r);});});
 async function command(action,extra={}){fixture.stdin.write(JSON.stringify({action,...extra})+'\n');const r=await receive();assert.ok(r.ok,r.error);return r;}
 const trials=[],metrics=[],started=Date.now();let ready,mon;
 const save=()=>fs.writeFileSync(path.join(output,'trials.json'),JSON.stringify(trials,null,2));
 try{
  ready=await receive();bridge=new MultiBridge({mqttPort:ready.mqtt_port,session:'browser-multi',output:path.join(output,'bridge')});await bridge.start();
  browser=await chromium.launch({channel:'msedge',headless:true});ui=await browser.newPage({viewport:{width:1280,height:900}});
  await ui.addInitScript(()=>{window.__renders=[];window.addEventListener('parking:render',e=>{window.__renders.push(e.detail);if(window.__renders.length>3000)window.__renders.shift();});});
  const state=async()=> (await fetch(ready.url+'/api/availability')).json();
  async function wait(predicate,timeout=30000){const end=Date.now()+timeout;while(Date.now()<end){if(bridge.error)throw bridge.error;const s=await state();if(predicate(s))return s;await sleep(50);}throw Error('State timeout');}
  await wait(s=>s.spaces.every(b=>b.online));
  const sample=async()=>{const r=await command('metrics',{pids:{runner:process.pid,serial_worker:bridge.worker.pid}});r.runner_memory=process.memoryUsage();metrics.push(r);fs.writeFileSync(path.join(output,'resource-samples.json'),JSON.stringify(metrics,null,2));};
  await sample();let sampling=false;mon=setInterval(async()=>{if(sampling)return;sampling=true;try{await sample();}catch(e){metrics.push({error:e.message});}finally{sampling=false;}},15000);
  // Bring all sources to the same known free baseline through actual virtual controls.
  await bridge.setBayDistance(1002,35);await wait(s=>s.spaces.every(b=>b.status==='available'));
  for(const [poll,rounds] of [[500,3],[200,Number(process.env.PERF_ROUNDS||10)]]){
   await ui.goto(ready.url+'/backend/?poll_ms='+poll);await ui.waitForFunction(()=>document.querySelectorAll('.parking-card.available').length===3);
   for(let round=0;round<rounds;round++)for(const [cm,expected] of [[10,'occupied'],[35,'available']]){
    const batch=[];
    for(const spot of [1001,1002,1003]){
     const action=await bridge.setBayDistance(spot,cm);batch.push({spot_id:spot,expected,poll_ms:poll,round,control_wall_ms:action.wall_start});
    }
    await Promise.all(batch.map(async t=>{
     try{
      const end=Date.now()+15000;let observation,render,timing;
      while(Date.now()<end){
       if(bridge.error)throw bridge.error;
       observation=bridge.observations.find(o=>{const p=JSON.parse(o.raw);return o.observed_at>=t.control_wall_ms&&p.spot_id===t.spot_id&&!p.heartbeat&&p.occupied===(expected==='occupied');});
       if(observation){timing=read(path.join(output,'backend.jsonl')).find(r=>r.event==='multi_delivery_timing'&&r.delivery_key===observation.delivery_key&&r.outcome==='accepted');
        if(timing)render=await ui.evaluate(({spot,id,status})=>window.__renders.find(r=>!r.unavailable&&r.spaces.some(s=>s.spot_id===spot&&s.event_id===id&&s.status===status)),{spot:t.spot_id,id:timing.event_id,status:expected});
       }
       if(render)break;await sleep(30);
      }
      if(!render)throw Error('No matching transition event and Dashboard render within 15 seconds');
      const delivery=read(path.join(output,'bridge/delivery.jsonl')).find(r=>r.event==='mqtt_publish_started'&&r.delivery_key===observation.delivery_key);
      const first=read(path.join(output,'bridge/bridge.jsonl')).find(r=>r.event==='sensor_distance_observed'&&r.spot_id===t.spot_id&&r.observed_wall_ms>=t.control_wall_ms&&Math.abs(r.distance_mm-cm*10)<10);
      Object.assign(t,{success:true,delivery_key:observation.delivery_key,event_id:timing.event_id,serial_wall_ms:observation.observed_at,render_wall_ms:render.wall_ms,
       control_to_dom_ms:render.wall_ms-t.control_wall_ms,observed_confirmed_serial_to_dom_ms:render.wall_ms-observation.observed_at,
       control_to_serial_ms:observation.observed_at-t.control_wall_ms,publish_to_receive_ms:timing.subscriber_received_wall_ms-delivery.publish_wall_ms,
       validation_transaction_ms:timing.validation_transaction_ms,commit_to_dom_ms:render.wall_ms-timing.commit_finished_wall_ms,
       api_fetch_parse_ms:render.api_fetch_parse_ms??null,dom_build_ms:render.render_duration_ms??null,
       commit_to_poll_start_ms:render.poll_started_wall_ms!==undefined?render.poll_started_wall_ms-timing.commit_finished_wall_ms:null,
       simulated_confirmation_ms:first&&observation.firmware_confirmed_sim_ms!==null?observation.firmware_confirmed_sim_ms-first.sim_t_ms:null});
     }catch(e){t.success=false;t.error=e.message;}
     trials.push(t);save();
    }));
    console.log(`cadence=${poll} round=${round+1} ${expected}: ${batch.filter(t=>t.success).length}/3`);
    await wait(s=>s.spaces.every(b=>b.status===expected));
   }
  }
  // Recovery during the same long-lived source session, never a saved capture input.
  clearInterval(mon);mon=null;await command('broker_down');await wait(s=>s.spaces.every(b=>b.status==='unknown'));
  for(const spot of [1001,1002,1003])await bridge.setBayDistance(spot,10);await sleep(5000);
  await command('broker_up');await wait(s=>s.spaces.every(b=>b.status==='occupied'),40000);
  await command('backend_restart');await wait(s=>s.spaces.every(b=>b.online),20000);
  const soakStarted=Date.now();let tick=0;
  while(Date.now()-soakStarted<Number(process.env.PERF_SOAK||180)*1000){
   const spot=1001+(tick%3);const occupied=Math.floor(tick/3)%2===0;
   await bridge.setBayDistance(spot,occupied?35:10);await sleep(4000);await sample();tick++;
  }
  await ui.screenshot({path:path.join(output,'stability-dashboard.png'),fullPage:true});
  // Stop only the source, drain already confirmed frames, then compare each observed key.
  await bridge.page.getByRole('button',{name:'Stop the simulation',exact:true}).click();await sleep(1500);
  const disk=(await command('inspect')).disk;const deliveries=read(path.join(output,'backend.jsonl')).filter(r=>r.event==='multi_delivery_timing'&&r.outcome==='accepted');
  const keys=new Set(deliveries.map(r=>r.delivery_key));const missing=bridge.observations.filter(o=>!keys.has(o.delivery_key));
  assert.equal(missing.length,0,'Confirmed observed live events must all have committed delivery keys');assert.equal(disk.events.length,keys.size);assert.equal(disk.integrity,'ok');
  assert.ok(metrics.every(r=>!r.error&&r.process_alive.backend&&r.process_alive.broker));assert.equal(trials.filter(t=>!t.success).length,0);
  const stability={passed:true,duration_seconds:(Date.now()-started)/1000,soak_seconds:(Date.now()-soakStarted)/1000,
   observed_live_serial_events:bridge.observations.length,committed_distinct_keys:keys.size,missing_observed_events:missing.length,
   sqlite_events:disk.events.length,heartbeat_events:disk.events.filter(e=>e.heartbeat).length,integrity:disk.integrity,
   retries:read(path.join(output,'bridge/delivery.jsonl')).filter(r=>r.event==='retry_pending').length,
   scope:'One bounded local virtual-sensor run, not an hours/days endurance claim; RSS excludes Edge child tree.',browser:browser.version()};
  fs.writeFileSync(path.join(output,'stability.json'),JSON.stringify(stability,null,2));console.log(JSON.stringify(stability));
 }finally{
  if(mon)clearInterval(mon);save();if(browser)await browser.close();if(bridge)await bridge.stop();
  if(fixture.exitCode===null){fixture.stdin.end('{"action":"stop"}\n');await new Promise(resolve=>fixture.once('exit',resolve));}
 }
});
