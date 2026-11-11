"""Assemble final technical handover from preserved, measured evidence only."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
EVIDENCE=HERE.parent/'evidence'

def load(path):return json.loads(path.read_text(encoding='utf-8'))
def link(path):return path.relative_to(ROOT).as_posix()
def row(name,stats):
    return '| '+name+' | '+' | '.join(f'{stats[k]:.2f}' for k in ('minimum_ms','median_ms','p95_ms','maximum_ms'))+' |'

def source_paths():
    """Prune generated trees before walking them, not after visiting every file."""
    paths=[]
    for directory,dirs,files in os.walk(HERE.parent):
        dirs[:]=[d for d in dirs if d not in ('evidence','node_modules','vendor','tools','data','__pycache__')]
        for name in files:
            path=Path(directory)/name
            if path.suffix.lower() in ('.py','.cjs','.mjs','.js','.html','.css','.ino','.sql','.json','.cpp','.h','.ps1') and name!='FINAL_AUDIT.json':paths.append(path)
    return paths+[ROOT/n for n in ('Start-LocalDemo.ps1','Stop-LocalDemo.ps1','INTEGRATION_DEMO_README.md','FINAL_TECHNICAL_AUDIT.md')]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system',required=True,type=Path)
    parser.add_argument('--performance',type=Path,default=EVIDENCE/'performance-20261111T162406427918Z')
    parser.add_argument('--stability',type=Path,default=EVIDENCE/'performance-20261111T161832850441Z')
    parser.add_argument('--volume',type=Path,default=EVIDENCE/'volume-20261111T162326102873Z')
    args=parser.parse_args();args.system=args.system.resolve()
    system=load(args.system);perf=load(args.performance/'results.json');trials=load(args.performance/'trials.json')
    stability=load(args.stability/'stability.json');volume=load(args.volume/'volume.json');volume_result=load(args.volume/'results.json')
    resources=load(args.stability/'resource-samples.json')
    assert system['overall']=='PASS' and perf['exit_code']==0 and stability['passed'] and volume['passed']
    handoff=EVIDENCE/'stabilization-handoff-20261112';startcheck=EVIDENCE/'stabilization-startcheck-20261112'
    assert load(handoff/'browser-check.json')['passed']
    stopped=load(startcheck/'session.json');assert stopped['status']=='stopped' and all(c==0 for c in stopped['child_exit_codes'].values())
    protected={p:hashlib.sha256(Path(p).read_bytes()).hexdigest()==v for p,v in system['preserved_file_sha256'].items()}
    git=subprocess.run(['git','-c','safe.directory='+str(ROOT/'smart-parking-web'),'-C',str(ROOT/'smart-parking-web'),'status','--porcelain'],capture_output=True,text=True)
    assert all(protected.values()) and git.returncode==0 and not git.stdout.strip()
    folder=EVIDENCE/('stabilization-audit-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));folder.mkdir()
    changed=['integration-validation/demo/multi/'+n for n in (
        'model.py','outbox.py','bridge.cjs','build_firmware.py','firmware/sketch.ino','browser_fixture.py',
        'web/dashboard.js','test_multi.py','performance_tools.py','performance.test.cjs','run_performance.py','run_volume.py','stabilization_audit.py')]
    changed+=['INTEGRATION_DEMO_README.md','FINAL_TECHNICAL_AUDIT.md',link(folder/'results.json'),link(folder/'source_sha256.json')]
    memory={}
    for role in resources[0]['rss_bytes']:
        values=[r['rss_bytes'][role] for r in resources if r.get('rss_bytes',{}).get(role) is not None]
        memory[role]=dict(first_bytes=values[0],last_bytes=values[-1],minimum_bytes=min(values),maximum_bytes=max(values))
    target_misses={d:sum(t['control_to_dom_ms']>3000 for t in trials if t['poll_ms']==200 and t['expected']==d) for d in ('occupied','available')}
    summary=dict(client_date='2026-11-12',created_at_utc=datetime.now(timezone.utc).isoformat(),
        regression_results=str(args.system),regression_counts=system['totals'],
        supplementary=dict(controlled_performance_counts=perf['counts'],extended_stability_counts=load(args.stability/'results.json')['counts'],volume_counts=volume_result),
        counting_note='Supplementary scenario executions are reported separately; repeated performance runs are not counted as new regression test cases.',
        performance=perf['performance'],target_exceedances_over_3000ms=target_misses,
        stability=stability,stability_rss=memory,
        runner_heap_used_bytes=dict(first=resources[0]['runner_memory']['heapUsed'],last=resources[-1]['runner_memory']['heapUsed'],peak=max(r['runner_memory']['heapUsed'] for r in resources)),
        database_growth_bytes=dict(first=resources[0]['database_bytes'],last=resources[-1]['database_bytes'],peak=max(r['database_bytes'] for r in resources)),
        volume=dict(traffic_kind=volume['traffic_kind'],generated=volume['generated'],accepted=volume['accepted'],duplicates=volume['duplicate_deliveries'],rejected=volume['rejected'],missing=volume['missing_confirmed_events'],integrity=volume['integrity'],resource_samples=len(volume['resource_samples'])),
        protected_files_unchanged=protected,teammate_frontend_git_clean=True,
        verified_path='three live Wokwi virtual HC-SR04 -> browser Serial -> durable outbox -> TCP MQTT QoS1 -> SQLite reference backend -> API -> Edge Dashboard/Admin',
        ready_for_bounded_local_virtual_demo=True,three_second_compliance=False,physical_hardware_verified=False,
        direct_esp32_mqtt_verified=False,production_ready=False,
        remaining_blockers=['Saaket production backend unavailable','Physical hardware and physical latency unverified',
            'Direct ESP32-to-local MQTT unverified','Material browser-driver Node memory growth; no long-duration leak qualification',
            'Six of thirty Free trials exceeded 3000 ms','Production authentication/TLS/ACLs/operations not implemented',
            'Admin history has first-page display only; use API pagination for later events'],
        previous_runs=dict(interrupted_completed='system-20261111T162138594916Z: 254/0/0/0',
            resumed_failed='system-20261111T185541768436Z: 254/1/0/0; fixture health-ordering race corrected'),
        memory_scope='RSS samples exclude Edge child tree; Node runner combines Playwright, bridge and measurement harness. No leak-free claim.',
        evidence=dict(performance=str(args.performance),stability=str(args.stability),volume=str(args.volume),handoff=str(handoff),start_stop=str(startcheck)),changed_files=changed)
    (folder/'results.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    counts=system['totals'];perf_table='\n'.join(row(direction.title()+' virtual control -> DOM',perf['performance']['200'][direction]['control_to_dom_ms']) for direction in ('occupied','available'))
    post_table='\n'.join(row(direction.title()+' observed confirmed Serial -> DOM',perf['performance']['200'][direction]['observed_confirmed_serial_to_dom_ms']) for direction in ('occupied','available'))
    boundary_table='\n'.join(row(direction.title()+' / '+metric,perf['performance']['200'][direction][metric]) for direction in ('occupied','available') for metric in ('simulated_confirmation_ms','control_to_serial_ms','publish_to_receive_ms','validation_transaction_ms','commit_to_dom_ms','api_fetch_parse_ms','dom_build_ms'))
    memory_table='\n'.join('| '+role+' | '+' | '.join(f'{values[k]/1048576:.1f}' for k in ('first_bytes','last_bytes','maximum_bytes'))+' |' for role,values in memory.items())
    suites='\n'.join('| '+s['name']+' | '+' | '.join(str(sum(c[k] for c in s['counts'])) for k in ('passed','failed','errors','skipped'))+' |' for s in system['suites'])
    text=f'''# Final technical audit: local three-bay virtual-sensor prototype

Technical integration handover, 12 November 2026 (Asia/Shanghai). This is project code validation, not an academic report. All evidence paths retain UTC timestamps. No commits, pushes, deployment, public exposure or teammate source changes were made.

## Architecture and verified scope

```text
ONE Wokwi ESP32 + three independent measured HC-SR04 instances
  -> new browser Serial observations (not capture-file input)
  -> per-source durable SQLite outbox
  -> actual loopback TCP MQTT, QoS 1, retain false
  -> reference subscriber validates -> atomic SQLite transaction
  -> application commit ACK -> outbox marks delivered
  -> read-only API -> real Edge Overview / Admin
```

Mapping and GPIO: 1001/A01 TRIG5 ECHO18; 1002/A02 TRIG19 ECHO21; 1003/A03 TRIG22 ECHO23. Thresholds remain 120/220 mm, timeout 25 ms, occupied confirmation 1500 ms, free confirmation 2500 ms. Heartbeats and 8-bit counters are independent. Battery 3600 mV is a placeholder. There is no magnetic fusion or physical hardware test.

The six JSON fields remain spot_id, occupied, batt_mv, status, ctr and heartbeat. Separate EVENT diagnostics expose firmware simulation-clock confirmation time without inventing source UTC. The backend keeps source_timestamp NULL and records host receipt UTC separately. Topics carry bridge UUID/Serial index delivery identity, never use the rolling counter as a UUID. Current disconnected/untrusted status becomes Unknown; last-known occupancy is retained separately. Replay, memory MQTT, reference capture MQTT, original single-bay live and original frontend Simulation modes remain independent. Multi mode has no implicit replay fallback.

## Regression and browser verification

Final complete regression: **{counts['passed']} passed, {counts['failed']} failed, {counts['errors']} errors, {counts['skipped']} skipped**. All original 247 tests are included. The earlier interrupted-workflow run completed with 254/0/0/0; the later denied-SUBACK test is included in this fresh final run.

The first resumed full run, `system-20261111T185541768436Z`, recorded **254 passed, 1 failed, 0 errors, 0 skipped**. Its three-channel MQTT test could publish before initial untrusted health had been superseded at the subscriber; a late startup health message correctly cleared freshness. The fixture now waits for actual subscribed online health before injecting events. Occupancy, persistence and freshness assertions remain unchanged. That failed evidence is preserved; the final counts above are from a subsequent complete rerun.

| Suite | Passed | Failed | Errors | Skipped |
| --- | ---: | ---: | ---: | ---: |
{suites}

Supplementary preserved runs: final controlled performance 1 passed; extended performance/stability 1 passed; high-volume transport 1 passed, each with zero failed/cancelled/skipped (volume zero errors). These are separate scenario executions, not inflated per-assertion counts. [Full regression results]({link(args.system)}), [final machine-readable audit]({link(folder/'results.json')}).

Actual Microsoft Edge verifies independently changing A01/A02/A03, concurrent transitions, real virtual ECHO failure, unknown/last-known separation, Dashboard/Admin consistency, history filters, API failure/recovery, responsive layout, broker outage, backend restart and persisted rows. Root launcher start, browser check, graceful stop with all three children exit 0, restart on the same ports and second real-browser check are recorded in [start/stop evidence]({link(startcheck/'session.json')}) and [restarted handoff]({link(handoff/'browser-check.json')}). No physical or direct ESP32 MQTT acceptance claim is made.

## Performance: 30 Occupied and 30 Free trials

Final instrumented run: [raw trials]({link(args.performance/'trials.json')}), [statistics]({link(args.performance/'results.json')}). Each direction has n=30 at 200 ms Dashboard polling, distributed across all three bays, with 0/30 propagation failures (15-second observation timeout). p95 uses nearest rank. Durations below are milliseconds.

| Metric | Minimum | Median | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
{perf_table}
{post_table}

The first metric begins immediately before the browser sets the virtual distance control and ends after the Dashboard DOM contains the matching committed event ID. It includes virtual measurement/debounce and all host processing. The second begins when the bridge observes the already-confirmed Serial JSON on the host; it excludes any earlier simulated UART/browser rendering delay. Exact firmware-confirmation-to-host elapsed time cannot be obtained by subtracting unsynchronized firmware millis from host UTC. DOM completion is measured, not display paint or physical sensing latency. Physical end-to-end latency remains unverified.

There were **{target_misses['occupied']}/30 Occupied and {target_misses['available']}/30 Free observations over 3000 ms**. These target exceedances are distinct from propagation failure. No universal three-second compliance is claimed.

Boundary evidence separates the main contributors:

| Boundary | Minimum | Median | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
{boundary_table}

The historical 3136 ms sample was a Free transition and necessarily included its configured 2500 ms debounce. Historical instrumentation cannot attribute its remaining 636 ms exactly. Current firmware-clock confirmation deltas, host Serial observation, publish/receive, transaction commit, HTTP fetch/parse and DOM-build times show debounce dominates Free latency; MQTT/SQLite/DOM building are small contributors in this sample. Validation/transaction timing includes locking and durable SQLite work, not an isolated disk benchmark. commit-to-DOM combines polling wait, HTTP and DOM work; commit-to-poll-start can be negative when a request was already in flight at commit. Host wall-clock cross-process timings are distinct from firmware simulation-clock deltas.

At the preserved 500 ms comparison cadence (n=9 per direction), control-to-DOM medians were {perf['performance']['500']['occupied']['control_to_dom_ms']['median_ms']:.2f} ms Occupied and {perf['performance']['500']['available']['control_to_dom_ms']['median_ms']:.2f} ms Free. At 200 ms (n=30) they were {perf['performance']['200']['occupied']['control_to_dom_ms']['median_ms']:.2f} and {perf['performance']['200']['available']['control_to_dom_ms']['median_ms']:.2f} ms. This observed improvement is consistent with reduced polling quantization. These are sequential, unequal-size local samples with background test load, not a randomized benchmark or population-level guarantee. busy guards prevent overlapping polls; debounce and integrity checks are unchanged. Default requests increase from about 2 to 5 per second per tab, a deliberate local-demo tradeoff.

## Bounded stability, memory and high volume

The extended run lasted {stability['duration_seconds']:.3f} seconds including online compiler/startup and controlled trials, with {stability['soak_seconds']:.3f} seconds in its dedicated stability phase. It observed {stability['observed_live_serial_events']} live Serial events, {stability['heartbeat_events']} heartbeats and {stability['committed_distinct_keys']} distinct committed keys. Missing observed events: {stability['missing_observed_events']}; SQLite integrity: {stability['integrity']}; transport retry records: {stability['retries']}. Real broker interruption/reconnect and backend process restart were exercised during the same source session. [Stability evidence]({link(args.stability/'stability.json')}), [resource samples]({link(args.stability/'resource-samples.json')}), [screenshot]({link(args.stability/'stability-dashboard.png')}).

| Process role | Initial RSS MiB | Final RSS MiB | Peak RSS MiB |
| --- | ---: | ---: | ---: |
{memory_table}

The Node runner combines the live browser bridge, Playwright transport, full Serial DOM polling, metric arrays and test log parsing; it is not the browser Dashboard process. Its material RSS growth is unresolved. Sampled heap used started at {resources[0]['runner_memory']['heapUsed']/1048576:.1f} MiB, peaked at {max(r['runner_memory']['heapUsed'] for r in resources)/1048576:.1f} MiB and ended at {resources[-1]['runner_memory']['heapUsed']/1048576:.1f} MiB. That decline shows allocation/GC and reserved heap contribute, but no heap-retention profile proves the absence of a leak. Backend/broker/worker RSS stayed near their initial ranges in this bounded sample; backend and broker role samples span intentional process restarts, not a single continuous PID lifetime. This does not establish long-term memory stability. Edge child-tree RSS was not measured. Serial history and evidence logs grow with run length; do not treat this as an hours/days endurance qualification. Restart between bounded demonstrations.

Database-family sampled bytes (including transient WAL/SHM): initial {resources[0]['database_bytes']}, final {resources[-1]['database_bytes']}, peak {max(r['database_bytes'] for r in resources)}. These are race-tolerant sampled file sizes, not atomic disk-accounting snapshots. Durable event/history growth is expected; production retention is not implemented.

The separate [volume test]({link(args.volume/'volume.json')}) uses explicitly HARNESS-GENERATED messages, not sensor measurements: {volume['generated']} transmitted through actual MQTT/outbox/backend, {volume['accepted']} accepted rows, {volume['duplicate_deliveries']} duplicate deliveries without added event rows, {volume['rejected']} malformed/out-of-order rejections, zero missing accepted events, integrity ok. Each bay processes 300 frames, crosses counter wrap and ends at ctr43. {len(volume['resource_samples'])} resource samples were collected. An initial volume attempt passed transport assertions but its resource monitor died while a WAL/SHM file disappeared; that incomplete monitoring evidence is retained at volume-20261111T161943586162Z and is not used to claim memory stability. File sampling was fixed and the monitored test rerun successfully.

## Reviewed fixes and safety boundaries

- Malformed health arrays/nulls and bad field types now reject before state mutation; oversized MQTT payloads reject. A real-MQTT regression confirms the subscriber still accepts a subsequent valid event.
- Malformed commit ACK shapes, missing/invalid event identities and unknown outcomes cannot complete pending deliveries or crash the callback. Accepted/duplicate ACKs require a positive integer event ID.
- Denied SUBACK does not declare the publisher connected. Failed initial connection cleans up its MQTT loop.
- Optional backend/outbox text-journal failure cannot kill workers after a durable transaction; injected-error tests preserve commit/ACK behavior. Database errors still fail closed; this is not storage-failure auto-recovery.
- WAL/SHM disappearance during resource sampling is handled; monitoring must actually collect samples and remain alive.
- Instrumentation adds host and simulation-clock boundaries separately; 200 ms UI polling improves sampled response without weakening 1500/2500 ms debounce.

Transactions atomically update accepted history, current state, receipt/checkpoint and dedup identity. MQTT application ACK follows commit. Per-bay workers preserve ordering; repeated delivery identity deduplicates across non-adjacent retries. Conflicting identity and stale/missing-next-counter events reject. Counter wrap itself is valid and not globally unique. Existing database-restart, rollback, lost-ACK and outbox-restart tests pass. Missing data before the bridge observes Serial cannot be recovered by this protocol; observed-event consistency is the tested boundary, not an absolute delivery guarantee across arbitrary firmware/browser failures.

All required services bind 127.0.0.1. Read-only APIs, parameterized SQL, bounded history queries, local topic namespace checks, no-store/no-sniff/CSP remain in place. The isolated code contains no configured production credentials. There is no production authentication, authorization, TLS, broker ACL design, rate-limit/security certification, backup/retention policy or deployment acceptance. This is not production-secure. Original frontend Git remains clean and protected original firmware/capture hashes match the pre-existing evidence.

Admin current-status diagnostics use the latest persisted state. Its history table displays the first API page (up to 50 events, reversed for display), not an unlimited rolling recent-event feed. Later history is available through `/api/events?after=<last_id>&limit=50` and optional spot_id filtering; there is no UI pagination control. This existing limitation is retained rather than adding a new feature during code freeze.

## Reproducible demonstration and shutdown

Dependencies remain the existing Python/Node/Paho/Aedes/Playwright/Microsoft Edge installation; live Wokwi needs access to its online compiler/UI. Run from the workspace root:

```powershell
Set-Location D:\\Smart-Parking-System
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\Start-LocalDemo.ps1 -Mode Multi
```

Open http://127.0.0.1:8780/backend/. Wait for 3/3 online; all bays are Unknown until valid sourced observations arrive. Select each HC-SR04 in the interactive Wokwi window: 10 cm produces Occupied, 35 cm produces Available after unchanged debounce. Check Admin mapping, latest ctr/heartbeat and persisted history. Fault switches independently ground ECHO and make that bay Unknown while preserving labeled last-known state. The currently verified handoff directory is `{link(handoff)}`; it uses a fresh stream within the existing multi-demo.sqlite3 file without overwriting older rows.

Stop the current handoff:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\Stop-LocalDemo.ps1 -SessionDirectory .\\{str(handoff.relative_to(ROOT))}
```

For a subsequent launcher, use its printed session directory or Ctrl+C. Restart with the simple startup command to create a fresh manifest and firmware namespace; do not reuse an existing session manifest. Ports 8780/18890 are checked; unrelated listeners are never killed. Other modes require their explicit Mode selection and separate ports or a stopped instance.

Reproduce verification (the first command includes all 247 original tests plus final regressions):

```powershell
& 'python' integration-validation/demo/run_system_checks.py
& 'python' integration-validation/demo/multi/run_performance.py --rounds 10 --soak-seconds 180
& 'python' integration-validation/demo/multi/run_volume.py
```

Every command creates a new evidence directory. Existing captures/databases/results are preserved. Source SHA-256 fingerprints are saved in [{link(folder/'source_sha256.json')}]({link(folder/'source_sha256.json')}); this is a local reproducibility manifest, not a Git commit or immutable release.

## Exact files created or changed since the 247-test handoff

'''+ '\n'.join('- `'+p+'`' for p in changed)+f'''

New per-run evidence files are contained in the linked evidence directories; they are generated artifacts, not modifications to old results. The regenerated diagram is content-identical to the previous three-sensor layout. Existing startup/stop scripts were verified, not rewritten in this stabilization pass.

## Final assessment and remaining blockers

Ready for a reproducible, bounded local three-bay **virtual-sensor** demonstration with the stated memory/runtime limits. Not production-ready. Remaining blockers are Saaket's absent backend/database/API implementation, physical ESP32/HC-SR04 tests, direct ESP32 MQTT networking, long-duration Node/Edge memory profiling, production identity/auth/TLS/ACLs, monitoring, retention/backups and deployment verification. No physical accuracy, physical-to-web latency, universal three-second response or production exactly-once guarantee is claimed. The reference backend and live browser Serial bridge must retain those labels.
'''
    audit=ROOT/'FINAL_TECHNICAL_AUDIT.md'
    if audit.exists():shutil.copy2(audit,folder/'FINAL_TECHNICAL_AUDIT.before.md')
    audit.write_text(text,encoding='utf-8')
    readme=ROOT/'INTEGRATION_DEMO_README.md';shutil.copy2(readme,folder/'INTEGRATION_DEMO_README.before.md')
    intro=f'''# Final stabilization handover — 12 November 2026

Latest full regression: **{counts['passed']} passed, {counts['failed']} failed, {counts['errors']} errors, {counts['skipped']} skipped**. All original 247 tests remain included. Final code, evidence, measured boundary timings and exact changed files are in [FINAL_TECHNICAL_AUDIT.md](FINAL_TECHNICAL_AUDIT.md); [machine-readable results]({link(folder/'results.json')}). No teammate source or previous test/database evidence was overwritten.

At 200 ms polling, 30 trials per direction: Occupied median **{perf['performance']['200']['occupied']['control_to_dom_ms']['median_ms']:.1f} ms**, p95 **{perf['performance']['200']['occupied']['control_to_dom_ms']['p95_ms']:.1f} ms**; Free median **{perf['performance']['200']['available']['control_to_dom_ms']['median_ms']:.1f} ms**, p95 **{perf['performance']['200']['available']['control_to_dom_ms']['p95_ms']:.1f} ms**. Zero propagation failures; **{target_misses['available']}/30 Free trials exceeded 3000 ms**, so no general three-second compliance claim. Debounce remains 1500/2500 ms. Observed confirmed Serial-to-DOM latency is reported separately from distance-control latency; physical latency is unverified.

Extended bounded live run: {stability['observed_live_serial_events']} observed events = {stability['committed_distinct_keys']} committed keys, {stability['heartbeat_events']} heartbeats, zero missing observed events through broker/backend recovery; dedicated soak {stability['soak_seconds']:.1f} seconds. Separate real-MQTT synthetic stress: 900 accepted messages, 3 duplicates, 6 invalid/stale rejections. Node browser-driver RSS grew materially; leak-free long-duration operation is not established. The audit records measured RSS ranges and the monitoring limitation/fix.

Current handoff: **http://127.0.0.1:8780/backend/**. Reproducible startup:

```powershell
Set-Location D:\\Smart-Parking-System
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\Start-LocalDemo.ps1 -Mode Multi
```

Stop the running verified handoff before restarting:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\Stop-LocalDemo.ps1 -SessionDirectory .\\{str(handoff.relative_to(ROOT))}
```

The interactive Wokwi window measures three virtual HC-SR04 sources; this is not capture replay, physical sensing, direct ESP32 MQTT or Saaket's backend. All previous modes remain explicitly selectable. The remainder preserves the earlier setup details and evidence; earlier "latest" counts/session descriptions are historical.

---

'''
    readme.write_text(intro+readme.read_text(encoding='utf-8'),encoding='utf-8')
    source_files=source_paths()
    hashes={link(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(source_files))}
    (folder/'source_sha256.json').write_text(json.dumps(dict(created_at_utc=datetime.now(timezone.utc).isoformat(),files=hashes),indent=2),encoding='utf-8')
    print(json.dumps(dict(evidence=str(folder),regression_counts=counts,technical_audit=str(audit)),indent=2))

if __name__=='__main__':main()
