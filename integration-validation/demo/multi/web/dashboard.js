let latest=null,busy=false,lastAdmin=0;
const $=id=>document.getElementById(id);
const title=value=>value.charAt(0).toUpperCase()+value.slice(1);
function element(tag,text,className){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;}
function age(timestamp){if(!timestamp)return 'No message received';const seconds=Math.max(0,Math.floor((Date.now()-Date.parse(timestamp))/1000));return seconds<2?'Just now':seconds<60?`${seconds}s ago`:`${Math.floor(seconds/60)}m ago`;}
function validate(data){
 if(data.mode!=='MULTI_WOKWI_REFERENCE'||!Array.isArray(data.spaces)||data.spaces.length!==3||typeof data.broker_connected!=='boolean')throw new Error('Invalid multi-bay API');
 data.spaces.forEach((s,i)=>{if(s.spot_id!==1001+i||s.id!==['A01','A02','A03'][i]||!['available','occupied','unknown'].includes(s.status)||typeof s.online!=='boolean'||
  (s.status!=='unknown'&&(!s.online||!s.has_persisted_data))||(s.has_persisted_data&&(!Number.isInteger(s.ctr)||typeof s.occupied!=='boolean')))throw new Error('Invalid bay observation');});
}
function render(data,unavailable=false,timing={}){
 const renderStarted=performance.now();
 const counts={available:0,occupied:0,unknown:0};$('parkingGrid').replaceChildren();$('adminTableBody').replaceChildren();
 data.spaces.forEach(s=>{
  counts[s.status]++;const card=element('article',undefined,'parking-card '+s.status);card.dataset.bay=s.id;
  const heading=element('div',undefined,'card-heading');heading.append(element('h3',s.id),element('span',title(s.status),'status-badge'));card.append(heading);
  card.append(element('div',s.status==='occupied'?'▰':s.status==='available'?'P':'—','space-symbol'));
  const health=element('div',undefined,'bay-health');const indicator=element('span');indicator.append(element('i',undefined,'health-dot '+(s.online?'online':'')),document.createTextNode(s.online?'Sensor online':s.has_persisted_data?'Updates unavailable':'Waiting for sensor'));
  health.append(indicator,element('span',age(s.received_at)));card.append(health);
  const details=element('div',undefined,'card-details');details.append(element('div',s.source_type||'No connected source'));
  details.append(element('div',s.has_persisted_data?`Last message: ${s.heartbeat?'Sensor check-in':'Status update'}`:'No source observation yet'));
  if(s.received_at){const time=element('time',new Date(s.received_at).toLocaleTimeString('en-AU'));time.dateTime=s.received_at;details.append(element('span','Received '),time);}
  card.append(details);
  if(s.status==='unknown'&&s.last_known_status!=='unknown')card.append(element('p','Last known: '+title(s.last_known_status),'last-known'));
  $('parkingGrid').append(card);
  const row=element('tr');row.dataset.bay=s.id;
  [s.id+' / '+s.spot_id,title(s.status),title(s.last_known_status),s.online?'Online':s.health,
   s.source_type+(s.distance_mm!==null?` · ${s.distance_mm} mm`:''),s.has_persisted_data?`ctr ${s.ctr} · ${s.heartbeat?'heartbeat':'transition'} · status ${s.status_bits} · ${s.batt_mv} mV`:'No message',
   s.received_at||'No data',String(s.pending||0)].forEach(v=>row.append(element('td',v)));$('adminTableBody').append(row);
 });
 for(const [key,value] of Object.entries(counts))$(key+'Count').textContent=value;
 const online=data.spaces.filter(s=>s.online).length;$('systemHealth').textContent=unavailable?'Service unavailable':`${online}/3 sensors online`;$('systemHealth').className='system-health '+(online===3?'online':'');
 $('lastSync').textContent=unavailable?'Updates unavailable':'Updated '+new Date().toLocaleTimeString('en-AU');
 $('connectionNotice').hidden=!unavailable&&data.broker_connected;
 $('connectionNotice').textContent=unavailable?'The parking service is unavailable. Last-known observations are shown in bay details.':'Sensor updates are temporarily interrupted. Last-known observations are shown in bay details.';
 $('brokerStatus').textContent='Broker: '+(data.broker_connected?'connected':'disconnected');$('sessionLabel').textContent='Session '+data.session;
 $('footerHealth').textContent=unavailable?'Connection unavailable':`${data.accepted} committed sensor messages`;
 window.dispatchEvent(new CustomEvent('parking:render',{detail:{...timing,render_duration_ms:performance.now()-renderStarted,wall_ms:performance.timeOrigin+performance.now(),unavailable,spaces:data.spaces.map(s=>({spot_id:s.spot_id,event_id:s.event_id,status:s.status,received_at:s.received_at}))}}));
}
async function admin(){
 try{
  const filter=$('historyFilter').value;const query=filter?'?spot_id='+filter:'';
  const response=await fetch('/api/events'+query,{cache:'no-store',signal:AbortSignal.timeout(3000)});if(!response.ok)throw new Error('History unavailable');
  const data=await response.json();$('historyBody').replaceChildren();
  for(const e of data.records.slice().reverse()){
   const row=element('tr');[e.id,e.bay,e.occupied?'Occupied':'Available',e.heartbeat?'Heartbeat':'State change',e.ctr,`${e.status} / ${e.batt_mv} mV`,e.received_at].forEach(v=>row.append(element('td',v)));$('historyBody').append(row);
  }
  $('historyStatus').textContent=`Showing ${data.records.length} committed events (up to 50).`;
  const audit=await (await fetch('/api/receipts',{cache:'no-store'})).json();$('receiptLog').textContent=JSON.stringify(audit.records.filter(r=>r.outcome!=='accepted').map(r=>({bay:r.bay,outcome:r.outcome,reason:r.reason,received_at:r.received_at})),null,2);
 }catch(e){$('historyStatus').textContent='Message history unavailable. Retry when the service recovers.';}
}
document.querySelectorAll('.tab').forEach(tab=>tab.addEventListener('click',()=>{
 document.querySelectorAll('.tab').forEach(t=>{t.classList.toggle('active',t===tab);t.setAttribute('aria-selected',String(t===tab));});
 document.querySelectorAll('.page').forEach(p=>p.classList.toggle('active',p.id===tab.dataset.page));if(tab.dataset.page==='admin')admin();
}));$('historyFilter').addEventListener('change',admin);
async function poll(){if(busy)return;busy=true;
 try{const poll_started_wall_ms=performance.timeOrigin+performance.now();const r=await fetch('/api/availability',{cache:'no-store',signal:AbortSignal.timeout(3000)});if(!r.ok)throw new Error('Unavailable');const data=await r.json();const parsed_wall_ms=performance.timeOrigin+performance.now();validate(data);latest=data;render(data,false,{poll_started_wall_ms,api_fetch_parse_ms:parsed_wall_ms-poll_started_wall_ms});
  if($('admin').classList.contains('active')&&Date.now()-lastAdmin>1500){lastAdmin=Date.now();await admin();}
 }catch(e){const data=latest||{mode:'MULTI_WOKWI_REFERENCE',session:'—',accepted:0,broker_connected:false,spaces:['A01','A02','A03'].map((id,i)=>({id,spot_id:1001+i,has_persisted_data:false,last_known_status:'unknown',source_type:'No connected source',received_at:null,distance_mm:null}))};
  render({...data,broker_connected:false,spaces:data.spaces.map(s=>({...s,status:'unknown',online:false,health:'backend_unavailable'}))},true);
 }finally{busy=false;}}
// A bounded 200 ms poll reduces display quantization without changing sensor confirmation.
// The 500 ms option permits a like-for-like comparison with the preserved previous cadence.
const pollInterval=new URLSearchParams(location.search).get('poll_ms')==='500'?500:200;
poll();setInterval(poll,pollInterval);
