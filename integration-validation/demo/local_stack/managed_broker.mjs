// Reuse the existing broker unchanged; add an owned stdin shutdown channel.
import '../mqtt/broker.mjs';
process.stdin.setEncoding('utf8');
process.stdin.on('data',data=>{if(data.includes('stop'))process.emit('SIGTERM');});
process.stdin.on('end',()=>process.emit('SIGTERM'));
