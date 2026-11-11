// Reuse the teammate dashboard renderer and navigation without its simulation timer.
let cursor = 0, total = 0, playing = false, busy = false;
let requestVersion = 0, activeRequest = null;
function validateSnapshot(data, requestedCount) {
    const uint = (value, max) => Number.isInteger(value) && value >= 0 && value <= max;
    const bays = [[1001, 'A01'], [1002, 'A02'], [1003, 'A03']];
    if (!data || data.mode !== 'CAPTURE_REPLAY' || data.connectivity !== 'NOT_ASSESSED' ||
        !uint(data.total, Number.MAX_SAFE_INTEGER) || data.total === 0 ||
        (total !== 0 && data.total !== total) || data.count !== requestedCount ||
        !uint(data.count, data.total) || !/^[a-f0-9]{64}$/.test(data.capture_sha256) ||
        !Array.isArray(data.spaces) || data.spaces.length !== bays.length) {
        throw new Error('Invalid replay snapshot');
    }
    data.spaces.forEach((space, index) => {
        const [spotId, id] = bays[index];
        if (!space || space.id !== id || space.spotId !== spotId ||
            typeof space.online !== 'boolean' || typeof space.occupied !== 'boolean' || space.lastUpdate !== null) {
            throw new Error('Invalid bay mapping or state');
        }
        if (space.online) {
            if (data.count === 0 || space.connection !== 'Captured record' || !uint(space.ctr, 255) ||
                typeof space.heartbeat !== 'boolean' || !uint(space.batt_mv, 65535) ||
                !uint(space.status, 7) || Boolean(space.status & 1) !== space.occupied ||
                !Number.isInteger(space.line) || space.line < 1) throw new Error('Invalid captured metadata');
        } else if (space.connection !== 'No captured data' ||
                   ['ctr', 'heartbeat', 'batt_mv', 'status', 'line'].some(key => space[key] !== null)) {
            throw new Error('Invalid unknown bay');
        }
    });
    if (data.count > 0 && !data.spaces.some(space => space.online)) throw new Error('Missing captured state');
}
function renderReplay(data) {
    parkingSpaces.splice(0, parkingSpaces.length, ...data.spaces);
    updateDashboard();
    const body = document.getElementById('adminTableBody');
    body.innerHTML = '';
    parkingSpaces.forEach(space => {
        const row = document.createElement('tr');
        const detail = space.ctr === null ? 'No data' :
            `line ${space.line}; ctr ${space.ctr}; ${space.heartbeat ? 'heartbeat' : 'transition'}; ${space.batt_mv} mV; status ${space.status}`;
        [ `${space.id} / ${space.spotId}`, getParkingStatus(space), space.connection, detail ].forEach(value => {
            const cell = document.createElement('td');
            cell.textContent = value;
            row.appendChild(cell);
        });
        body.appendChild(row);
    });
}
async function loadCount(count) {
    // A newer user action supersedes in-flight work. Stale responses cannot undo Reset.
    const version = ++requestVersion;
    if (activeRequest) activeRequest.abort();
    activeRequest = new AbortController();
    busy = true;
    try {
        const response = await fetch(`/api/replay?count=${count}`, {cache: 'no-store',
            signal: AbortSignal.any([activeRequest.signal, AbortSignal.timeout(5000)])});
        if (!response.ok) throw new Error('Replay HTTP ' + response.status);
        const data = await response.json();
        if (version !== requestVersion) return;
        validateSnapshot(data, count);
        cursor = data.count; total = data.total;
        renderReplay(data);
        document.getElementById('replayStatus').textContent =
            `Captured replay ${cursor}/${total} — ${cursor === total ? 'complete; last captured state held' : playing ? 'playing' : 'paused'}. Sensor connectivity not assessed.`;
        if (cursor === total) playing = false;
    } catch (error) {
        if (version !== requestVersion) return;
        playing = false;
        parkingSpaces.forEach(space => { space.online = false; space.connection = 'Replay service unavailable (sensor connectivity unknown)'; });
        renderReplay({spaces: [...parkingSpaces]});
        document.getElementById('replayStatus').textContent = 'Replay service unavailable. Bays shown Unknown. Retry Next event or use labelled simulation fallback.';
    } finally { if (version === requestVersion) { busy = false; activeRequest = null; } }
}
document.getElementById('play').addEventListener('click', () => {
    playing = !playing;
    if (playing) loadCount(cursor === total ? 0 : cursor);
    else loadCount(cursor);
});
document.getElementById('step').addEventListener('click', () => { playing = false; loadCount(Math.min(cursor + 1, total)); });
document.getElementById('reset').addEventListener('click', () => { playing = false; loadCount(0); });
setInterval(() => { if (playing && !busy) loadCount(Math.min(cursor + 1, total)); }, 1000);
// Clear original synthetic defaults before any asynchronous request.
parkingSpaces.forEach(space => { space.online = false; space.ctr = null; space.connection = 'No captured data'; });
renderReplay({spaces: [...parkingSpaces]});
loadCount(0);
