const {test, before, after, beforeEach, afterEach} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
const base = 'http://127.0.0.1:8765';
const output = process.env.BROWSER_EVIDENCE || path.join(__dirname, '../evidence', 'browser-' + new Date().toISOString().replace(/[:.]/g, '-'));
fs.mkdirSync(output, {recursive:true});
const events = fs.readFileSync(path.join(__dirname, '../../captures/wokwi_serial_actual.txt'), 'utf8')
    .split(/\r?\n/).filter(line => line.startsWith('{')).map(JSON.parse);
let browser, context, page;
const observations = [];
before(async () => {
    browser = await chromium.launch({channel:'msedge', headless:true});
    fs.writeFileSync(path.join(output, 'environment.json'), JSON.stringify({browser:browser.version(), channel:'msedge',
        playwright:require('playwright/package.json').version, node:process.version, base, captureEvents:events.length}, null, 2));
    console.log('Browser evidence: ' + output);
});
after(async () => { if(browser) await browser.close(); });
beforeEach(async t => {
    context = await browser.newContext({viewport:{width:1280, height:900}});
    await context.tracing.start({screenshots:true, snapshots:true, sources:true});
    page = await context.newPage();
    page.on('pageerror', error => observations.push({test:t.name, pageError:error.message}));
    page.on('requestfailed', request => observations.push({test:t.name, failedRequest:request.url(), error:request.failure()}));
});
afterEach(async t => {
    const name = t.name.replace(/[^a-z0-9]+/gi,'-');
    await page.screenshot({path:path.join(output, name + '.png'), fullPage:true}).catch(()=>{});
    observations.push({test:t.name, status:await page.locator('#replayStatus').textContent().catch(()=>null),
        cards:await page.locator('.parking-card').allTextContents(), admin:await page.locator('#adminTableBody tr').allTextContents()});
    await context.tracing.stop({path:path.join(output, name + '.zip')});
    fs.writeFileSync(path.join(output,'observations.json'), JSON.stringify(observations,null,2));
    await context.close();
});
async function text(selector) { return (await page.locator(selector).textContent()).trim(); }
async function count(n) { await page.waitForFunction(n => document.getElementById('replayStatus').textContent.includes(`Captured replay ${n}/22`),n); }
async function open() { await page.goto(base); await count(0); }
async function next(n) { await page.locator('#step').click(); await count(n); }
async function unknown() { await page.waitForFunction(()=>document.getElementById('unknownCount').textContent==='3'); }

test('01 real rendering desktop mobile and navigation', async () => {
    await open();
    assert.match(await text('header .mode'), /Captured Wokwi replay/);
    assert.equal(await text('#unknownCount'),'3');
    assert.equal(await page.locator('.parking-card').count(),3);
    assert.equal(await page.locator('.parking-card').first().evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(240, 241, 241)');
    await page.getByRole('button',{name:'Admin View',exact:true}).click();
    assert.equal(await page.locator('#admin').isVisible(),true);
    assert.equal(await page.locator('#parking').isVisible(),false);
    assert.match(await text('#adminTableBody tr:first-child'),/A01 \/ 1001/);
    await page.getByRole('button',{name:'Parking Dashboard',exact:true}).click();
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.locator('.parking-grid').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length),1);
    await page.screenshot({path:path.join(output,'mobile.png'), fullPage:true});
});

test('02 all 22 Next events exactly match saved capture in Dashboard and Admin', async () => {
    await open();
    assert.equal(events.length,22);
    for (let i=0;i<events.length;i++) {
        const event=events[i];
        await next(i+1);
        const state=event.occupied?'occupied':'available';
        assert.equal(await text('.parking-card:first-child h3'),'A01');
        assert.equal(await text('.parking-card:first-child .status-badge'),event.occupied?'Occupied':'Available');
        assert.equal(await text('#unknownCount'),'2');
        assert.equal(await text('#occupiedCount'),event.occupied?'1':'0');
        assert.equal(await text('#availableCount'),event.occupied?'0':'1');
        for (const bay of ['A02','A03']) assert.match(await page.locator('.parking-card').filter({hasText:bay}).textContent(),/Unknown/);
        await page.getByRole('button',{name:'Admin View',exact:true}).click();
        const row=page.locator('#adminTableBody tr').first();
        assert.equal(await row.locator('td').nth(0).textContent(),'A01 / 1001');
        assert.equal(await row.locator('td').nth(1).textContent(),state);
        assert.equal(await row.locator('td').nth(2).textContent(),'Captured record');
        assert.match(await row.locator('td').nth(3).textContent(),new RegExp(`ctr ${event.ctr}; ${event.heartbeat?'heartbeat':'transition'}; ${event.batt_mv} mV; status ${event.status}`));
        assert.match(await page.locator('#adminTableBody tr').nth(1).textContent(),/A02 \/ 1002unknownNo captured data/);
        assert.match(await page.locator('#adminTableBody tr').nth(2).textContent(),/A03 \/ 1003unknownNo captured data/);
        if ([4,12,20,21].includes(i)) await page.screenshot({path:path.join(output,`event-${i+1}-admin.png`),fullPage:true});
        await page.getByRole('button',{name:'Parking Dashboard',exact:true}).click();
    }
    await page.waitForTimeout(1500);
    await count(22);
    assert.match(await text('#replayStatus'),/complete; last captured state held/);
    await page.locator('#play').click(); await count(0);
    await page.locator('#play').click(); await count(0);
    await page.locator('#reset').click(); await count(0);
});

test('03 real timer Play Pause and no synthetic updates while paused', async () => {
    await open();
    await page.locator('#play').click();
    await count(1);
    await page.locator('#play').click();
    await page.waitForFunction(()=>document.getElementById('replayStatus').textContent.includes('paused'));
    const status=await text('#replayStatus');
    const cards=await page.locator('.parking-card').allTextContents();
    await page.waitForTimeout(10500);
    assert.equal(await text('#replayStatus'),status);
    assert.deepEqual(await page.locator('.parking-card').allTextContents(),cards);
    await page.locator('#play').click(); await count(2);
    await page.locator('#reset').click(); await count(0);
});

test('04 simulation independent labelled original timer', async () => {
    await open(); await next(1);
    const simulation=await context.newPage();
    await simulation.goto(base+'/simulation/');
    assert.equal((await simulation.locator('.mode').textContent()).trim(),'Simulation Mode');
    assert.equal(await simulation.locator('#availableCount').textContent(),'1');
    assert.equal(await simulation.locator('#occupiedCount').textContent(),'1');
    assert.equal(await simulation.locator('#unknownCount').textContent(),'1');
    await simulation.waitForFunction(()=>document.getElementById('occupiedCount').textContent==='2',null,{timeout:13000});
    await simulation.getByRole('button',{name:'Admin View',exact:true}).click();
    assert.match(await simulation.locator('#adminTableBody tr').first().textContent(),/A01occupiedOnline/);
    await simulation.screenshot({path:path.join(output,'simulation-admin.png'),fullPage:true});
    await count(1); assert.equal(await text('#occupiedCount'),'0');
    await simulation.close();
});

test('05 aborted replay request shows Unknown then recovers', async () => {
    await open(); await next(1);
    await page.route('**/api/replay?*',route=>route.abort('failed'));
    await page.locator('#step').click(); await unknown();
    assert.match(await text('#replayStatus'),/Replay service unavailable/);
    await page.getByRole('button',{name:'Admin View',exact:true}).click();
    assert.match(await text('#adminTableBody'),/sensor connectivity unknown/);
    await page.unroute('**/api/replay?*');
    await page.locator('#step').click(); await count(2);
    assert.equal(await text('#unknownCount'),'2');
});

test('06 invalid JSON and HTTP 503 fail safely and recover', async () => {
    await open();
    for (const response of [{status:200,contentType:'application/json',body:'{bad json'}, {status:503,body:'Unavailable'}]) {
        await page.route('**/api/replay?*',route=>route.fulfill(response));
        await page.locator('#step').click(); await unknown();
        await page.waitForFunction(()=>document.getElementById('replayStatus').textContent.includes('unavailable'));
        await page.unroute('**/api/replay?*');
        await page.locator('#reset').click(); await count(0);
    }
});

test('07 structurally malformed snapshot fails safely without losing bays or cursor', async () => {
    await open(); await next(1);
    await page.route('**/api/replay?*',route=>route.fulfill({json:{mode:'CAPTURE_REPLAY',count:777,total:22,spaces:[]}}));
    await page.locator('#step').click();
    await page.waitForFunction(()=>document.getElementById('replayStatus').textContent.includes('unavailable'),null,{timeout:2000});
    await unknown();
    assert.equal(await page.locator('.parking-card').count(),3);
    await page.unroute('**/api/replay?*');
    await page.locator('#step').click(); await count(2);
});

test('08 Reset during delayed Next wins over stale response', async () => {
    await open();
    let release, entered;
    const started=new Promise(resolve=>entered=resolve);
    const gate=new Promise(resolve=>release=resolve);
    await page.route('**/api/replay?count=1',async route=>{entered(); await gate; await route.continue();});
    await page.locator('#step').click(); await started;
    await page.locator('#reset').click();
    release();
    await page.waitForTimeout(700);
    await page.waitForFunction(()=>document.getElementById('replayStatus').textContent.includes('Captured replay 0/22'),null,{timeout:2000});
    assert.equal(await text('#unknownCount'),'3');
});

test('09 timeout marks service unavailable and recovers', async () => {
    await open();
    await page.route('**/api/replay?*',async route=>{await new Promise(resolve=>setTimeout(resolve,6000)); await route.abort().catch(()=>{});});
    await page.locator('#step').click();
    await page.waitForFunction(()=>document.getElementById('replayStatus').textContent.includes('unavailable'),null,{timeout:7500});
    await unknown();
    await page.unroute('**/api/replay?*');
    await page.locator('#step').click(); await count(1);
});

test('10 invalid API requests rejected by actual service', async () => {
    await open();
    for (const value of ['-1','23','bad']) {
        const response=await page.request.get(base+'/api/replay?count='+value);
        assert.equal(response.status(),400);
    }
    await count(0);
    assert.equal(observations.filter(item=>item.pageError).length,0,'No uncaught browser JavaScript errors');
});

test('11 invalid mapping metadata and response counter never replace validated state', async () => {
    await open(); await next(1);
    const snapshot=await (await page.request.get(base+'/api/replay?count=2')).json();
    for (const mutate of [s=>s.spaces[0].spotId=9999, s=>s.spaces[0].occupied='false',
        s=>s.spaces[0].ctr=256, s=>s.connectivity='ONLINE', s=>s.count=3]) {
        const bad=structuredClone(snapshot); mutate(bad);
        await page.route('**/api/replay?*',route=>route.fulfill({json:bad}));
        await page.locator('#step').click();
        await page.waitForFunction(()=>document.getElementById('replayStatus').textContent.includes('unavailable'));
        await unknown();
        assert.equal(await page.locator('.parking-card').count(),3);
        await page.unroute('**/api/replay?*');
        await page.locator('#reset').click(); await count(0);
        await next(1);
    }
});

test('12 browser tabs have independent replay cursors', async () => {
    await open(); await next(1);
    const other=await context.newPage();
    await other.goto(base);
    await other.waitForFunction(()=>document.getElementById('replayStatus').textContent.includes('Captured replay 0/22'));
    assert.equal(await other.locator('#unknownCount').textContent(),'3');
    await next(2);
    assert.match(await other.locator('#replayStatus').textContent(),/Captured replay 0\/22/);
    await other.close();
});
