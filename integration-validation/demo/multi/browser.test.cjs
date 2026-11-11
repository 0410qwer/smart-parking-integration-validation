const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');
const {spawn}=require('node:child_process');const readline=require('node:readline');const {MultiBridge}=require('./bridge.cjs');
const output=process.env.MULTI_BROWSER_OUTPUT;
const python=process.env.PARKING_PYTHON||'python';
test('three real virtual sensors, professional UI, independent faults, durable transport and recovery',{timeout:800000},async()=>{
 const fixture=spawn(python,[path.join(__dirname,'browser_fixture.py')],{env:{...process.env,MQTT_TEST_EVIDENCE:output},windowsHide:true});
 let queue=[],lines=[],bridge,ui,viewer;const proof={source_type:'three Wokwi HC-SR04 instances on one simulated ESP32',physical_accuracy:false,cases:[],latency:[]};
 fixture.stderr.on('data',chunk=>fs.appendFileSync(path.join(output,'fixture.txt'),chunk));
 readline.createInterface({input:fixture.stdout}).on('line',line=>{fs.appendFileSync(path.join(output,'controller.jsonl'),line+'\n');const data=JSON.parse(line);if(queue.length)queue.shift()(data);else lines.push(data);});
 function receive(){return lines.length?Promise.resolve(lines.shift()):new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('Fixture timeout')),20000);queue.push(v=>{clearTimeout(timer);resolve(v);});});}
 async function command(action){fixture.stdin.write(JSON.stringify({action})+'\n');const r=await receive();assert.equal(r.ok,true,r.error);return r;}
 const ready=await receive();assert.ok(ready.ready);const base=ready.url;
 const state=async()=> (await fetch(base+'/api/availability')).json();
 async function wait(predicate,timeout=20000){const end=Date.now()+timeout;while(Date.now()<end){if(bridge?.error)throw bridge.error;const data=await state();if(await predicate(data))return data;await new Promise(r=>setTimeout(r,100));}throw new Error('Multi-bay expectation timed out');}
 async function displayed(spot,status){await ui.waitForFunction(({spot,status})=>document.querySelector(`[data-bay="A0${spot-1000}"] .status-badge`)?.textContent.toLowerCase()===status,{spot,status});}
 async function change(spot,cm,expected,phase='normal'){
  const action=await bridge.setBayDistance(spot,cm);return {action,expected,phase};
 }
 async function confirm(trial){const {spot_id:spot,distance_cm:cm}=trial.action;
  const data=await wait(d=>d.spaces.find(s=>s.spot_id===spot).status===trial.expected);await displayed(spot,trial.expected);
  const value=data.spaces.find(s=>s.spot_id===spot);const metric={spot_id:spot,distance_cm:cm,expected:trial.expected,observed:value.status,
   start:'immediately before browser sets the virtual distance control',end:'Dashboard DOM shows expected new state',
   control_wall_at:trial.action.wall_start,elapsed_wall_ms:performance.now()-trial.action.monotonic_start,phase:trial.phase,
   received_at:value.received_at,ctr:value.ctr,distance_mm:value.distance_mm};proof.latency.push(metric);proof.cases.push(metric);
 }
 try{
  bridge=new MultiBridge({mqttPort:ready.mqtt_port,session:'browser-multi',output:path.join(output,'bridge'),captureTrace:false});
  // Check a genuinely unsourced UI before any simulator is started.
  const {chromium}=require('../browser/node_modules/playwright');viewer=await chromium.launch({channel:'msedge',headless:true});
  ui=await viewer.newPage({viewport:{width:1280,height:900}});await ui.goto(base+'/backend/');
  await ui.waitForFunction(()=>document.getElementById('unknownCount').textContent==='3');
  proof.unsourced_unknown=true;
  await bridge.start();
  let data=await wait(d=>d.spaces.every(s=>s.online));
  assert.deepEqual(data.spaces.map(s=>s.status),['available','occupied','available']);
  for(const s of data.spaces){await displayed(s.spot_id,s.status);proof.cases.push({spot_id:s.spot_id,phase:'initial known virtual input',expected:s.status,observed:s.status});}
  await ui.screenshot({path:path.join(output,'overview-desktop.png'),fullPage:true});
  await confirm(await change(1001,10,'occupied'));
  const second=await change(1002,35,'available');const third=await change(1003,9,'occupied');await Promise.all([confirm(second),confirm(third)]);
  assert.deepEqual((await state()).spaces.map(s=>s.status),['occupied','available','occupied']);
  await ui.screenshot({path:path.join(output,'concurrent-updates.png'),fullPage:true});
  await bridge.setBayDistance(1003,17);await new Promise(r=>setTimeout(r,3000));await displayed(1003,'occupied');
  proof.cases.push({spot_id:1003,phase:'hysteresis',distance_cm:17,expected:'occupied',observed:(await state()).spaces[2].status});
  // This is an actual virtual ECHO disconnection, not a fabricated health flag.
  await bridge.toggleEchoFault(1002);data=await wait(d=>d.spaces[1].health==='untrusted'&&d.spaces[1].status==='unknown');
  await displayed(1002,'unknown');assert.equal(data.spaces[1].last_known_status,'available');assert.ok(data.spaces[0].online&&data.spaces[2].online);
  proof.echo_fault={state:data.spaces[1],diagnostic:bridge.diagnostics['1002']};
  await ui.screenshot({path:path.join(output,'independent-sensor-fault.png'),fullPage:true});
  await bridge.toggleEchoFault(1002);await wait(d=>d.spaces[1].online);await displayed(1002,'available');
  // Pause delivery on only A02; backlog must not block the other source channels.
  bridge.pause([1002]);await wait(d=>d.spaces[1].health==='offline');await new Promise(r=>setTimeout(r,5500));
  assert.ok((await state()).spaces[0].online&&(await state()).spaces[2].online);bridge.pause([]);await wait(d=>d.spaces.every(s=>s.online));
  const beforeRestart=await command('inspect');await command('backend_restart');await wait(d=>d.spaces.every(s=>s.online));
  const afterRestart=await command('inspect');assert.deepEqual(afterRestart.disk.events.slice(0,beforeRestart.disk.events.length),beforeRestart.disk.events);
  await command('broker_down');await wait(d=>d.spaces.every(s=>s.status==='unknown'));await displayed(1001,'unknown');
  const recovery1=await change(1001,35,'available','broker outage included');const recovery3=await change(1003,35,'available','broker outage included');
  await new Promise(r=>setTimeout(r,6500));await command('broker_up');await wait(d=>d.spaces.every(s=>s.online),30000);await confirm(recovery1);await confirm(recovery3);
  const result=await command('inspect');proof.database=result.disk;assert.equal(result.disk.integrity,'ok');
  for(const row of result.disk.events){
   // Canonical key order differs; compare parsed source values instead.
   assert.ok(bridge.observations.some(o=>Object.entries(JSON.parse(o.raw)).every(([k,v])=>JSON.parse(row.payload_json)[k]===v)));
  }
  await ui.getByRole('button',{name:'Admin View',exact:true}).click();await ui.waitForFunction(()=>document.querySelectorAll('#historyBody tr').length>0);
  await ui.locator('#historyFilter').selectOption('1002');await ui.waitForFunction(()=>[...document.querySelectorAll('#historyBody tr')].every(r=>r.children[1].textContent==='A02'));
  assert.match(await ui.locator('#adminTableBody').textContent(),/1001/);await ui.screenshot({path:path.join(output,'admin-diagnostics.png'),fullPage:true});
  await ui.getByRole('button',{name:'Overview',exact:true}).click();await ui.setViewportSize({width:390,height:844});
  assert.equal(await ui.locator('.parking-grid').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length),1);
  assert.ok(await ui.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await ui.screenshot({path:path.join(output,'overview-mobile.png'),fullPage:true});
  // Backend HTTP failure must not show stale Available as current.
  await ui.route('**/api/availability',r=>r.abort());await ui.waitForFunction(()=>document.getElementById('unknownCount').textContent==='3');
  await ui.unroute('**/api/availability');await ui.waitForFunction(()=>document.getElementById('availableCount').textContent==='3');
  proof.correctness={matched:proof.cases.filter(c=>c.expected===c.observed).length,total:proof.cases.length,basis:'known virtual inputs only; not physical accuracy'};
  assert.equal(proof.correctness.matched,proof.correctness.total);proof.passed=true;
  fs.writeFileSync(path.join(output,'proof.json'),JSON.stringify(proof,null,2));await viewer.close();
 }finally{
  if(viewer)await viewer.close();if(bridge)await bridge.stop();fixture.stdin.end('{"action":"stop"}\n');await new Promise(resolve=>fixture.once('exit',resolve));
  if(!proof.passed)fs.writeFileSync(path.join(output,'partial-proof.json'),JSON.stringify(proof,null,2));
 }
});
