// Real Wokwi web simulation. Never saves/shares a project or changes the originals.
const {chromium}=require('../browser/node_modules/playwright');
const fs=require('node:fs');const path=require('node:path');
const mode=process.argv[2]||'inspect';
const output=path.resolve(__dirname,'../evidence','sensor-wokwi-'+mode+'-'+new Date().toISOString().replace(/[:.]/g,'-'));
fs.mkdirSync(output,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({viewport:{width:1500,height:1000}});const page=await context.newPage();
 await context.tracing.start({screenshots:true,snapshots:true,sources:true});
 const diagnostics=[];page.on('pageerror',e=>diagnostics.push({error:e.message}));
 page.on('console',message=>{if(message.type()==='error')diagnostics.push({consoleError:message.text()});});
 const result={mode,output,browser:browser.version(),url:'https://wokwi.com/projects/new/esp32',saved:false};
 try{
  await page.goto(result.url,{waitUntil:'domcontentloaded',timeout:45000});
  await page.waitForFunction(()=>window.monaco?.editor.getModels().some(m=>String(m.uri)==='vfs:sketch.ino'));
  let sketch=fs.readFileSync(path.join(__dirname,mode==='network'?'network-probe/sketch.ino':'firmware/sketch.ino'),'utf8');
  if(mode==='selftest')sketch=sketch.replace('#define SENSOR_SELF_TEST 0','#define SENSOR_SELF_TEST 1');
  await page.evaluate(code=>window.monaco.editor.getModels().find(m=>String(m.uri)==='vfs:sketch.ino').setValue(code),sketch);
  await page.getByText('diagram.json',{exact:true}).click();
  await page.waitForFunction(()=>window.monaco.editor.getModels().some(m=>String(m.uri)==='vfs:diagram.json'));
  const diagram=JSON.parse(fs.readFileSync(path.join(__dirname,'firmware/diagram.json'),'utf8'));
  if(mode==='timeout')diagram.connections=diagram.connections.filter(wire=>!wire.includes('ultrasonic1:ECHO'));
  fs.writeFileSync(path.join(output,'sketch.ino'),sketch);fs.writeFileSync(path.join(output,'diagram.json'),JSON.stringify(diagram,null,2));
  await page.evaluate(code=>window.monaco.editor.getModels().find(m=>String(m.uri)==='vfs:diagram.json').setValue(code),JSON.stringify(diagram));
  await page.getByText('sketch.ino',{exact:true}).click();await page.waitForTimeout(750);
  result.buttons=await page.locator('button').evaluateAll(els=>els.map(el=>({title:el.title,aria:el.getAttribute('aria-label'),text:el.textContent})));
  const play=page.locator('button[title*="Start"],button[aria-label*="Start"]');
  if(await play.count())await play.first().click();
  else await page.getByRole('button',{name:/Start|Play/}).first().click();
  for(let i=0;i<120;i++){
    await page.waitForTimeout(5000);
    const body=await page.locator('body').innerText();
    if(i%6===0)console.log(JSON.stringify({progress:body.slice(-700),elapsed_s:(i+1)*5,output}));
    if(/^\[SENSOR\]|^\[SELFTEST\]|^\[NETWORK\] DONE/m.test(body)||body.includes('Compilation error'))break;
  }
  const serial=async()=> (await page.locator('body').innerText()).split(/\r?\n/).filter(line=>/^\[(BOOT|SENSOR|SELFTEST|NETWORK)\]|^\{"spot_id"/.test(line)).join('\n')+'\n';
  const messages=async()=> (await serial()).split('\n').filter(line=>line.startsWith('{')).map(JSON.parse);
  if(mode==='capture'){
    const waitState=async(occupied,after)=>{
      for(let i=0;i<120;i++){
        const events=await messages();if(events.length>after&&events.at(-1).occupied===occupied)return;
        await page.waitForTimeout(250);
      }throw new Error('No confirmed sensor state '+occupied);
    };
    await waitState(false,0);result.actions=[];
    await page.locator('wokwi-hc-sr04').click();
    const slider=page.locator('input[type=range]');
    const setDistance=async(cm)=>{
      const before=(await messages()).length;
      await slider.evaluate((el,value)=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,String(value));el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));},cm);
      result.actions.push({distance_cm:cm,control_value:await slider.inputValue(),after_event_count:before,wall_time:new Date().toISOString()});return before;
    };
    await waitState(true,await setDistance(10));await page.screenshot({path:path.join(output,'occupied-10cm.png'),fullPage:true});
    const bandBefore=await messages();await setDistance(17);await page.waitForTimeout(3000);
    const bandAfter=await messages();if(bandAfter.slice(bandBefore.length).some(e=>!e.occupied))throw new Error('Hysteresis band changed occupancy');
    await waitState(false,await setDistance(35));await page.screenshot({path:path.join(output,'free-35cm.png'),fullPage:true});
    await waitState(true,await setDistance(9));
    await waitState(false,await setDistance(35));await setDistance(400);await page.waitForTimeout(5500);
  }
  result.serial=await serial();fs.writeFileSync(path.join(output,'serial_actual.txt'),result.serial);
  result.actual_events=(await messages()).length;
  if(mode==='capture'&&result.actual_events<5)throw new Error('Insufficient actual events');
  if(mode==='timeout'&&(!result.serial.includes('valid=0')||result.actual_events!==0))throw new Error('Timeout behavior not observed');
  if(mode==='selftest'&&!result.serial.includes('passed=20 failed=0'))throw new Error('Firmware selftests did not all pass');
  if(mode==='network'&&!result.serial.includes('[NETWORK] DONE'))throw new Error('Network probe did not finish');
  result.body=(await page.locator('body').innerText()).slice(-18000);
  result.elements=await page.evaluate(()=>Array.from(document.querySelectorAll('*')).filter(el=>el.tagName.startsWith('WOKWI')||el.className==='xterm-rows').map(el=>({tag:el.tagName,id:el.id,keys:Object.keys(el),text:el.textContent?.slice(-3000),shadow:el.shadowRoot?.innerHTML.slice(-1500)})));
  result.terminal=await page.evaluate(()=>Array.from(document.querySelectorAll('[class*="xterm"]')).map(el=>({class:el.className,keys:Object.keys(el)})));
  await page.locator('wokwi-hc-sr04').click().catch(()=>{});
  result.controls=await page.locator('input').evaluateAll(els=>els.map(el=>({type:el.type,value:el.value,aria:el.getAttribute('aria-label')})));
  await page.screenshot({path:path.join(output,'simulation.png'),fullPage:true});
 }catch(error){result.error=error.stack;await page.screenshot({path:path.join(output,'error.png'),fullPage:true}).catch(()=>{});}
 fs.writeFileSync(path.join(output,'result.json'),JSON.stringify({...result,diagnostics},null,2));
 await context.tracing.stop({path:path.join(output,'trace.zip')});await browser.close();
 console.log(JSON.stringify({mode,output,error:result.error,actual_events:result.actual_events,serial_tail:result.serial?.slice(-2000)},null,2));if(result.error)process.exitCode=1;
})();
