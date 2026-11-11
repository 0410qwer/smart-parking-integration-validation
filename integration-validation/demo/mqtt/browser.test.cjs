const {test,before,after,beforeEach,afterEach}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const readline=require('node:readline');
const {spawn}=require('node:child_process');
const {chromium}=require('../browser/node_modules/playwright');
const output=process.env.BROWSER_EVIDENCE;
const python=process.env.PARKING_PYTHON || 'python';
const events=fs.readFileSync(path.join(__dirname,'../../captures/wokwi_serial_actual.txt'),'utf8').split(/\r?\n/).filter(l=>l.startsWith('{')).map(JSON.parse);
let browser,context,page,fixture,url,queue,lines,folder,errors;
before(async()=>{
    browser=await chromium.launch({channel:'msedge',headless:true});
    fs.writeFileSync(path.join(output,'environment.json'),JSON.stringify({browser:browser.version(),
        playwright:require('../browser/node_modules/playwright/package.json').version,node:process.version,python},null,2));
});
after(async()=>{if(browser)await browser.close();});
beforeEach(async t=>{
    folder=path.join(output,t.name.replace(/[^a-z0-9]+/gi,'-'));
    fs.mkdirSync(folder,{recursive:true}); queue=[]; lines=[]; errors=[];
    fixture=spawn(python,[path.join(__dirname,'browser_fixture.py')],{env:{...process.env,MQTT_TEST_EVIDENCE:folder}});
    fixture.stderr.on('data',chunk=>fs.appendFileSync(path.join(folder,'fixture-console.txt'),chunk));
    readline.createInterface({input:fixture.stdout}).on('line',line=>{
        fs.appendFileSync(path.join(folder,'controller.jsonl'),line+'\n');
        if(queue.length) queue.shift()(JSON.parse(line)); else lines.push(JSON.parse(line));
    });
    const ready=await receive(); assert.equal(ready.event,'ready');url=ready.url;
    context=await browser.newContext({viewport:{width:1280,height:900}});
    await context.tracing.start({screenshots:true,snapshots:true,sources:true});
    page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
    await page.goto(url+'/mqtt/');await accepted(0);
});
afterEach(async()=>{
    if(page){
        await page.screenshot({path:path.join(folder,'final.png'),fullPage:true});
        fs.writeFileSync(path.join(folder,'ui.json'),JSON.stringify({status:await page.locator('#mqttStatus').textContent(),
            cards:await page.locator('.parking-card').allTextContents(),admin:await page.locator('#adminTableBody tr').allTextContents(),errors},null,2));
        await context.tracing.stop({path:path.join(folder,'trace.zip')});await context.close();
    }
    if(fixture){
        fixture.stdin.end(JSON.stringify({action:'stop'})+'\n');
        await new Promise(resolve=>fixture.once('exit',resolve));
    }
    assert.deepEqual(errors,[],'No uncaught browser errors');
});
function receive(){return lines.length?Promise.resolve(lines.shift()):new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(new Error('Fixture response timeout')),15000);
    queue.push(value=>{clearTimeout(timer);resolve(value);});
});}
async function command(value){fixture.stdin.write(JSON.stringify(value)+'\n');const result=await receive();assert.equal(result.ok,true,result.error);return result.state;}
async function accepted(n){await page.waitForFunction(n=>document.getElementById('mqttStatus').textContent.includes(`accepted ${n};`),n);}
async function connected(value){await page.waitForFunction(value=>document.getElementById('mqttStatus').textContent.includes(`subscriber ${value?'connected':'disconnected'};`),value);}
async function publish(index){await command({action:'publish',index});await accepted(index+1);}

test('01 MQTT mode starts Unknown with explicit received-data boundary',async()=>{
    assert.match(await page.locator('.mode').textContent(),/Local MQTT transport harness/);
    assert.equal(await page.locator('#unknownCount').textContent(),'3');
    assert.match(await page.locator('#adminTableBody tr').first().textContent(),/A01 \/ 1001unknownWaiting for MQTT data/);
    await connected(true);
    await page.waitForTimeout(1200);await accepted(0);
});

test('02 every actual MQTT event updates Dashboard and Admin consistently',async()=>{
    for(let i=0;i<events.length;i++){
        await publish(i);const event=events[i];
        assert.equal(await page.locator('.parking-card').first().locator('.status-badge').textContent(),event.occupied?'Occupied':'Available');
        assert.equal(await page.locator('#unknownCount').textContent(),'2');
        assert.equal(await page.locator('#occupiedCount').textContent(),event.occupied?'1':'0');
        await page.getByRole('button',{name:'Admin View',exact:true}).click();
        const cells=await page.locator('#adminTableBody tr').first().locator('td').allTextContents();
        assert.equal(cells[0],'A01 / 1001');assert.equal(cells[1],event.occupied?'occupied':'available');
        assert.equal(cells[2],'Received via local MQTT');
        assert.match(cells[3],new RegExp(`ctr ${event.ctr}; ${event.heartbeat?'heartbeat':'transition'}; ${event.batt_mv} mV; status ${event.status}; received`));
        for(const n of [1,2])assert.match(await page.locator('#adminTableBody tr').nth(n).textContent(),/unknownWaiting for MQTT data/);
        if([4,12,20,21].includes(i))await page.screenshot({path:path.join(folder,`event-${i+1}.png`),fullPage:true});
        await page.getByRole('button',{name:'Parking Dashboard',exact:true}).click();
    }
    assert.match(await page.locator('#mqttStatus').textContent(),/accepted 22; duplicates 0; rejected 0/);
});

test('03 duplicate malformed and gap packets rejected with observable counts then recovery',async()=>{
    await publish(0);
    await command({action:'publish',index:0});
    await command({action:'raw',raw:'{broken'});
    await command({action:'publish',index:2});
    await command({action:'publish',index:1});await accepted(2);
    assert.match(await page.locator('#mqttStatus').textContent(),/accepted 2; duplicates 1; rejected 2/);
    assert.match(await page.locator('#adminTableBody tr').first().textContent(),/ctr 1; heartbeat/);
});

test('04 actual broker shutdown Unknown reconnect waits for fresh receipt then recovers',async()=>{
    await publish(0);
    await command({action:'disconnect'});await connected(false);
    assert.equal(await page.locator('#unknownCount').textContent(),'3');
    await page.screenshot({path:path.join(folder,'broker-disconnected.png'),fullPage:true});
    await command({action:'reconnect'});await connected(true);
    assert.equal(await page.locator('#unknownCount').textContent(),'3');
    await publish(1);
    assert.equal(await page.locator('#unknownCount').textContent(),'2');
});

test('05 subscriber HTTP failure Unknown and automatic polling recovery',async()=>{
    await publish(0);
    await page.route('**/api/mqtt',route=>route.abort());
    await page.waitForFunction(()=>document.getElementById('mqttStatus').textContent.includes('HTTP service unavailable'));
    assert.equal(await page.locator('#unknownCount').textContent(),'3');
    await page.unroute('**/api/mqtt');await accepted(1);
    assert.equal(await page.locator('#unknownCount').textContent(),'2');
});

test('06 saved replay and simulation fallbacks remain separate from MQTT receipts',async()=>{
    const fallback=await context.newPage();
    await fallback.goto(url+'/');
    await fallback.waitForFunction(()=>document.getElementById('replayStatus').textContent.includes('Captured replay 0/22'));
    await fallback.locator('#step').click();
    await fallback.waitForFunction(()=>document.getElementById('replayStatus').textContent.includes('Captured replay 1/22'));
    await fallback.goto(url+'/simulation/');
    assert.equal(await fallback.locator('.mode').textContent(),'Simulation Mode');
    assert.equal(await fallback.locator('#occupiedCount').textContent(),'1');
    await accepted(0);assert.equal(await page.locator('#unknownCount').textContent(),'3');
    await fallback.close();
});

test('07 malformed MQTT HTTP snapshot cannot replace mapped bays and recovers',async()=>{
    await publish(0);
    await page.route('**/api/mqtt',route=>route.fulfill({json:{mode:'MQTT_CAPTURE_TRANSPORT',spaces:[]}}));
    await page.waitForFunction(()=>document.getElementById('mqttStatus').textContent.includes('HTTP service unavailable'));
    assert.equal(await page.locator('.parking-card').count(),3);
    assert.equal(await page.locator('#unknownCount').textContent(),'3');
    await page.unroute('**/api/mqtt');await accepted(1);
});
