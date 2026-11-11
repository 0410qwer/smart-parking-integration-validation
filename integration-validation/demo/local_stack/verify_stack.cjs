const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');
const {chromium}=require('../browser/node_modules/playwright');
(async()=>{
 const session=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1280,height:900}});await page.goto(session.url);
  const base=new URL(session.url).origin;const data=await (await fetch(base+'/api/availability')).json();
  if(session.mode==='Multi')await page.waitForFunction(()=>document.getElementById('systemHealth')?.textContent==='3/3 sensors online');
  else await page.waitForFunction(n=>document.getElementById('backendStatus')?.textContent.includes(`committed ${n};`),data.accepted);
  assert.equal(await page.locator('#unknownCount').textContent(),session.mode==='Multi'?'0':'2');
  assert.equal(await page.locator('.parking-card .status-badge').first().textContent(),data.spaces[0].occupied?'Occupied':'Available');
  if(session.mode==='Live')assert.match(await page.locator('.mode').textContent(),/live Wokwi Serial bridge/);
  if(session.mode==='Multi')assert.match(await page.locator('.environment').textContent(),/Virtual sensor demo/);
  await page.getByRole('button',{name:'Admin View',exact:true}).click();
  assert.match(await page.locator('#adminTableBody tr').first().textContent(),/A01 \/ 1001/);
  await page.screenshot({path:path.join(session.session_directory,'startup-dashboard.png'),fullPage:true});
  fs.writeFileSync(path.join(session.session_directory,'browser-check.json'),JSON.stringify({passed:true,browser:browser.version(),api:data},null,2));
 }finally{await browser.close();}
})();
