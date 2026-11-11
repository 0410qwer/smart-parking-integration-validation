// Actual MQTT 3.1.1 TCP broker, loopback-only. In-memory test harness, no DB.
import {createServer} from 'node:net';
import {Aedes} from 'aedes';
import {appendFileSync} from 'node:fs';
const port = Number(process.argv[2] ?? 18883);
const logPath = process.argv[3];
function log(event, fields={}) {
    const line=JSON.stringify({at:new Date().toISOString(),event,...fields});
    console.log(line);
    if(logPath) appendFileSync(logPath,line+'\n');
}
const broker = await Aedes.createBroker();
// Keep the harness namespace isolated from any production topics.
const prefix='smart-parking/integration-test/';
broker.authorizePublish=(client,packet,done)=>{
    if(!packet.topic.startsWith(prefix) || packet.retain || packet.qos!==1)
        return done(new Error('Harness requires its namespace, QoS 1 and retain=false'));
    done(null);
};
broker.authorizeSubscribe=(client,subscription,done)=>{
    if(!subscription.topic.startsWith(prefix)) return done(new Error('Harness namespace only'));
    done(null,subscription);
};
broker.on('client',client=>log('client_connected',{client_id:client.id}));
broker.on('clientDisconnect',client=>log('client_disconnected',{client_id:client.id}));
broker.on('subscribe',(subscriptions,client)=>log('subscribe',{client_id:client.id,subscriptions}));
broker.on('publish',(packet,client)=>{
    if(client) log('publish',{client_id:client.id,topic:packet.topic,qos:packet.qos,
        message_id:packet.messageId,retain:packet.retain,payload:packet.payload.toString('utf8')});
});
broker.on('clientError',(client,error)=>log('client_error',{client_id:client?.id,error:error.message}));
const server=createServer(broker.handle);
server.on('error',error=>{log('server_error',{error:error.message});process.exitCode=1;broker.close();});
server.listen(port,'127.0.0.1',()=>log('listening',{host:'127.0.0.1',port:server.address().port,broker:'aedes',version:'1.2.0'}));
for(const signal of ['SIGINT','SIGTERM']) process.on(signal,()=>{
    server.close(); broker.close(()=>process.exit(0));
});
