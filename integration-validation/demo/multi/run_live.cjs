const path=require('node:path');const fs=require('node:fs');const {MultiBridge}=require('./bridge.cjs');
const args=process.argv.slice(2);const option=(n,d)=>{const i=args.indexOf(n);return i<0?d:args[i+1];};
const output=path.resolve(option('--output',path.join(__dirname,'../evidence','multi-live-'+new Date().toISOString().replace(/[:.]/g,'-'))));
const bridge=new MultiBridge({mqttPort:Number(option('--mqtt-port',18890)),session:option('--session','multi-demo'),output,headed:args.includes('--headed')});
let stop=false;for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>{stop=true;});
(async()=>{try{
 await bridge.start();console.log('LIVE multi-bay Wokwi bridge: three virtual HC-SR04 sources; no saved capture input.');let cycle=false;
 while(!stop&&!bridge.error&&!fs.existsSync(path.join(output,'stop.request'))){
  if(args.includes('--demo-cycle')&&!cycle&&new Set(bridge.observations.map(o=>JSON.parse(o.raw).spot_id)).size===3){
   await bridge.setBayDistance(1001,10);await bridge.setBayDistance(1002,35);await bridge.setBayDistance(1003,9);cycle=true;
  }
  await new Promise(r=>setTimeout(r,250));
 }
 if(bridge.error)throw bridge.error;
}catch(e){console.error(e.stack);process.exitCode=e.message.includes('stopped during Wokwi startup')?0:1;}
finally{await bridge.stop();fs.writeFileSync(path.join(output,'stopped.json'),JSON.stringify({stopped:true,source_events:bridge.observations.length}));}})();
