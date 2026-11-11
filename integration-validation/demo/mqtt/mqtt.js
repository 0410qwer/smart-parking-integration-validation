// Separate MQTT mode. No synthetic sensor timer and no direct capture-file reads.
let mqttBusy = false;
function mqttRender(spaces) {
    parkingSpaces.splice(0, parkingSpaces.length, ...spaces);
    updateDashboard();
    const body = document.getElementById('adminTableBody');
    body.innerHTML = '';
    parkingSpaces.forEach(space => {
        const row = document.createElement('tr');
        const detail = space.ctr === null ? 'No received data' :
            `ctr ${space.ctr}; ${space.heartbeat ? 'heartbeat' : 'transition'}; ${space.batt_mv} mV; status ${space.status}; received ${space.received_at}`;
        [`${space.id} / ${space.spotId}`, getParkingStatus(space), space.connection, detail].forEach(value => {
            const cell = document.createElement('td'); cell.textContent = value; row.appendChild(cell);
        });
        body.appendChild(row);
    });
}
async function pollMqtt() {
    if (mqttBusy) return;
    mqttBusy = true;
    try {
        const response = await fetch('/api/mqtt', {cache:'no-store', signal:AbortSignal.timeout(3000)});
        if (!response.ok) throw new Error('MQTT view unavailable');
        const data = await response.json();
        if (data.mode !== 'MQTT_CAPTURE_TRANSPORT' || data.evidence_kind !== 'CAPTURE_REPLAY_OVER_MQTT' ||
            data.physical_connectivity !== 'NOT_ASSESSED' || typeof data.broker_connected !== 'boolean' ||
            !['accepted','duplicates','rejected','received'].every(key=>Number.isInteger(data[key]) && data[key]>=0) ||
            !Array.isArray(data.spaces) || data.spaces.length !== 3 ||
            !data.spaces.every((space,i)=>space.id === ['A01','A02','A03'][i] && space.spotId === 1001+i &&
                typeof space.online === 'boolean' && typeof space.occupied === 'boolean' &&
                (!space.online || (data.broker_connected && Number.isInteger(space.ctr) && space.ctr>=0 && space.ctr<=255 &&
                    typeof space.heartbeat === 'boolean' && Number.isInteger(space.status) &&
                    typeof space.received_at === 'string')))) throw new Error('Malformed MQTT snapshot');
        mqttRender(data.spaces);
        document.getElementById('mqttStatus').textContent =
            `Local MQTT subscriber ${data.broker_connected ? 'connected' : 'disconnected'}; accepted ${data.accepted}; duplicates ${data.duplicates}; rejected ${data.rejected}. Saved-event transport, physical connectivity not assessed.`;
    } catch (error) {
        parkingSpaces.forEach(space=>{space.online=false; space.connection='Subscriber HTTP service unavailable; physical connectivity unknown';});
        mqttRender([...parkingSpaces]);
        document.getElementById('mqttStatus').textContent = 'Subscriber HTTP service unavailable. Bays Unknown; physical connectivity not assessed.';
    } finally { mqttBusy = false; }
}
parkingSpaces.forEach(space=>{space.online=false; space.ctr=null; space.connection='Waiting for MQTT data';});
mqttRender([...parkingSpaces]);
pollMqtt();
setInterval(pollMqtt,500);
