const {test}=require('node:test');const assert=require('node:assert/strict');const {SerialCursor}=require('./bridge.cjs');
const event=n=>JSON.stringify({spot_id:1001,occupied:false,batt_mv:3600,status:0,ctr:n,heartbeat:true});
test('cursor ignores diagnostics and does not replay an unchanged DOM snapshot',()=>{
 const cursor=new SerialCursor();const body='[SENSOR] pulse=580\n'+event(0)+'\n';
 const pending=cursor.extract(body);assert.equal(pending.length,1);cursor.commit(pending[0]);
 assert.deepEqual(cursor.extract(body),[]);
});
test('cursor sends only the new Serial suffix',()=>{
 const cursor=new SerialCursor();cursor.commit(cursor.extract(event(0))[0]);
 const pending=cursor.extract(event(0)+'\n'+event(1));assert.equal(pending.length,1);assert.equal(pending[0].serial_index,1);
});
test('counter wrap does not become a globally unique identity',()=>{
 const cursor=new SerialCursor();const body=Array.from({length:257},(_,i)=>event(i%256)).join('\n');
 const pending=cursor.extract(body);pending.forEach(r=>cursor.commit(r));
 assert.equal(cursor.seen.length,257);assert.equal(cursor.seen[0],cursor.seen[256]);
 assert.deepEqual(cursor.extract(body),[]);
});
test('duplicate payloads are separate received Serial lines for backend deduplication',()=>{
 const cursor=new SerialCursor();const pending=cursor.extract(event(0)+'\n'+event(0));
 assert.equal(pending.length,2);pending.forEach(r=>cursor.commit(r));assert.equal(cursor.seen.length,2);
});
test('log reset or truncation fails closed instead of replaying old lines',()=>{
 const cursor=new SerialCursor();cursor.extract(event(0)+'\n'+event(1)).forEach(r=>cursor.commit(r));
 assert.throws(()=>cursor.extract(event(1)),/reset\/truncated/);
 assert.throws(()=>cursor.extract(event(0)+'\n'+event(2)),/reset\/truncated/);
});
test('out of order bridge acknowledgement cannot advance the cursor',()=>{
 const cursor=new SerialCursor();assert.throws(()=>cursor.commit({raw:event(1),serial_index:1}),/Out-of-order/);
 assert.equal(cursor.seen.length,0);
});
test('partial UART text waits for completion instead of rejecting a valid event',()=>{
 const cursor=new SerialCursor();cursor.commit(cursor.extract(event(0))[0]);
 assert.deepEqual(cursor.extract(event(0)+'\n{"spot_id":1001,"occupi'),[]);
 const pending=cursor.extract(event(0)+'\n'+event(1));assert.equal(pending.length,1);cursor.commit(pending[0]);
 assert.equal(cursor.seen.length,2);
});
test('a broken frame followed by another sensor sample fails explicitly',()=>{
 const cursor=new SerialCursor();assert.throws(()=>cursor.extract('{"spot_id":bad\n[SENSOR] t_ms=10'),/Malformed completed/);
});
