// Persistent reference backend mode. All availability comes from SQLite-backed API.
let backendBusy=false;
function renderBackend(spaces){
    const mapped=spaces.map(s=>({...s,spotId:s.spot_id,online:s.has_persisted_data,occupied:s.occupied===true}));
    parkingSpaces.splice(0,parkingSpaces.length,...mapped);
    updateDashboard();
    const body=document.getElementById('adminTableBody');body.innerHTML='';
    mapped.forEach(s=>{
        const row=document.createElement('tr');
        const detail=s.has_persisted_data?`DB event ${s.event_id}; ctr ${s.ctr}; ${s.heartbeat?'heartbeat':'transition'}; ${s.batt_mv} mV; status ${s.status_bits}; received ${s.received_at}`:'No persisted data';
        [`${s.id} / ${s.spotId}`,s.status,s.connection,detail].forEach(value=>{
            const cell=document.createElement('td');cell.textContent=value;row.appendChild(cell);
        });body.appendChild(row);
    });
}
function unknownBackend(){
    renderBackend(['A01','A02','A03'].map((id,i)=>({id,spot_id:1001+i,has_persisted_data:false,
        occupied:null,status:'unknown',connection:'Backend/database unavailable; physical connectivity unknown'})));
}
function validateBackend(data){
    if(data.mode!=='SQLITE_REFERENCE_BACKEND'||data.database_persistent!==true||data.physical_connectivity!=='NOT_ASSESSED'||
       typeof data.broker_connected!=='boolean'||!['accepted','duplicates','rejected','received'].every(k=>Number.isInteger(data[k])&&data[k]>=0)||
       !Array.isArray(data.spaces)||data.spaces.length!==3)throw new Error('Invalid reference snapshot');
    data.spaces.forEach((s,i)=>{
        if(s.id!==['A01','A02','A03'][i]||s.spot_id!==1001+i||typeof s.has_persisted_data!=='boolean'||
           typeof s.fresh_this_connection!=='boolean'||typeof s.connection!=='string')throw new Error('Invalid bay mapping');
        if(s.has_persisted_data){
            if(typeof s.occupied!=='boolean'||s.status!==(s.occupied?'occupied':'available')||
               !Number.isInteger(s.ctr)||s.ctr<0||s.ctr>255||typeof s.heartbeat!=='boolean'||
               !Number.isInteger(s.status_bits)||s.status_bits<0||s.status_bits>7||Boolean(s.status_bits&1)!==s.occupied||
               !Number.isInteger(s.batt_mv)||s.batt_mv<0||s.batt_mv>65535||!Number.isInteger(s.event_id)||s.event_id<1||
               typeof s.received_at!=='string'||s.source_timestamp!==null||s.availability_basis!=='LAST_PERSISTED_OBSERVATION')
                throw new Error('Invalid persisted observation');
        }else if(s.status!=='unknown'||s.occupied!==null||s.availability_basis!=='NO_DATA')throw new Error('Invented unknown occupancy');
    });
}
async function pollBackend(){
    if(backendBusy)return;backendBusy=true;
    try{
        const response=await fetch('/api/availability',{cache:'no-store',signal:AbortSignal.timeout(3000)});
        if(!response.ok)throw new Error('Backend unavailable');
        const data=await response.json();validateBackend(data);renderBackend(data.spaces);
        document.getElementById('backendStatus').textContent=`SQLite reference backend; committed ${data.accepted}; duplicates ${data.duplicates}; rejected ${data.rejected}; broker ${data.broker_connected?'connected':'disconnected'}. Showing persisted last-known state; physical connectivity not assessed.`;
    }catch(error){
        unknownBackend();document.getElementById('backendStatus').textContent='Backend/database unavailable. Bays Unknown; physical connectivity not assessed.';
    }finally{backendBusy=false;}
}
unknownBackend();pollBackend();setInterval(pollBackend,500);
