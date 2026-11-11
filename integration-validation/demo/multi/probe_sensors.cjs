const {chromium}=require('../browser/node_modules/playwright');const fs=require('node:fs');const path=require('node:path');
const output=path.resolve(__dirname,'../evidence','multi-sensors-'+new Date().toISOString().replace(/[:.]/g,'-'));fs.mkdirSync(output,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});const context=await browser.newContext({viewport:{width:1600,height:1000}});
 await context.tracing.start({screenshots:true,snapshots:true,sources:true});const page=await context.newPage();const proof={actions:[],physical_hardware:false};
 const serial=async()=> (await page.locator('body').innerText()).split(/\r?\n/).filter(l=>/^\[(SENSOR|BOOT)\]|^\{"spot_id"/.test(l)).join('\n');
 const events=async()=> (await serial()).split('\n').filter(l=>l.startsWith('{')&&l.endsWith('}')).map(JSON.parse);
 const wait=async predicate=>{for(let i=0;i<150;i++){if(await predicate())return;await page.waitForTimeout(200);}throw new Error('Sensor expectation timed out');};
 try{
  await page.goto('https://wokwi.com/projects/new/esp32');await page.waitForFunction(()=>window.monaco?.editor.getModels().some(m=>String(m.uri)==='vfs:sketch.ino'));
  for(const name of ['sketch.ino','diagram.json']){
   if(name==='diagram.json')await page.getByText(name,{exact:true}).click();
   await page.waitForFunction(name=>window.monaco.editor.getModels().some(m=>String(m.uri)==='vfs:'+name),name);
   const source=fs.readFileSync(path.join(__dirname,'firmware',name),'utf8');fs.writeFileSync(path.join(output,name),source);
   await page.evaluate(({name,source})=>window.monaco.editor.getModels().find(m=>String(m.uri)==='vfs:'+name).setValue(source),{name,source});
  }
  await page.getByText('sketch.ino',{exact:true}).click();await page.waitForTimeout(750);await page.getByRole('button',{name:'Start the simulation',exact:true}).click();
  for(let i=0;i<120;i++){
   if(new Set((await events()).map(e=>e.spot_id)).size===3)break;
   const buildBody=await page.locator('body').innerText();if(/Compilation error|error:/.test(buildBody))throw new Error(buildBody.slice(-3000));
   if(i%6===0)console.log('Waiting for real three-sensor Wokwi build/readings');await page.waitForTimeout(5000);
  }
  proof.initial=await events();if(new Set(proof.initial.map(e=>e.spot_id)).size!==3)throw new Error('Three independent sensors not observed');
  async function distance(id,cm){
   const part=page.locator('#ultrasonic'+(id-1000));await part.click();await page.waitForTimeout(100);const slider=page.locator('input[type=range]');
   if(!await slider.count()){await part.click();await page.waitForTimeout(100);}
   await slider.evaluate((el,v)=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,String(v));el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));},cm);
   proof.actions.push({id,cm,at:new Date().toISOString()});
  }
  const before=proof.initial.length;await distance(1001,10);await distance(1002,35);await distance(1003,9);
  await wait(async()=>{const seen=(await events()).slice(before);return [1001,1002,1003].every(id=>seen.some(e=>e.spot_id===id&&!e.heartbeat&&e.occupied===(id!==1002)));});
  proof.final=await events();proof.passed=true;
  fs.writeFileSync(path.join(output,'serial_actual.txt'),await serial());await page.screenshot({path:path.join(output,'three-sensors.png'),fullPage:true});
 }catch(e){proof.error=e.stack;process.exitCode=1;await page.screenshot({path:path.join(output,'error.png'),fullPage:true});}
 finally{try{await context.tracing.stop({path:path.join(output,'trace.zip')});}catch(e){proof.trace_warning=e.message;}finally{await browser.close();}fs.writeFileSync(path.join(output,'proof.json'),JSON.stringify(proof,null,2));console.log(JSON.stringify({output,passed:proof.passed,error:proof.error}));}
})();
