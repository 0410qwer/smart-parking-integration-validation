const {LiveBridge}=require('./bridge.cjs');const path=require('node:path');const fs=require('node:fs');
const args=process.argv.slice(2);const option=(name,fallback)=>{const i=args.indexOf(name);return i>=0?args[i+1]:fallback;};
const output=path.resolve(option('--output',path.join(__dirname,'../evidence','live-bridge-'+new Date().toISOString().replace(/[:.]/g,'-'))));
const bridge=new LiveBridge({mqttPort:Number(option('--mqtt-port',18886)),output,headed:args.includes('--headed')});
let stop=false;for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>{stop=true;});
(async()=>{
 try{
  await bridge.start();console.log('LIVE Wokwi Serial bridge running. Change the HC-SR04 slider; no saved capture is read.');
  let cycle=0;
  while(!stop&&!bridge.error){
   if(fs.existsSync(path.join(output,'stop.request')))break;
   if(args.includes('--demo-cycle')){
    const observed=bridge.observations.map(o=>JSON.parse(o.raw));
    if(cycle===0&&observed.some(e=>!e.occupied)){await bridge.setDistance(10);cycle=1;}
    else if(cycle===1&&observed.some(e=>e.occupied)){await bridge.setDistance(35);cycle=2;}
    else if(cycle===2&&observed.filter(e=>!e.occupied).length>=2){
     fs.writeFileSync(path.join(output,'demo-cycle-complete.json'),JSON.stringify({virtual_sensor_cycle:true,replay:false,observed_events:observed.length}));cycle=3;
    }
   }
   await new Promise(resolve=>setTimeout(resolve,500));
  }
  if(bridge.error)throw bridge.error;
 }catch(error){console.error(error.stack);process.exitCode=error.message.includes('stopped during Wokwi startup')?0:1;}
 finally{await bridge.stop();fs.writeFileSync(path.join(output,'stopped.json'),JSON.stringify({stopped:true,forwarded:bridge.cursor.seen.length}));}
})();
