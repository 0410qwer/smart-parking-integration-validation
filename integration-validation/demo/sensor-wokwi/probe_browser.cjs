const {chromium}=require('../browser/node_modules/playwright');
const fs=require('node:fs');const path=require('node:path');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage();
 const result={at:new Date().toISOString(),url:'https://wokwi.com/projects/new/esp32',browser:browser.version()};
 try{
   const response=await page.goto(result.url,{waitUntil:'domcontentloaded',timeout:45000});
   result.http=response.status();await page.waitForTimeout(10000);
   result.title=await page.title();result.body=(await page.locator('body').innerText()).slice(0,14000);
   result.frames=page.frames().map(f=>f.url());
   result.monaco=await page.evaluate(()=>({monaco:!!window.monaco,models:window.monaco?.editor?.getModels().map(m=>({uri:String(m.uri),length:m.getValueLength()}))}));
   await page.screenshot({path:path.join(__dirname,'browser-access.png'),fullPage:true});
 }catch(error){result.error=error.message;}
 fs.writeFileSync(path.join(__dirname,'browser-access.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
 await browser.close();
})();
