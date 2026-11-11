const fs=require('node:fs');
const path=require('node:path');
const {spawn}=require('node:child_process');
const output=path.resolve(__dirname,'../evidence','mqtt-browser-'+new Date().toISOString().replace(/[:.]/g,'-'));
fs.mkdirSync(output,{recursive:true});
const args=['--test','--test-reporter=tap',path.join(__dirname,'browser.test.cjs')];
const child=spawn(process.execPath,args,{env:{...process.env,BROWSER_EVIDENCE:output}});
let log='';
for(const stream of [child.stdout,child.stderr])stream.on('data',chunk=>{log+=chunk;process.stdout.write(chunk);});
child.on('error',e=>{console.error(e);process.exitCode=1;});
child.on('close',code=>{
    fs.writeFileSync(path.join(output,'console.tap'),log);
    const counts=Object.fromEntries([...log.matchAll(/^# (tests|pass|fail|cancelled|skipped) (\d+)/gm)].map(m=>[m[1],Number(m[2])]));
    fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({command:[process.execPath,...args],exitCode:code,...counts},null,2));
    console.log('MQTT browser evidence: '+output);process.exitCode=code===0?0:1;
});
