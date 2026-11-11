const {test,before,after,beforeEach,afterEach}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const readline=require('node:readline');
const {spawn}=require('node:child_process');
const {chromium}=require('../browser/node_modules/playwright');
const output=process.env.BROWSER_EVIDENCE;
const python=process.env.PARKING_PYTHON || 'python';
const linesOfCapture=fs.readFileSync(path.join(__dirname,'../../captures/wokwi_serial_actual.txt'),'utf8').split(/\r?\n/).filter(l=>l.startsWith('{'));
const events=linesOfCapture.map(JSON.parse);
let browser,context,page,fixture,url,queue,lines,folder,errors;
before(async()=>{
    browser=await chromium.launch({channel:'msedge',headless:true});
    fs.writeFileSync(path.join(output,'environment.json'),JSON.stringify({browser:browser.version(),
        playwright:require('../browser/node_modules/playwright/package.json').version,node:process.version,python},null,2));
});
after(async()=>{if(browser)await browser.close();});
beforeEach(async t=>{
    folder=path.join(output,t.name.replace(/[^a-z0-9]+/gi,'-'));fs.mkdirSync(folder,{recursive:true});queue=[];lines=[];errors=[];
    fixture=spawn(python,[path.join(__dirname,'browser_fixture.py')],{env:{...process.env,BACKEND_TEST_EVIDENCE:folder,MQTT_TEST_EVIDENCE:folder}});
    fixture.stderr.on('data',chunk=>fs.appendFileSync(path.join(folder,'fixture-console.txt'),chunk));
    readline.createInterface({input:fixture.stdout}).on('line',line=>{
        fs.appendFileSync(path.join(folder,'controller.jsonl'),line+'\n');
        if(queue.length)queue.shift()(JSON.parse(line));else lines.push(JSON.parse(line));
    });
    const ready=await receive();assert.equal(ready.event,'ready');url=ready.url;
    context=await browser.newContext({viewport:{width:1280,height:900}});
    await context.tracing.start({screenshots:true,snapshots:true,sources:true});
    page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
    await page.goto(url+'/backend/');await committed(0);
});
afterEach(async()=>{
    if(page){
        await page.screenshot({path:path.join(folder,'final.png'),fullPage:true});
        fs.writeFileSync(path.join(folder,'ui.json'),JSON.stringify({status:await page.locator('#backendStatus').textContent(),
            cards:await page.locator('.parking-card').allTextContents(),admin:await page.locator('#adminTableBody tr').allTextContents(),errors},null,2));
        await context.tracing.stop({path:path.join(folder,'trace.zip')});await context.close();
    }
    if(fixture){fixture.stdin.end(JSON.stringify({action:'stop'})+'\n');await new Promise(resolve=>fixture.once('exit',resolve));}
    assert.deepEqual(errors,[]);
});
function receive(){return lines.length?Promise.resolve(lines.shift()):new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(new Error('Backend fixture timeout')),18000);
    queue.push(value=>{clearTimeout(timer);resolve(value);});
});}
async function command(value){fixture.stdin.write(JSON.stringify(value)+'\n');const result=await receive();assert.equal(result.ok,true,result.error);return result;}
async function committed(n){await page.waitForFunction(n=>document.getElementById('backendStatus').textContent.includes(`committed ${n};`),n);}
async function publish(index){const result=await command({action:'publish',index});await committed(index+1);return result;}

test('01 persistent mode initially Unknown with explicit reference label',async()=>{
    assert.match(await page.locator('.mode').textContent(),/SQLite reference backend/);
    assert.equal(await page.locator('#unknownCount').textContent(),'3');
    const result=await command({action:'inspect'});
    assert.equal(result.disk.events.length,0);assert.equal(result.disk.integrity,'ok');
    assert.ok(result.state.spaces.every(s=>s.occupied===null));
});

test('02 all 22 real MQTT messages equal database rows history API and UI',async()=>{
    for(let i=0;i<events.length;i++){
        const result=await publish(i);const event=events[i];
        assert.equal(result.disk.events.length,i+1);assert.equal(result.disk.current.length,1);
        const row=result.disk.events.at(-1);const api=result.history.records.at(-1);
        for(const key of ['spot_id','status','batt_mv','ctr'])assert.equal(row[key],event[key]);
        assert.equal(Boolean(row.occupied),event.occupied);assert.equal(Boolean(row.heartbeat),event.heartbeat);
        assert.equal(row.raw_payload,Buffer.from(linesOfCapture[i]).toString('hex'));
        assert.deepEqual(api.payload,event);assert.equal(row.id,api.id);assert.equal(row.source_timestamp,null);
        assert.equal(await page.locator('.parking-card').first().locator('.status-badge').textContent(),event.occupied?'Occupied':'Available');
        assert.equal(await page.locator('#unknownCount').textContent(),'2');
        await page.getByRole('button',{name:'Admin View',exact:true}).click();
        const cells=await page.locator('#adminTableBody tr').first().locator('td').allTextContents();
        assert.equal(cells[0],'A01 / 1001');assert.equal(cells[1],event.occupied?'occupied':'available');
        assert.match(cells[3],new RegExp(`DB event ${row.id}; ctr ${event.ctr}; ${event.heartbeat?'heartbeat':'transition'}; ${event.batt_mv} mV; status ${event.status}; received`));
        for(const n of [1,2])assert.match(await page.locator('#adminTableBody tr').nth(n).textContent(),/unknownNo persisted observation/);
        if([4,12,20,21].includes(i))await page.screenshot({path:path.join(folder,`event-${i+1}.png`),fullPage:true});
        await page.getByRole('button',{name:'Parking Dashboard',exact:true}).click();
    }
});

test('03 separate backend process restart preserves database UI history and dedup checkpoint',async()=>{
    let before;for(let i=0;i<5;i++)before=await publish(i);
    const after=await command({action:'restart'});await committed(5);
    assert.notEqual(before.backend_pid,after.backend_pid);
    assert.deepEqual(after.disk.events,before.disk.events);
    assert.deepEqual(after.history,before.history);
    assert.equal(after.state.spaces[0].fresh_this_connection,false);
    assert.equal(await page.locator('.parking-card').first().locator('.status-badge').textContent(),'Occupied');
    await page.waitForFunction(()=>document.getElementById('adminTableBody').textContent.includes('Persisted last-known; awaiting new receipt'));
    await page.getByRole('button',{name:'Admin View',exact:true}).click();
    await page.screenshot({path:path.join(folder,'after-process-restart.png'),fullPage:true});
    const duplicate=await command({action:'publish',index:4});assert.equal(duplicate.disk.events.length,5);
    assert.equal(duplicate.state.duplicates,1);
    const next=await publish(5);assert.equal(next.state.spaces[0].fresh_this_connection,true);
});

test('04 duplicate malformed gap and recovery keep history atomic',async()=>{
    await publish(0);await command({action:'publish',index:0});await command({action:'raw',raw:'{bad'});
    await command({action:'publish',index:2});const result=await command({action:'publish',index:1});await committed(2);
    assert.equal(result.disk.events.length,2);assert.equal(result.state.duplicates,1);assert.equal(result.state.rejected,2);
    assert.equal(result.disk.integrity,'ok');
    assert.match(await page.locator('#backendStatus').textContent(),/committed 2; duplicates 1; rejected 2/);
});

test('05 actual broker reconnect retains last-known state and reports freshness separately',async()=>{
    await publish(0);const disconnected=await command({action:'disconnect'});
    assert.equal(disconnected.health.broker_connected,false);assert.equal(disconnected.health.sensors[0].fresh_this_connection,false);
    await page.waitForFunction(()=>document.getElementById('backendStatus').textContent.includes('broker disconnected'));
    assert.equal(await page.locator('.parking-card').first().locator('.status-badge').textContent(),'Available');
    const connected=await command({action:'reconnect'});assert.equal(connected.state.spaces[0].fresh_this_connection,false);
    const next=await publish(1);assert.equal(next.health.sensors[0].fresh_this_connection,true);
});

test('06 HTTP and malformed response failures Unknown then recover persisted state',async()=>{
    await publish(0);
    for(const fault of ['abort','malformed']){
        await page.route('**/api/availability',route=>fault==='abort'?route.abort():route.fulfill({json:{mode:'SQLITE_REFERENCE_BACKEND',spaces:[]}}));
        await page.waitForFunction(()=>document.getElementById('backendStatus').textContent.includes('Backend/database unavailable'));
        assert.equal(await page.locator('#unknownCount').textContent(),'3');
        await page.unroute('**/api/availability');await committed(1);
        assert.equal(await page.locator('#unknownCount').textContent(),'2');
    }
    const result=await command({action:'inspect'});assert.equal(result.disk.events.length,1);
});

test('07 persisted backend APIs and fallback pages remain independent',async()=>{
    await publish(0);
    const health=await (await page.request.get(url+'/api/health')).json();assert.equal(health.physical_connectivity,'NOT_ASSESSED');
    const fallback=await context.newPage();await fallback.goto(url+'/');
    await fallback.waitForFunction(()=>document.getElementById('replayStatus').textContent.includes('Captured replay 0/22'));
    await fallback.locator('#step').click();await fallback.waitForFunction(()=>document.getElementById('replayStatus').textContent.includes('Captured replay 1/22'));
    await fallback.goto(url+'/simulation/');assert.equal(await fallback.locator('.mode').textContent(),'Simulation Mode');await fallback.close();
    const result=await command({action:'inspect'});assert.equal(result.disk.events.length,1);await committed(1);
});
