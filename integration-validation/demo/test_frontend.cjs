// DOM contract tests, not a full browser: execute the actual teammate app + adapter.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
class Element {
    constructor() { this.children = []; this.textContent = ''; this.listeners = {}; this.dataset = {}; this.classList = {add(){}, remove(){}}; }
    set innerHTML(value) { this.children = []; }
    appendChild(child) { this.children.push(child); }
    addEventListener(name, fn) { this.listeners[name] = fn; }
}
function harness(original = false) {
    const elements = {};
    const document = {getElementById: id => elements[id] ||= new Element(), createElement: () => new Element(), querySelectorAll: () => []};
    const context = vm.createContext({document, Date, AbortSignal, AbortController, setInterval(){}, fetch: () => new Promise(() => {})});
    const app = fs.readFileSync(path.join(__dirname, '../../smart-parking-web/app.js'), 'utf8');
    vm.runInContext(original ? app : app.split('// 7. Initialise application')[0], context);
    if (!original) vm.runInContext(fs.readFileSync(path.join(__dirname, 'integration.js'), 'utf8'), context);
    return {context, elements, run: code => vm.runInContext(code, context)};
}
test('original simulation: Available, Occupied, Unknown and Admin rows', () => {
    const h = harness(true);
    assert.deepEqual(['availableCount','occupiedCount','unknownCount'].map(id => h.elements[id].textContent), [1,1,1]);
    assert.equal(h.elements.adminTableBody.children.length, 3);
    h.run('simulateSensorUpdates(); simulateSensorUpdates()');
    assert.equal(h.elements.occupiedCount.textContent, 2);
});
test('integration clears synthetic defaults before fetch', () => {
    const h = harness();
    assert.equal(h.elements.unknownCount.textContent, 3);
    assert.equal(h.elements.availableCount.textContent, 0);
});
test('actual Python HTTP snapshots render capture transitions and Admin evidence', async () => {
    const h = harness();
    for (const [count, expected] of [[1,'available'],[5,'occupied'],[13,'available'],[22,'occupied']]) {
        const response = await fetch(`http://127.0.0.1:8765/api/replay?count=${count}`);
        assert.equal(response.status, 200);
        h.context.data = await response.json();
        h.run('renderReplay(data)');
        assert.equal(h.elements.parkingGrid.children[0].className, 'parking-card ' + expected);
        assert.equal(h.elements.unknownCount.textContent, 2);
        const row = h.elements.adminTableBody.children[0];
        assert.equal(row.children[0].textContent, 'A01 / 1001');
        assert.match(row.children[3].textContent, /line \d+; ctr \d+; (heartbeat|transition)/);
    }
});
test('replay service failure marks all bays Unknown and identifies transport', async () => {
    const h = harness();
    h.context.fetch = async () => {throw new Error('offline');};
    h.run('busy = false');
    await h.run('loadCount(1)');
    assert.equal(h.elements.unknownCount.textContent, 3);
    assert.match(h.elements.replayStatus.textContent, /Replay service unavailable/);
    assert.match(h.elements.adminTableBody.children[0].children[2].textContent, /sensor connectivity unknown/);
});

test('malformed snapshot preserves cursor and all bay cards', async () => {
    const h = harness();
    h.context.fetch = async () => ({ok:true,json:async()=>({count:777,total:22,spaces:[]})});
    await h.run('loadCount(1)');
    assert.equal(h.run('cursor'),0);
    assert.equal(h.elements.parkingGrid.children.length,3);
    assert.equal(h.elements.unknownCount.textContent,3);
    assert.match(h.elements.replayStatus.textContent,/unavailable/);
});

test('Reset supersedes delayed response even if transport ignores cancellation', async () => {
    const h=harness();
    const states=await Promise.all([0,1].map(async n=>(await fetch(`http://127.0.0.1:8765/api/replay?count=${n}`)).json()));
    let release;
    h.context.fetch=async url=>{
        if(url.endsWith('=1')) await new Promise(resolve=>release=resolve);
        return {ok:true,json:async()=>states[url.endsWith('=1')?1:0]};
    };
    const pending=h.run('loadCount(1)');
    await h.run('loadCount(0)');
    release(); await pending;
    assert.equal(h.run('cursor'),0);
    assert.equal(h.elements.unknownCount.textContent,3);
    assert.match(h.elements.replayStatus.textContent,/Captured replay 0\/22/);
});
