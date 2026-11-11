// One real-browser integration test, observed from the running simulator, not a capture.
const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const {LiveBridge}=require('./bridge.cjs');
const output=process.env.LIVE_TEST_OUTPUT||path.resolve(__dirname,'../evidence','live-e2e-'+new Date().toISOString().replace(/[:.]/g,'-'));
fs.mkdirSync(output,{recursive:true});
const base=process.env.LIVE_TEST_URL||'http://127.0.0.1:8770';
test('live Wokwi distance changes cross Serial MQTT SQLite API and Dashboard without capture replay',async()=>{
 const bridge=new LiveBridge({mqttPort:Number(process.env.LIVE_MQTT_PORT||18886),output,captureTrace:true});
 const proof={input_mode:'LIVE_WOKWI_SERIAL_BRIDGE',saved_capture_input:false,states:[],metrics:[]};
 try{
  await bridge.start();const ui=await bridge.context.newPage();await ui.goto(base+'/backend/');
  const observe=async(occupied,after)=>{
   const deadline=Date.now()+30000;let state;
   while(Date.now()<deadline){
    if(bridge.error)throw bridge.error;
    state=await (await fetch(base+'/api/availability')).json();
    if(state.accepted>after&&state.spaces[0].occupied===occupied&&state.spaces[0].fresh_this_connection)break;
    await new Promise(r=>setTimeout(r,100));
   }
   assert.ok(state.accepted>after&&state.spaces[0].occupied===occupied,'Expected new database-backed observation');
   await ui.waitForFunction(occupied=>document.querySelector('.parking-card .status-badge')?.textContent===(occupied?'Occupied':'Available'),occupied);
   assert.equal(await ui.locator('#unknownCount').textContent(),'2');
   assert.equal(state.input_mode,'LIVE_WOKWI_SERIAL_BRIDGE');assert.equal(state.replay,false);
   assert.ok(state.spaces[0].fresh_this_connection);
   const history=await (await fetch(base+'/api/events')).json();
   const last=history.records.at(-1);const observed=bridge.observations.find(o=>o.serial_index===last.ordinal-1);
   assert.ok(observed);assert.deepEqual(last.payload,JSON.parse(observed.raw));
   assert.equal(last.raw_payload_hex,Buffer.from(observed.raw).toString('hex'));
   proof.states.push({api:state,event:last});
   proof.metrics.push({metric:'browser_live_serial_observation_to_dashboard_wall_ms',value:performance.now()-observed.monotonic_observed_ms,ctr:last.ctr});
   await ui.getByRole('button',{name:'Admin View',exact:true}).click();
   assert.match(await ui.locator('#adminTableBody tr').first().textContent(),/A01 \/ 1001/);
   await ui.screenshot({path:path.join(output,`dashboard-event-${last.id}.png`),fullPage:true});
   await ui.getByRole('button',{name:'Parking Dashboard',exact:true}).click();
   return state.accepted;
  };
  let count=await observe(false,0);
  await bridge.setDistance(10);count=await observe(true,count);
  await bridge.page.screenshot({path:path.join(output,'live-occupied-wokwi.png'),fullPage:true});
  await bridge.setDistance(35);await observe(false,count);
  await bridge.stopSource();
  await ui.waitForFunction(()=>document.getElementById('liveHealth')?.textContent.includes('offline'));
  assert.equal(await ui.locator('.parking-card .status-badge').first().textContent(),'Available');
  proof.after_stop_health=await (await fetch(base+'/api/health')).json();
  assert.equal(proof.after_stop_health.bridge.state,'offline');
  assert.equal(proof.after_stop_health.sensors[0].fresh_this_connection,false);
  await ui.getByRole('button',{name:'Admin View',exact:true}).click();
  await ui.screenshot({path:path.join(output,'live-bridge-offline-last-known.png'),fullPage:true});
  proof.observed_events=bridge.observations.length;
  fs.writeFileSync(path.join(output,'proof.json'),JSON.stringify(proof,null,2));
  console.log('LIVE evidence: '+output);
 }finally{await bridge.stop();}
});
