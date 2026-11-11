> Publication copy: host-specific paths and archived evidence links are sanitized. Start with [README.md](README.md) for fresh-clone setup. Original local documents and evidence are preserved.

# Final stabilization handover — 12 November 2026

Latest full regression: **255 passed, 0 failed, 0 errors, 0 skipped**. All original 247 tests remain included. Final code, evidence, measured boundary timings and exact changed files are in [FINAL_TECHNICAL_AUDIT.md](FINAL_TECHNICAL_AUDIT.md); [machine-readable results](docs/verification-summary.json). No teammate source or previous test/database evidence was overwritten.

At 200 ms polling, 30 trials per direction: Occupied median **1861.4 ms**, p95 **1971.5 ms**; Free median **2902.3 ms**, p95 **3038.8 ms**. Zero propagation failures; **6/30 Free trials exceeded 3000 ms**, so no general three-second compliance claim. Debounce remains 1500/2500 ms. Observed confirmed Serial-to-DOM latency is reported separately from distance-control latency; physical latency is unverified.

Extended bounded live run: 199 observed events = 199 committed keys, 77 heartbeats, zero missing observed events through broker/backend recovery; dedicated soak 184.4 seconds. Separate real-MQTT synthetic stress: 900 accepted messages, 3 duplicates, 6 invalid/stale rejections. Node browser-driver RSS grew materially; leak-free long-duration operation is not established. The audit records measured RSS ranges and the monitoring limitation/fix.

Current handoff: **http://127.0.0.1:8780/backend/**. Reproducible startup:

```powershell
Set-Location D:\Smart-Parking-System
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-LocalDemo.ps1 -Mode Multi
```

Stop the running verified handoff before restarting:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Stop-LocalDemo.ps1 -SessionDirectory .\integration-validation\demo\evidence\stabilization-handoff-20261112
```

The interactive Wokwi window measures three virtual HC-SR04 sources; this is not capture replay, physical sensing, direct ESP32 MQTT or Saaket's backend. All previous modes remain explicitly selectable. The remainder preserves the earlier setup details and evidence; earlier "latest" counts/session descriptions are historical.

---

# Three-bay local virtual-sensor demonstration

Current implementation: **three independently measured Wokwi HC-SR04 sensors on one simulated ESP32**, live Serial browser bridge, durable outbox, real loopback TCP MQTT, reference backend, SQLite, API and responsive Overview/Admin Dashboard. This is a virtual-sensor prototype; it is not physical hardware or Saaket's production backend. Multi mode never reads a saved capture.

## Start and stop

From Windows PowerShell, keep the first terminal open:

```powershell
Set-Location D:\Smart-Parking-System
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-LocalDemo.ps1 -Mode Multi
```

Open **http://127.0.0.1:8780/backend/** (also `/` and `/admin/`). A separate interactive Edge window runs Wokwi. Services can be ready before the online Wokwi compiler has finished: all bays correctly remain Unknown until observations arrive. Select each HC-SR04, then adjust its distance: 10 cm becomes Occupied; 35 cm becomes Available after debounce. A02 starts at 10 cm; A01/A03 start at 350 cm. These are virtual sensor input settings, not frontend occupancy cycles. Changing one source leaves the others independent. `-Headless -DemoCycle` changes the three actual virtual controls automatically; it does not replay a file.

Stop with Ctrl+C in the launcher terminal. Alternatively use the **exact session directory printed by startup**:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Stop-LocalDemo.ps1 -SessionDirectory '<printed session directory>'
```

The supervisor checks dependencies and ports, records owned child PIDs, waits for service readiness, fails on child exit, and gracefully stops its own bridge/backend/broker. It never kills unrelated listeners. Use new ports with `-BrokerPort 18891 -HttpPort 8781` if defaults are occupied. To select an explicit NEW evidence directory, use `-SessionDirectory .\integration-validation\demo\evidence\my-new-session`. Do not reuse an existing manifest. The default Multi database is `integration-validation/demo/local_stack/data/multi-demo.sqlite3`; older single-bay databases remain intact. Each new firmware run uses a fresh namespace in the database; history persists without mixing restarted 8-bit counters. Persistence/restart within the same running source session is tested separately.

Independent previous modes remain available through explicit `-Mode Live` (original single-bay live bridge), `Reference -SeedCapture` (persisted 22-event captured replay over MQTT), `Memory -SeedCapture` (memory MQTT replay), `Replay` (browser-controlled capture replay), and `Simulation` (original teammate frontend). They are separate launcher modes; `/simulation/` is provided by Simulation/legacy modes rather than by the new Multi HTTP handler. Use different ports or stop the current owned session first. No mode silently substitutes replay for live measurements.

## Dependencies and reproducible checks

Tested: Windows PowerShell, Python 3.14.7, Node 24.22.1, Microsoft Edge 157, Playwright 1.65, Paho MQTT 2.1 and Aedes 1.2. Existing local dependencies are reused. For a fresh checkout:

```powershell
& 'python' -m pip install --target integration-validation/demo/mqtt/vendor -r integration-validation/demo/mqtt/requirements.txt
npm --prefix integration-validation/demo/mqtt ci
npm --prefix integration-validation/demo/browser ci
& 'python' integration-validation/demo/run_system_checks.py
```

Use `-PythonPath` on the launcher if Python is installed elsewhere. Edge must be installed. Wokwi live verification additionally requires access to its website/compiler and browser UI; the local Dashboard assets do not require external fonts/CDNs. Full verification runs Python/C++/JavaScript/real-browser/real-broker tests, including all original 230 tests. `--without-live` deliberately reports live stages NOT RUN and cannot establish complete verification. New focused commands are `python integration-validation/demo/multi/run_checks.py` and `python integration-validation/demo/multi/run_browser.py` with the same real interpreter. Firmware can be regenerated with `python integration-validation/demo/multi/build_firmware.py`.

## Firmware and contract

| Bay | spot_id | TRIG | ECHO | HC-SR04 | ECHO fault switch |
| --- | --- | --- | --- | --- | --- |
| A01 | 1001 | GPIO 5 | GPIO 18 | ultrasonic1 | fault1 |
| A02 | 1002 | GPIO 19 | GPIO 21 | ultrasonic2 | fault2 |
| A03 | 1003 | GPIO 22 | GPIO 23 | ultrasonic3 | fault3 |

Each source runs ultrasonic trigger/echo measurement, 25 ms timeout, occupied threshold 120 mm, free threshold 220 mm, 1.5 s occupied/2.5 s free confirmation and independent 5 s heartbeat/8-bit counter. The band between thresholds retains confirmed occupancy. Invalid ECHO readings change trust/health and make the current Dashboard state Unknown; last-known occupancy is separately retained. The virtual switch's left position connects ECHO and right position grounds that source's GPIO, producing a real **simulated measurement timeout**. No magnetic source or fusion is claimed. `batt_mv=3600` remains a placeholder, not a measured battery.

Serial messages retain `spot_id`, `occupied`, `status`, `batt_mv`, `ctr`, `heartbeat`. Firmware has no UTC timestamp: database source timestamps remain NULL; host observation and receipt times are explicitly distinct. MQTT namespaces are isolated per launcher session; each bay has its own source state and serial delivery identity. [Production interface and exact contracts](integration-validation/demo/multi/PRODUCTION_INTERFACE.md) documents topic format, API pagination, schema, health expiration, missing production interfaces, timestamp policy and recovery limits.

The new UI shows current counts, each source's latest received message/time, status and health; Admin adds numeric mapping, source diagnostics, counters, heartbeat, pending deliveries, filtered history and rejected/duplicate receipts. Backend or broker failure makes current occupancy Unknown, retaining labeled last-known observations. It never counts an unsourced bay as Available. Desktop/mobile layouts were checked in actual Edge.

## Reliability and evidence

The bridge persists each newly observed Serial event before forwarding. Per-bay workers publish QoS 1 and wait for an acknowledgement emitted **after the SQLite transaction commits**. Transactional delivery keys suppress even non-adjacent retries; an 8-bit counter alone is never used as a unique event ID. Counter wrap, inconsistent duplicate counters, malformed messages and ordering are covered by automated checks. One paused channel does not block the others. Backend restart preserves state/history; broker disconnect makes all current states Unknown and queued live observations recover after reconnect. Pending-outbox restart uses its original file and namespace; new launcher sessions intentionally create a new firmware session rather than resuming an arbitrary old browser.

The comprehensive three-bay Edge test verifies: initially unsourced Unknown; three actual virtual sources; independent and overlapping distance transitions; hysteresis; actual A02 ECHO fault and recovery; A02 forwarding pause with other bays online; backend process restart and history persistence; broker stop/start with durable backlog; source JSON versus SQLite rows; API/DOM consistency; Admin filter; desktop/mobile overflow; API failure and recovery. The scenario is counted as ONE test, not as many assertions.

Initial consolidated run `system-20261111T145651070540Z`: **246 passed, 1 failed, 0 errors, 0 skipped**. The older single-bay browser test sampled the occupancy event before the independent health update had arrived. Its wait now requires both expected persisted occupancy and fresh health; assertions remain intact. Failed run evidence is preserved. Final rerun results and timings are recorded below and in `integration-validation/demo/multi/FINAL_AUDIT.json`.

Final full rerun: **247 passed, 0 failed, 0 errors, 0 skipped**, recorded in [consolidated results](docs/verification-summary.json). This includes all original 230 tests, 15 new multi-source contract/transport/database tests, one added multi-source startup test and one comprehensive multi-source real Edge scenario. The additional handoff browser check is evidence, not added to that test count.

| Suite | Passed | Failed / errors / skipped |
| --- | ---: | --- |
| Original validation / replay Python / JavaScript | 103 | 0 / 0 / 0 |
| MQTT transport | 18 | 0 / 0 / 0 |
| Backend / SQLite | 26 | 0 / 0 / 0 |
| Sensor Python / compiled C++ | 30 | 0 / 0 / 0 |
| Replay / MQTT / backend Edge | 26 | 0 / 0 / 0 |
| Single-source live contract Python / JavaScript | 19 | 0 / 0 / 0 |
| Multi-source contract / transport / SQLite | 15 | 0 / 0 / 0 |
| Single-source live Edge end-to-end | 1 | 0 / 0 / 0 |
| PowerShell startup / shutdown / failure checks | 8 | 0 / 0 / 0 |
| Three-source live Edge end-to-end | 1 | 0 / 0 / 0 |

[Three-bay browser proof](docs/verification-summary.json) records **9/9 known virtual-input observations matching expectations**, 26 persisted delivery keys and SQLite integrity `ok`. This small virtual sample does not estimate physical accuracy. Normal browser-control-to-Dashboard timings were **1738, 1877 and 3136 ms** (n=3). Two deliberately broker-interrupted trials took **9644 and 9300 ms**, including the injected outage. Measurement begins immediately before setting the virtual distance control and ends when the matching Dashboard DOM state is observed; it includes debounce, browser polling and local transport. No three-second guarantee or physical-to-web latency is claimed.

Screenshots: [Overview desktop](docs/EVIDENCE.md), [concurrent updates](docs/EVIDENCE.md), [independent A02 ECHO failure](docs/EVIDENCE.md), [Admin diagnostics](docs/EVIDENCE.md), [mobile Overview](docs/EVIDENCE.md). Journals, live Serial observations, real broker traffic, backend records and SQLite files accompany those images. [Machine-readable final audit](integration-validation/demo/multi/FINAL_AUDIT.json) links each suite and confirms protected source/capture hashes and clean teammate frontend Git status.

Final interactive handoff was started using:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-LocalDemo.ps1 -Mode Multi -SessionDirectory D:\Smart-Parking-System\integration-validation\demo\evidence\multi-handoff-20261111-final
node integration-validation/demo/local_stack/verify_stack.cjs integration-validation/demo/evidence/multi-handoff-20261111-final/session.json
```

Real Edge verified the running launcher instance at **http://127.0.0.1:8780/backend/** with all three sources online: A01 Available, A02 Occupied, A03 Available, from newly emitted live virtual-sensor messages. [Handoff browser check](docs/verification-summary.json) and [Admin screenshot](docs/EVIDENCE.md) are saved. This is ready for a local virtual-sensor demonstration; process survival after the coding session depends on the host. Stop this exact instance with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Stop-LocalDemo.ps1 -SessionDirectory D:\Smart-Parking-System\integration-validation\demo\evidence\multi-handoff-20261111-final
```

After shutdown, restart with the simple `-Mode Multi` command above, which creates a fresh evidence directory automatically; do not reuse the final handoff manifest directory.

Other demonstrated fixes: explicit C++ declaration for the new multi-source firmware; Wokwi selection/popover handling when changing different sensors; routine Playwright tracing disabled by default after an older long-running single-bay session exhausted C: temporary storage. Bounded tests can explicitly trace. That old interrupted trace was not successfully finalized; preserved Serial journals, databases and prior finalized evidence are not claimed lost or overwritten. Initial failed probe/browser runs remain in evidence directories.

## Remaining limits

Saaket's implementation is absent; this is an isolated reference backend. Direct simulated ESP32-to-local MQTT is not verified: the tested Wokwi public gateway cannot reach the Windows loopback broker. The verified path uses newly observed browser Serial data and a local MQTT client. Official [Wokwi gateway documentation](https://docs.wokwi.com/guides/esp32-wifi) describes private gateway local access; [VS Code project configuration](https://docs.wokwi.com/vscode/project-config) describes its private gateway and optional RFC2217 Serial forwarding. Those alternatives require an available setup and were not installed or verified. No public broker, tunnel, deployment or public listener was created.

Physical sensing, sensor placement/cross-talk, physical ESP32 power/wiring, device credentials, TLS, authentication/authorization, broker ACLs, production migrations, operational monitoring, backups/retention and deployment acceptance remain unverified/missing. All services are loopback. Read-only API, self-only CSP and no-sniff headers improve the local boundary but do not establish production security. Virtual test correctness and browser-control-to-DOM timings are not physical accuracy or physical-to-web latency. Eight-second per-source freshness is based on current bridge traffic, never on dates inside an old saved capture. Abrupt process loss, disk failure or missed browser Serial segments are not covered by an exactly-once promise.

## Files created or modified in this continuation

Created under `integration-validation/demo/multi/`: `build_firmware.py`, `firmware/sketch.ino`, `firmware/diagram.json`, `probe_sensors.cjs`, `model.py`, `outbox.py`, `bridge.cjs`, `run_live.cjs`, `server.py`, `web/index.html`, `web/dashboard.css`, `web/dashboard.js`, `test_multi.py`, `run_checks.py`, `browser_fixture.py`, `browser.test.cjs`, `run_browser.py`, `audit.py`, `PRODUCTION_INTERFACE.md`, `COMPLETION.md`, `.gitignore` and generated `FINAL_AUDIT.json`.

Modified: root `Start-LocalDemo.ps1`, `INTEGRATION_DEMO_README.md`; `demo/live/bridge.cjs`, `demo/live/verify_live.cjs`; `demo/local_stack/supervisor.py`, `managed_backend.py`, `verify_stack.cjs`, `test_startup.py`; `demo/run_system_checks.py`. Paths prefixed `demo/` here are under `integration-validation/`. New evidence directories contain logs, SQLite snapshots, JSON results and screenshots; existing evidence remains. No teammate frontend/firmware source, academic report, commit or remote repository was changed.


---

# Historical implementation milestones (earlier modes and evidence)

The following sections preserve earlier implementation details. Current default startup, UI and limitations are described above. Earlier running-session descriptions are historical; use the current launcher.

# Local Wokwi capture → frontend integration demo

Implemented and checked on 11 November 2026 in `D:\Smart-Parking-System`.
Four integration paths are available: saved-file replay, memory-based MQTT,
persisted MQTT capture replay, and **live Wokwi Serial → MQTT → reference backend
→ SQLite → Dashboard**. No physical ESP32 or physical sensor is used. The original
frontend simulation also remains.
Previous single-bay verification: **230 passed, 0 failed, 0 errors, 0 skipped**.
The managed live demo is running at **http://127.0.0.1:8780/backend/**. Its Wokwi
window is interactive: select HC-SR04 and change the distance to 10 cm / 35 cm.
This live path reads newly emitted Serial data, not a saved capture. Direct
simulated-ESP32 Wi-Fi MQTT remains blocked by the tested public gateway.

One-command startup from this directory (reuse the running demo or stop it first):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-LocalDemo.ps1 -Mode Live
```

For the full consolidated test workflow:

```powershell
& 'python' integration-validation/demo/run_system_checks.py
```

See **Five-stage completion and final technical audit** at the end for shutdown,
dependencies, evidence, limitations and the exact changed-file list. Earlier
sections below retain historical milestones and their original evidence.
Actual Wokwi HC-SR04 trigger/echo readings and distance-driven transitions are now
verified in an isolated firmware variant. Direct simulated ESP32 → Windows MQTT
remains unavailable through the tested public gateway; see the final section.
Persistent backend UI: **http://127.0.0.1:8767/backend/**; see the final section
for its installation, schema, API contracts, evidence and restart commands.
No university report, slides or video were edited.

## Installation and restart (Windows PowerShell)

Prerequisites: Python 3 (tested with 3.14.7), Node.js (tested with v24.22.1;
needed for MQTT broker and browser tests), and Git if the frontend checkout is missing.
The direct-file replay needs no pip or npm packages. MQTT dependencies and commands
are specified in the local MQTT section below. Optional real-browser tests use
Playwright installed in `integration-validation/demo/browser/` and Microsoft Edge.

The frontend is already cloned at `smart-parking-web`, commit
`9546209475df899161187155fc3d6deab822eece`. Its Git status was clean after
implementation. No frontend files were edited, committed, pushed or deployed.
If setting up a different workspace, clone it once:

```powershell
Set-Location D:\Smart-Parking-System
git clone https://github.com/hxnwls/smart-parking-web.git smart-parking-web
```

Start or restart in a terminal; keep the terminal running:

```powershell
Set-Location D:\Smart-Parking-System
& 'python' integration-validation/demo/server.py
```

On another machine, `py -3 integration-validation/demo/server.py` can replace the
absolute Python executable. The Windows Store `python`/`py` aliases could not run
inside this workspace's sandbox; the actual interpreter above worked.

Open **http://127.0.0.1:8765/**. Replay starts paused with three Unknown bays.
Click **Play / Pause** to advance one saved event per second, or use **Next event**
to inspect individual records. **Reset** returns to no captured data. Each browser
tab has an independent cursor. At completion, the last observed state is held;
Play starts another replay. Stop the server with Ctrl+C before restarting.
If port 8765 is already in use, reuse the running demo or stop its owning terminal;
`--port 8766` is also supported (the Node HTTP test currently expects port 8765).

The server was started during implementation. Process persistence after the coding
session depends on the host; use the restart command if the URL stops responding.

**Simulation fallback:** http://127.0.0.1:8765/simulation/ serves the original
frontend unchanged, labelled Simulation Mode. It does not consume the capture.
There is no automatic switch from evidence replay to synthetic data.

## Architecture and original frontend behavior

```text
captures/wokwi_serial_actual.txt (existing, read only)
    → existing wokwi_serial_adapter.validate_capture
    → demo/server.py: ordered, validated snapshots + explicit ID mapping
    → GET /api/replay?count=N (same-origin local HTTP)
    → demo/integration.js
    → original dashboard renderer, original CSS and tab navigation
       + capture-specific Admin View
```

The Python standard-library HTTP server binds only to `127.0.0.1`.
It reads the capture at startup and rejects malformed/schema-invalid messages,
invalid status bits, counter discontinuities, contradictory heartbeat transitions,
duplicates and unmapped IDs using the existing adapter. It does not silently
repair, reorder or substitute bad input. Restart after changing the capture.
HTTP requests only select a bounded prefix of that file; they do not ingest events.

The original app initially shows A01 Available, A02 Occupied and A03 Unknown.
Every five seconds its synthetic timer refreshes online timestamps; A01 toggles
every ten seconds and A02 every fifteen seconds. Offline overrides occupancy to
Unknown. Admin View shows bay, status, Online/Offline and browser-local last update.
The original CSS provides green/red/grey status cards and responsive layout.
These initial statuses, Admin rows and a simulated transition were exercised in
the JavaScript DOM harness. The original page and assets also returned HTTP 200.

For replay, the server transforms the original HTML in memory, serves the original
JavaScript up to its initialization marker as `/base.js`, and loads the isolated
adapter. This preserves original rendering and navigation while disabling its
synthetic initialization/timer. The adapter clears synthetic defaults before any
asynchronous request and renders the explicit Unknown state immediately.
Admin View replaces the original connection/timestamp claims with capture evidence.

## Message contract and mapping

| Field | Source contract and demo use |
|---|---|
| `spot_id` | uint32; explicitly mapped to bay label, never treated as array index |
| `occupied` | strict JSON boolean; drives Available/Occupied |
| `batt_mv` | uint16; displayed as recorded millivolts |
| `status` | integer 0..7; adapter checks source-specific occupied/fault/low-battery bits |
| `ctr` | uint8, global to node/session, increment modulo 256; not an event identity |
| `heartbeat` | strict boolean; accepted heartbeats refresh captured metadata without creating an occupancy transition |

Mapping in `demo/server.py`: **1001 → A01, 1002 → A02, 1003 → A03**.
Only 1001 occurs in the supplied file. A02/A03 remain Unknown with “No captured
data”; no network outage is inferred for them. Additional IDs require an explicit
mapping change. The adapter respects BOOT markers when resetting counter history.

Replay states are based solely on file order. No event timestamps exist in this
capture. One second per record is an arbitrary demonstration interval, not measured
sensor cadence, latency or elapsed capture time. The old ROM boot banner date is
not a capture timestamp. Completion and pause never mark sensors offline.
The internal `online` boolean is only compatibility with the original status
renderer: Admin View says “Captured record,” never live Online. API connectivity
is explicitly `NOT_ASSESSED` and `lastUpdate` remains null.

If a request fails or times out after five seconds, playback stops and the UI marks
all bays Unknown, with “Replay service unavailable (sensor connectivity unknown).”
This is a local replay-service failure, not evidence of ESP32/network failure.
Use Next event to retry, or choose the explicitly labelled simulation link.

## Evidence and expected display

The input is the user's actual saved Wokwi output, not the sample fixture:
`integration-validation/captures/wokwi_serial_actual.txt`.
SHA-256: `dbfb098e800fe0d23a91beff2cec781350d23ea013597e625e85e7d73181e5c2`
(matches the pre-existing captured-output report). Its origin cannot be independently
authenticated from text, so the validator retains `UNVERIFIED_CAPTURE`.

There are 22 accepted JSON events, counters 0..21, 19 heartbeats and three
occupancy transitions. Boot/Serial diagnostics and HEX lines are not JSON events.

| Consumed count | Last ctr | A01 | A02 / A03 |
|---|---|---|---|
| 0 | none | Unknown | Unknown |
| 1..4 | 0..3 | Available | Unknown |
| 5..12 | 4..11 | Occupied | Unknown |
| 13..20 | 12..19 | Available | Unknown |
| 21..22 | 20..21 | Occupied | Unknown |

Admin rows expose bay/numeric ID, parking status, capture availability, source line,
counter, heartbeat/transition, battery and status bits. Source line is a local file
reference, not a sensor event ID or timestamp.

Latest Python/JavaScript evidence: `integration-validation/demo/evidence/20261111T122450185043Z/`:

- `results.json`: exact counts, environment, executed test command and source hashes.
- `existing.txt`: complete existing-suite console, including deliberate bad fixtures.
- `demo.txt`: new Python tests and HTTP request evidence.
- `frontend.txt`: Node TAP results, including actual running-service → DOM integration.
- `capture_validation.json`: existing adapter output for the actual capture.
- `snapshots.json`: initial, heartbeat, transition and completed replay states.

The first successful run is also retained in `evidence/20261111T121043566854Z/`.
Existing reports and historical evidence were not overwritten. The existing
report-generating runner was inspected but not invoked because it updates latest
report files; its existing 81 tests were discovered and executed directly instead.

## Automated checks and actual results

With the server running on 8765, run in a second terminal:

```powershell
Set-Location D:\Smart-Parking-System
& 'python' integration-validation/demo/run_checks.py
```

Each execution writes a new evidence directory, preserving previous runs.
Individual commands, if needed:

```powershell
& 'python' -m unittest discover -s integration-validation -p 'test_*.py' -v
& 'python' -m unittest discover -s integration-validation/demo -p 'test_*.py' -v
node --test --test-reporter=tap integration-validation/demo/test_frontend.cjs
node --check integration-validation/demo/integration.js
```

| Suite | Passed | Failed | Errors | Skipped |
|---|---:|---:|---:|---:|
| Existing validation suite | 81 | 0 | 0 | 0 |
| New Python replay/HTTP suite | 16 | 0 | 0 | 0 |
| JavaScript DOM/HTTP suite, including new regressions | 6 | 0 | 0 | 0 |
| Real Edge browser end-to-end suite | 12 | 0 | 0 | 0 |
| Total | **115** | **0** | **0** | **0** |

JavaScript syntax check also passed. Python tests cover parsing, types, required
fields, duplicate JSON keys, mapping, unmapped IDs, heartbeat preservation, actual
transitions, counters/gaps/rollover/BOOT reset, Unknown state, completion, API bounds,
HTTP assets and simulation isolation. JavaScript tests execute the actual original
app and adapter against a small DOM harness, fetch real Python HTTP snapshots,
assert card/count/Admin updates and verify Unknown on replay-service failure.

The original 101-test run used a DOM harness. A subsequent real-browser pass now
verifies rendering, browser click handling and real timer behavior as detailed
below. Historical evidence remains preserved; the original 101-test result is not
being represented as a browser run.

## Real-browser end-to-end verification

**Truly verified in a real browser:** Playwright 1.65.0 launched installed
Microsoft Edge 157.0.4341.42 headlessly against `http://127.0.0.1:8765/` on Windows.
This used actual browser rendering and real timers, not the DOM harness. The
already-running server was reused. Desktop viewport was 1280×900; a 390×844
viewport also verified the single-column layout. Desktop Admin and mobile
screenshots were visually inspected during implementation.

The final run passed **12/12**, with **0 failed, 0 skipped and 0 cancelled**:

1. Render original styles, switch Dashboard/Admin tabs and check mobile layout.
2. Click Next through **every one of the 22 actual captured messages**, comparing
   each card, summary count, Admin bay/numeric ID, status, counter, heartbeat flag,
   battery and status bits against the saved file read independently by the test.
   A01/1001 changes at counters 4, 12 and 20; A02/A03 stay Unknown throughout.
   Completion holds state and Play restarts from event zero.
3. Play and Pause with real one-second timer ticks; wait 10.5 seconds while paused
   to verify that the original synthetic timer does not change the replay state.
4. Open `/simulation/` in a second browser tab, check its explicit Simulation Mode
   label, wait for the original ten-second synthetic change, and verify replay
   remains paused and independent. Check simulation Admin View as well.
5. Abort a replay API request: all bays become Unknown; removing the fault and
   clicking Next recovers the last committed cursor and captured state.
6. Inject malformed JSON and HTTP 503; verify safe failure and Reset recovery.
7. Inject a structurally invalid snapshot with an impossible counter and no bays;
   verify three Unknown cards remain, the cursor is preserved, and retry recovers.
8. Delay a Next request, click Reset before it completes, and verify stale work
   cannot undo Reset.
9. Delay the replay API beyond its five-second timeout; verify Unknown and recovery.
10. Request invalid event counts against the real service and verify HTTP 400;
    check for uncaught browser JavaScript errors (none observed).
11. Inject incorrect numeric ID mapping, nonboolean occupancy, out-of-range
    counter, live-connectivity claim and mismatched response count; reject each
    without losing the mapped bays, then recover through the real API.
12. Verify browser tabs keep independent replay cursors.

Browser evidence directory:
`integration-validation/demo/evidence/browser-2026-11-11T12-24-31-715Z/`.
It contains `console.tap`, machine-readable `results.json`, `environment.json`,
`observations.json`, per-test screenshots and per-test Playwright trace ZIPs,
plus `mobile.png`, `event-5-admin.png`, `event-13-admin.png`,
`event-21-admin.png`, `event-22-admin.png` and `simulation-admin.png`.
Observations include deliberately aborted requests used by failure tests; these
are injected test faults, not ESP32/network outage evidence.

### Demonstrated bugs fixed

The first real-browser run recorded **7 passed, 3 failed, 0 skipped** in
`evidence/browser-2026-11-11T12-21-56-381Z/`. One failure was an incorrect assertion
argument in the new browser test itself and was corrected. The other two were
reproducible demo implementation defects:

- A valid-JSON but invalid snapshot could clear all cards and accept event count
  777. `integration.js` now validates mode, connectivity label, requested count,
  total, checksum format, complete bay mapping and metadata types/ranges before
  committing the cursor or rendering. Invalid input retains the mapped bays and
  committed cursor and shows the service-unavailable/Unknown state.
- Reset was ignored while a request was pending. New requests now abort older
  requests and carry a version guard. Older responses and errors cannot undo a
  newer user action, even if a transport ignores cancellation.

The final browser rerun passes both regressions. Two additional JavaScript
regression tests also cover malformed snapshots and stale responses. Changes are
confined to the isolated adapter/test files; teammates' original frontend remains
Git-clean and its three source hashes match the prior run. The saved capture hash
also remains unchanged. No university report, commit, push or deployment occurred.

### Repeat browser verification

With the Python server running at port 8765:

```powershell
Set-Location D:\Smart-Parking-System
npm.cmd ci --prefix integration-validation/demo/browser
node integration-validation/demo/browser/run.cjs
```

`npm ci` is needed only when dependencies are missing or the lockfile changes.
The lockfile pins the installed Playwright dependency. Installed Microsoft Edge
is required; no browser download was needed here. Browser launch may require the
host's normal execution approval. Each run saves a new evidence directory and
returns a nonzero exit code on failure. To inspect a trace interactively:

```powershell
& .\integration-validation\demo\browser\node_modules\.bin\playwright.cmd show-trace .\integration-validation\demo\evidence\browser-2026-11-11T12-24-31-715Z\08-Reset-during-delayed-Next-wins-over-stale-response.zip
```

The browser suite is a separate explicit command; `run_checks.py` reruns the
81 existing Python, 16 demo Python and 6 JavaScript harness tests (103 total).
Run both commands to reproduce the combined **115 passed** result.

Remaining verification limits: only Edge was tested, headlessly, on this Windows
host; mobile coverage is viewport emulation, not a physical mobile device. Replay
failure/recovery was induced through browser request interception, not by stopping
the shared Python process or disconnecting real hardware. Malformed captured
messages are rejected in Python tests using constructed input; the original file
was never corrupted. The browser tests inject malformed API responses separately.
That browser pass did not verify MQTT transport. The later MQTT section below
documents its separate real-broker verification. Live ESP32, production backend,
database and physical-sensor verification remain absent; no sensor accuracy,
three-second latency or physical network-recovery claim is made.

## Files and commands used

Created: this README; `integration-validation/demo/server.py`, `integration.js`,
`test_demo.py`, `test_frontend.cjs`, `run_checks.py`; initial evidence directories
and Python-generated `__pycache__` files. Cloned `smart-parking-web/` including its
Git metadata and three original source files. No pre-existing project source or
report files were modified or deleted during that initial implementation.
The browser-verification follow-up modified this README, `integration.js` and
`test_frontend.cjs`; added `browser/browser.test.cjs`, `browser/run.cjs`,
`browser/package.json`, `browser/package-lock.json`, `browser/.gitignore` and
local `browser/node_modules/`; and added the browser and rerun evidence above.

Key executed commands were the clone above (sandbox HTTPS failed; approved retry
succeeded), `git status --short`, `git rev-parse HEAD`, `py -0p`, `node --version`,
the server and check commands above, and `node --check`. For sandbox read-only
Git inspection, a command-scoped ownership exception was used:

```powershell
git -c safe.directory=D:/Smart-Parking-System/smart-parking-web -C smart-parking-web status --short
```

Workspace reads used `Get-ChildItem`, `rg --files` and `Get-Content` to inspect
source, firmware, validation adapters, tests and technical evidence. The workspace
root is not a Git repository; the cloned frontend is. No global Git configuration
was changed. No commit, push, deployment or remote write occurred.

## Known limitations

- Working: actual saved Serial → validated Python replay API → original dashboard
  renderer, capture Admin View, mapped bays, heartbeat metadata, Unknown states,
  isolated synthetic fallback, repeatable automated tests and evidence.
- Missing: live ESP32 transport, teammate production backend/database verification
  and physical sensors. Reference SQLite persistence is verified in the final
  section below. The direct-file replay service demonstrates a local HTTP
  connection. The separate MQTT harness below additionally demonstrates real local
  broker transport, subscriber validation and observed broker reconnect.
- No claim is made for physical accuracy, three-second end-to-end latency,
  network recovery or database correctness. Firmware uses mocked sensor inputs.
- No measured real-time freshness can be derived from this capture. Only one
  numeric spot ID and no counter rollover occur in the actual evidence; rollover
  and BOOT reset are separately tested with explicitly constructed fixtures.
- The server is a development demo, not a production service. It keeps no database
  or shared cursor. A frontend upstream change to its HTML structure or JavaScript
  initialization marker may require updating this adapter; the tested commit is
  recorded above. Keep it pinned when reproducing these results.

## Real local MQTT transport harness

Implemented and verified on 11 November 2026, after the 115-test browser milestone.
This is a **real MQTT 3.1.1 TCP transport path**, using Aedes 1.2.0 and Paho MQTT
2.1.0. The publisher and subscriber are separate clients connected to the broker
over loopback sockets. The input remains the user's saved Wokwi Serial capture.
It is an integration test harness, not a teammate production backend.

### Component inventory and boundaries

Inspection found only the Wokwi sketch, the frontend checkout, validation tools and
technical evidence. No runnable teammate MQTT subscriber/backend, database server,
migration or database connection was available. `integration_config.template.json`
still has null broker/topic/backend/database settings. The optional publisher in
`integration_adapters.py` does not implement a subscriber or complete reconnect
verification. Those files were left unchanged. The harness reuses the existing
strict JSON parser, Wokwi source-aware validator, explicit bay mapping, captured
input and original frontend renderer/navigation/CSS.

```text
saved actual Wokwi JSON text (22 records, file input only)
    → publish_capture.py / Paho publisher
    → MQTT 3.1.1 TCP, 127.0.0.1:18883, QoS 1, retain=false
    → broker.mjs / real Aedes broker, in-memory, loopback only
    → Paho Subscriber / strict source-aware validation and deduplication
    → ReceivedState (in-memory current state + counters, no database)
    → GET http://127.0.0.1:8766/api/mqtt
    → mqtt.js polling every 500 ms
    → existing Dashboard renderer and capture-specific Admin View
```

The MQTT page itself never reads the capture. Its data comes from subscriber
callbacks after broker delivery. HTTP is the dashboard delivery boundary, not a
replacement for the MQTT publisher/broker/subscriber connection.

### Local test contract and Task 2 conversion

This **harness-only topic** was chosen because no production topic was supplied:

`smart-parking/integration-test/wokwi/node-1/events`

- Broker bind: `127.0.0.1:18883`; no external deployment or broker connection.
- Protocol: MQTT 3.1.1; QoS 1; retain=false; clean sessions; unique client IDs.
- Broker permits publishing only in `smart-parking/integration-test/` with QoS 1
  and no retain. It permits subscriptions only in that namespace. Tests use unique
  subtopics and separate ephemeral broker ports to avoid affecting the demo.
- Local-only unauthenticated TCP; TLS, credentials and production authorization
  are not implemented. Broker and current-state storage are in-memory.
- Wire schema is **exactly** `spot_id`, `occupied`, `batt_mv`, `status`, `ctr`,
  `heartbeat`, with the source types/ranges described earlier. Actual capture JSON
  lines are transmitted unchanged, without source timestamps or session IDs added.
  Serial boot text and HEX lines are not published as MQTT events.
- Mapping is explicit: 1001 → A01, 1002 → A02, 1003 → A03. Unmapped IDs are rejected.

The available original validation/Task 2-style event contract requires
`event_id`, `parking_space_id`, `status`, `timestamp`. The original Task 2 backend
implementation and its authoritative production topic/schema are **not available**;
the four-field contract is the local validator's contract, not evidence that a
teammate service accepted it. Conversion is recorded in subscriber journals:

| Wokwi input | Local normalized representation |
|---|---|
| `spot_id: 1001` | `parking_space_id: "1001"`, plus `bay_label: "A01"` for frontend display |
| `occupied: false/true` | `status: "AVAILABLE"/"OCCUPIED"`; numeric status bits remain source metadata |
| no source event ID | `event_id: "mqtt-receipt-<subscriber-session>-<accepted-index>"`, explicitly a local receipt identity |
| no source timestamp | `timestamp` = actual subscriber receive time in UTC; `timestamp_basis: "subscriber_received_at"` |
| saved Wokwi input | `evidence_kind: "CAPTURE_REPLAY_OVER_MQTT"` |

The conversion passes the existing `ParkingEventValidator` contract test. It is
logged locally, not forwarded to an unavailable backend/database. Do not use its
receipt timestamp as source event time or its receipt ID as durable sensor identity.

### State, duplicates, invalid input and reconnect

The subscriber waits for actual CONNACK and SUBACK before declaring readiness.
It strictly rejects malformed UTF-8/JSON, duplicate JSON keys, wrong fields/types,
oversized payloads, unmapped IDs, invalid source-specific status bits, counter
gaps/reorder/reset and contradictory heartbeat/occupancy transitions. A rejected
event increments `rejected` and does not change accepted state or counter history.
An immediately repeated identical six-field payload increments `duplicates` and
does not create a transition or restore post-reconnect freshness. Application
deduplication is deliberately limited; uint8 counters are not durable identities.

The uint8 counter is global to this node stream across spot ID changes, increments
modulo 256 and is not a per-bay counter. First receipt establishes a baseline.
Thereafter a missing record must be supplied before later counters are accepted.
Heartbeats preserve occupancy and update recorded metadata. Only the three actual
captured non-heartbeats change A01 occupancy; A02/A03 stay Unknown without receipts.

Broker disconnect makes all MQTT bays Unknown. Paho automatically reconnects and
resubscribes; old states remain Unknown until a **new accepted MQTT receipt** in
the new connection generation. This was tested by actually terminating/restarting
test-owned broker processes, not just changing a Python boolean. Counter history
is retained across that reconnect, so the next sequential event is required.

Subscriber restart creates a new in-memory session with no restored state. This
also provides the explicit reset needed before replaying the full capture again
from counter 0. There is no source BOOT/session event on the JSON-only MQTT topic;
automatic guessing of resets would hide loss/reorder. The publisher has no durable
retry queue; restart it at the next required index after restoring connectivity.

Admin View says “Received via local MQTT” and shows actual subscriber receipt time.
This establishes local transport receipt, not sensor connectivity or physical
freshness. No offline decision uses the old capture's age. The final state is held
while the subscriber remains connected; no source-time or inactivity timeout is
invented. Subscriber HTTP failure separately makes the UI Unknown and polling
recovers automatically. Fallback modes remain explicitly labelled and independent.

### Install and start every component (PowerShell)

Dependencies are isolated under `integration-validation/demo/mqtt/`:

```powershell
Set-Location D:\Smart-Parking-System
npm.cmd ci --prefix integration-validation/demo/mqtt
& 'python' -m pip install --target integration-validation/demo/mqtt/vendor -r integration-validation/demo/mqtt/requirements.txt
```

Run installation only when dependencies are missing or requirements change. The
broker npm lockfile pins dependencies and Paho is pinned to 2.1.0. Browser tests
reuse the existing `demo/browser/` Playwright installation and installed Edge.

Start **broker** in terminal 1 and leave it running:

```powershell
Set-Location D:\Smart-Parking-System
node integration-validation/demo/mqtt/broker.mjs 18883
```

Start **subscriber + dashboard HTTP service** in terminal 2 and leave it running:

```powershell
Set-Location D:\Smart-Parking-System
& 'python' integration-validation/demo/mqtt/dashboard_server.py
```

Open **http://127.0.0.1:8766/mqtt/**. Wait for “subscriber connected.” A01/A02/A03
initially show Unknown. Start the finite **capture publisher** in terminal 3:

```powershell
Set-Location D:\Smart-Parking-System
& 'python' integration-validation/demo/mqtt/publish_capture.py --interval 1
```

It publishes the 22 saved messages at a demo interval and exits. Each PUBACK proves
broker acknowledgement only; check accepted counts/Admin values or subscriber
journal for receipt. Use `--start 5 --limit 1` to send just event index 5 when
continuing an already accepted 0..4 prefix. No measured source cadence is implied.

For another complete replay, Ctrl+C and restart the **subscriber/dashboard** first,
then rerun the publisher from zero. The broker can remain running. Stop owned
services with Ctrl+C. If a port is occupied by the already-running demo, use it or
stop that owning terminal before starting another copy; do not kill unrelated
processes. Alternate ports are supported by broker positional port,
subscriber `--mqtt-port`/`--port`, and publisher `--port`.

The original direct-file replay remains available independently:

```powershell
Set-Location D:\Smart-Parking-System
& 'python' integration-validation/demo/server.py
```

Its URL is **http://127.0.0.1:8765/**, with simulation at `/simulation/`.
The MQTT service also exposes independent direct-file replay at
`http://127.0.0.1:8766/` and simulation at `http://127.0.0.1:8766/simulation/`.

The subscriber creates a new timestamped `demo/evidence/mqtt-session-.../` journal
by default. Optional `--log <existing-parent-directory>/subscriber.jsonl` and
publisher `--log .../publisher.jsonl` write JSONL. The broker accepts an optional
third argument for its JSONL path: `node broker.mjs 18883 <log-path>`. Logs append,
so choose new filenames/directories for new runs; do not overwrite old evidence.
Processes started during this task are responding on 18883, 8766 and existing 8765;
their persistence after the coding session depends on the host.

### Actual test results and evidence

| Latest suite | Passed | Failed | Errors | Skipped |
|---|---:|---:|---:|---:|
| Existing validation Python | 81 | 0 | 0 | 0 |
| Existing demo Python | 16 | 0 | 0 | 0 |
| Existing JavaScript DOM/HTTP | 6 | 0 | 0 | 0 |
| Existing real Edge replay browser | 12 | 0 | 0 | 0 |
| New MQTT contract unit tests | 12 | 0 | 0 | 0 |
| New actual TCP broker/client integration tests | 6 | 0 | 0 | 0 |
| New real Edge MQTT browser tests | 7 | 0 | 0 | 0 |
| **Total** | **140** | **0** | **0** | **0** |

No unavailable physical/production test is counted as a skipped automated test or
a pass. MQTT browser coverage includes all 22 per-event Dashboard/Admin updates,
mapping, heartbeats, duplicates, malformed messages, gaps/recovery, actual broker
disconnect/reconnect, post-reconnect receipt requirement, HTTP failure/recovery,
malformed HTTP snapshots and independence of both fallbacks. Tests own and clean
up their temporary broker/HTTP processes; they do not restart the shared demo.
JavaScript syntax check also passed. Screenshots of MQTT Admin View were inspected.

Latest evidence under `integration-validation/demo/evidence/`:

- `20261111T124310997760Z/`: 81 + 16 Python and 6 JavaScript regression logs/results.
- `browser-2026-11-11T12-43-13-030Z/`: all 12 existing real-browser tests rerun.
- `mqtt-tests-20261111T124247174805Z/`: all 18 new Python tests; actual broker,
  publisher PUBACK, subscriber CONNACK/SUBACK, accepted/rejected/duplicate journals
  and reconnect evidence. The initial run `mqtt-tests-20261111T124102134008Z/`
  is retained: 17 passed, 1 failed due to an incorrect new assertion about the
  existing validator's return type. The assertion was corrected; no old test or
  existing validator was changed to force a pass.
- `mqtt-browser-2026-11-11T12-42-55-087Z/`: 7 real Edge tests, TAP results,
  environment, screenshots, traces, per-test broker/client journals, UI snapshots
  and test-controller exchanges. Controller stdin only instructs the test fixture;
  the fixture actually publishes MQTT messages and terminates/restarts its broker.
- `mqtt-session-20261111T123927639603Z/subscriber.jsonl`: demonstration service's
  22 actual accepted receipts, counters 0..21, no duplicate/rejection.
- `mqtt-broker-demo.jsonl` and `mqtt-publisher-demo.jsonl`: matching standalone
  demo broker observations and 22 publisher PUBACKs/capture source-line references.
- `mqtt-audit-20261111T124443329886Z/`: cross-check and API snapshot. It compared
  every broker payload and publisher payload byte-for-byte against the original
  captured JSON lines, compared all 22 subscriber payloads against them, checked
  mapping/final state and aggregate test counts, and recorded source hashes.
  Original capture and all three teammate frontend hashes match the prior run.

Re-run regression and new suites (keep the existing replay server on 8765 running):

```powershell
Set-Location D:\Smart-Parking-System
& 'python' integration-validation/demo/run_checks.py
node integration-validation/demo/browser/run.cjs
& 'python' integration-validation/demo/mqtt/run_transport_checks.py
node integration-validation/demo/mqtt/run_browser.cjs
```

The two new suites use their own brokers and do not require the shared broker or
MQTT HTTP service. They require Node/Paho and, for browser tests, installed Edge
and Playwright. Set `PARKING_PYTHON` to a different interpreter path if required
for browser fixtures. All test runners save new timestamped evidence directories.
`mqtt/verify_evidence.py` audits the specific recorded standalone demonstration
logs and the latest suite summaries; it expects that demonstrated MQTT service
to still show its 22 accepted messages. After a reset or a new demonstration,
collect and audit a separate evidence set rather than reinterpreting older logs.

### Changed files and remaining limits

Added only `demo/mqtt/`: broker, transport clients/state, publisher CLI,
subscriber/dashboard server, `mqtt.js`, Python contract/transport tests and runner,
browser fixture/tests/runner, evidence cross-check script, pinned requirements,
npm manifest/lockfile and ignores. Dependency directories are local and ignored.
Updated this README and added new evidence. No existing replay implementation,
teammate repository code, university report, slide or presentation file was edited.
No commit, push, remote write or external deployment occurred.

At that MQTT-only milestone, still missing: real HC-SR04 measurements, live ESP32 Wi-Fi/MQTT publishing,
teammate production backend, authoritative Task 2 production topic/schema,
database integration/persistence/verification, production security and durable
offline queuing. Broker and state restart lose their in-memory data; JSONL evidence
is a journal, not an application database. The later reference backend below
adds persistent SQLite storage without changing that independent MQTT mode.
Adjacent duplicate suppression and
uint8 sequence checking cannot provide durable exactly-once identity across boots.
Local broker reconnect is demonstrated; physical Wi-Fi recovery, three-second
sensor-to-web latency and real sensor accuracy are not assessed. Browser coverage
is headless Edge on this Windows host, not all browsers or real mobile hardware.

## Persistent SQLite reference backend

Implemented and verified on 11 November 2026 after the 140-test MQTT milestone.
**Saaket's actual backend/database is not present or usable in this workspace.**
The inspected source consists of the original frontend, Wokwi sketch, validation
framework and the isolated demos created here. No teammate backend service,
database schema/migrations, database file or configured connection was supplied.
`integration_config.template.json` still contains null backend/database values.
No teammate implementation was replaced, inferred or described as verified.

This addition is explicitly an **isolated reference integration backend**, using
Python's standard-library SQLite/HTTP support and the installed Paho dependency.
It is not Saaket's production backend and does not establish production acceptance.

### Verified architecture and separate modes

```text
actual saved Wokwi Serial JSON (22 events, unchanged)
  → existing publish_capture.py / real Paho publisher
  → existing Aedes broker implementation on isolated TCP port 18884
  → DurableSubscriber (existing Paho subscriber reused, manual acknowledgement)
  → existing strict Wokwi JSON/schema/state/counter validator reused
  → one SQLite transaction: history + current bay + checkpoint + receipt audit
  → commit succeeds, then subscriber sends MQTT acknowledgement
  → SQLite-backed availability / health / history HTTP APIs on port 8767
  → backend.js polling /api/availability, using original Dashboard renderer/CSS
```

The new broker instance on **18884** is separate from the existing memory MQTT
demo's broker on 18883. This prevents new demonstrations from appending traffic
to the old subscriber's recorded evidence. All components bind only to loopback.
The original teammate repository remains Git-clean and its source hashes, along
with the captured input hash, match the preceding evidence.

| Mode | URL | State source |
|---|---|---|
| Persistent reference backend | `http://127.0.0.1:8767/backend/` | committed SQLite rows received through real MQTT |
| Independent memory MQTT | `http://127.0.0.1:8766/mqtt/` | existing in-memory subscriber, broker 18883 |
| Independent file replay | `http://127.0.0.1:8765/` | saved capture, browser cursor |
| Original simulation | `http://127.0.0.1:8765/simulation/` | original synthetic JavaScript |

The backend HTTP service also serves independent replay at `/` and simulation at
`/simulation/`. Its Memory MQTT link opens the existing separate 8766 service.
There is no automatic fallback from persisted evidence to fabricated occupancy.

### SQLite schema and durability

Default database:
`integration-validation/demo/backend/data/parking-reference.sqlite3`.
The directory is local generated state and is ignored by the new directory's
`.gitignore`. No existing database or report file was overwritten.

Schema is defined in `demo/backend/schema.sql`, version 1:

| Table | Purpose and important fields |
|---|---|
| `streams` | durable source-session namespace, topic, accepted ordinal, last accepted payload and event reference; restores sequence/dedup checkpoint after backend restart |
| `events` | accepted history: integer database ID, independent unique event UUID, stream ordinal, **all six Wokwi fields**, canonical JSON, exact raw bytes, topic/QoS/retain/MQTT DUP/packet ID, null source timestamp, actual backend receive UTC, backend-run UUID and connection epoch |
| `bay_current` | `(stream_id, spot_id)` → committed event ID; foreign key to history; no fabricated row for bays without observations |
| `receipts` | every processed accepted/duplicate/rejected delivery, linked event ID when applicable, reason, raw bytes/size and MQTT/receive/run metadata |
| `connections` | durable broker/subscription connected/disconnected observations, with backend-run UUID and connection epoch |

SQLite uses foreign keys, WAL journaling, `synchronous=FULL`, parameterized values
and short per-operation connections. `BEGIN IMMEDIATE` serializes each receive
transaction. Accepted event insert, current-state upsert, checkpoint advance and
receipt insert commit together. A demonstrated injected failure on the receipt
insert rolled back all earlier writes; no partial event/current/checkpoint survived.
Read APIs use database queries; the availability read uses one coherent read
transaction. There is no in-memory occupancy/history authority.

Paho manual acknowledgement is enabled for the reference subscriber. Its
acknowledgement follows successful receipt processing/commit, including durable
duplicate/rejection auditing. Publisher PUBACK is still only broker acceptance;
it is not a database commit acknowledgement. A tested SQLite write failure rolls
back, withholds subscriber acknowledgement, disconnects the reference subscriber
and returns unhealthy/503. Resolve storage failure and explicitly restart it.
The current clean-session in-memory broker is not a durable delivery queue;
operator/publisher resend may be required. No exactly-once or lossless-recovery
guarantee is claimed.

On startup, an empty database gets the reference schema. A database with an
unrecognized schema/version is refused rather than having teammate tables replaced.
There are no destructive reset APIs or automatic database deletion/migrations.

### Consistent message, identity and timestamp contract

The MQTT wire contract and topic remain unchanged:
`smart-parking/integration-test/wokwi/node-1/events`, MQTT 3.1.1, QoS 1,
retain=false. Broker namespace/policy remains the same. Source payload fields:

```json
{"spot_id":1001,"occupied":false,"batt_mv":3599,"status":0,"ctr":0,"heartbeat":true}
```

The backend persists these fields without renaming their meaning. Database/history
`status` is the original integer bitmask. Availability `status` is the display
string `available`, `occupied` or `unknown`; `status_bits` preserves the bitmask
there. Numeric IDs map explicitly to A01/A02/A03. All APIs are scoped to the active
`--stream`, default `capture-1`.

- Source messages contain **no timestamps**. `source_timestamp` is always SQL/JSON
  null. `received_at` is actual backend receive UTC, not source emission time.
  No original capture duration or sensor-to-web latency is inferred.
- MQTT packet IDs and DUP flags are preserved as transport metadata, not durable
  identity. `event_uuid` is a local persistent event identity. `(stream_id, ordinal)`
  is unique; `ctr` deliberately is **not unique**. A 257-event fixture verifies
  0..255→0 produces 257 distinct history events, including two counter-zero rows.
- Sequence is global to the single node stream across spot ID changes, as in the
  firmware. The persisted last payload checks the next counter modulo 256 and
  heartbeat/transition consistency, including after backend restart.
- An identical adjacent last payload is a duplicate receipt, not another history
  event. A new heartbeat counter produces a distinct accepted history event while
  preserving occupancy. Gaps, reorder, malformed input, wrong status bits/types,
  unmapped IDs and invalid QoS/retain are audited as rejected without state changes.
  Oversized rejected input keeps its original size and up to 4096 raw bytes.
- For a new capture/boot sequence, choose a **new explicit `--stream`**. The raw
  MQTT schema has no source boot/session ID; the backend does not guess resets.
  Restarting with the same stream restores its checkpoint and never resets its
  history. Start a new stream for a full replay from counter zero. Old streams
  remain intact in the database.
- Adjacent deduplication is not global identity. Delayed duplicates after an entire
  uint8 cycle can be indistinguishable from legitimate events. Source-generated
  durable event/session IDs are still needed for a production contract.

### Availability versus sensor health

The persistent UI intentionally shows **last committed observations**, including
after a process restart or broker disconnect. It labels that basis explicitly.
It does not turn a recorded Occupied value into a newly fabricated Available value.
Sensor health is separate: `fresh_this_connection` requires an accepted receipt
from this backend run and its current subscribed connection epoch.

After backend/broker reconnect, persisted occupancy/history remain visible but the
Admin connection cell says “Persisted last-known; awaiting new receipt.” Duplicate
receipts do not restore freshness. A new sequential accepted message does. This
is local receipt freshness, not evidence that a physical sensor is connected.
No freshness timeout is invented from the old capture's date.

A02/A03 have no `bay_current` rows in the actual capture demo. They return
`status: "unknown"`, `occupied: null`, `has_persisted_data: false`, and
`availability_basis: "NO_DATA"`; the frontend renders Unknown. If the backend API
or database is unavailable or returns an invalid snapshot, the UI shows all bays
Unknown instead of presenting unavailable data as a successful current read.

### API endpoints

All are read-only, local HTTP GET and return JSON with `Cache-Control: no-store`:

| Endpoint | Contract |
|---|---|
| `/api/availability` | `mode: SQLITE_REFERENCE_BACKEND`, persistent flag, active stream, broker/storage status, committed/duplicate/rejected/received counts, three mapped `spaces`; each includes display status, source fields, committed event ID, receive time and last-known/freshness basis |
| `/api/health` | reference-database label, active stream, broker connected flag, storage error, `physical_connectivity: NOT_ASSESSED`, per-sensor data-presence/freshness/receive-time/connection indicators |
| `/api/events?after=0&limit=100` | accepted events ordered by durable DB ID, all source/transport/run/time fields, parsed original `payload`, exact `raw_payload_hex`, `next_after` cursor |
| `/api/receipts?after=0&limit=100` | accepted/duplicate/rejected audit deliveries with reasons, linked event, source bytes and transport metadata; same pagination |

`after` must be a nonnegative integer and `limit` must be 1..100; invalid input
returns HTTP 400. Unavailable database queries return JSON HTTP 503. Recorded
storage failure also makes availability/health return 503 until a clean restart.
History remains a read-only view of committed data if readable. There are no
write-ingestion HTTP endpoints; event ingestion is the real MQTT subscription.

Example after the actual 22-event demo:

```json
{
  "id":"A01", "spot_id":1001, "status":"occupied",
  "has_persisted_data":true, "occupied":true, "status_bits":1,
  "batt_mv":3581, "ctr":21, "heartbeat":true, "event_id":22,
  "source_timestamp":null, "availability_basis":"LAST_PERSISTED_OBSERVATION"
}
```

### Installation and exact startup/restart commands

No new Python dependency was added: SQLite/HTTP are built in, and the reference
backend reuses the already-isolated Paho installation and Aedes broker. For a fresh
checkout, install the pinned transport dependencies once:

```powershell
Set-Location D:\Smart-Parking-System
npm.cmd ci --prefix integration-validation/demo/mqtt
& 'python' -m pip install --target integration-validation/demo/mqtt/vendor -r integration-validation/demo/mqtt/requirements.txt
```

Start the **isolated reference broker** in terminal 1:

```powershell
Set-Location D:\Smart-Parking-System
node integration-validation/demo/mqtt/broker.mjs 18884
```

Start/restart the **persistent reference backend/subscriber/HTTP server** in terminal 2:

```powershell
Set-Location D:\Smart-Parking-System
& 'python' integration-validation/demo/backend/backend_server.py --mqtt-port 18884 --port 8767 --db integration-validation/demo/backend/data/parking-reference.sqlite3 --stream capture-1
```

Open **http://127.0.0.1:8767/backend/**. Restarting this command with the same
database/stream retains all committed events and the stream checkpoint. Stop only
the owned backend terminal with Ctrl+C before restarting; no database reset is
needed. Broker 18884 can stay running. Do not delete SQLite files to restart.

For an **empty stream**, publish the actual 22 saved events in terminal 3:

```powershell
Set-Location D:\Smart-Parking-System
& 'python' integration-validation/demo/mqtt/publish_capture.py --port 18884 --interval 1
```

**The included `capture-1` database already contains the 22 demonstrated events.**
To perform another full demonstration without deleting any data, stop the backend
and run its command with a new stream, e.g. `--stream capture-2`, then publish the
capture from zero. Keep the broker and database file. Replaying from zero into an
already completed stream is intentionally rejected as counter reset/reorder;
its last identical event is recorded as a duplicate. A broker PUBACK alone does
not mean that replay was accepted by this backend.

To continue a partial stream, use the existing publisher's `--start N` (zero-based
capture index) and optional `--limit`. Backend and publisher must use the same
isolated broker port. The service allows `--port`, `--mqtt-port`, `--db`, `--stream`
and optional `--log` overrides. Use new log filenames/directories for new evidence.
The reference components are currently responding on ports 18884 and 8767; reuse
them or stop their owning processes before launching duplicates. The old modes
retain their documented commands and ports unchanged. Host process persistence
after this coding session is not guaranteed.

### Tests, screenshots and evidence

**Final total: 173 passed, 0 failed, 0 errors, 0 skipped.**

| Re-run suite | Passed | Failed | Errors | Skipped |
|---|---:|---:|---:|---:|
| Existing validation Python | 81 | 0 | 0 | 0 |
| Existing direct-replay Python | 16 | 0 | 0 | 0 |
| Existing JavaScript DOM/HTTP | 6 | 0 | 0 | 0 |
| Existing MQTT Python contract/real transport | 18 | 0 | 0 | 0 |
| Existing real Edge replay | 12 | 0 | 0 | 0 |
| Existing real Edge memory MQTT | 7 | 0 | 0 | 0 |
| New backend/database unit and API tests | 21 | 0 | 0 | 0 |
| New actual MQTT/database/process-restart tests | 5 | 0 | 0 | 0 |
| New real Edge persistent-backend tests | 7 | 0 | 0 | 0 |
| **Total** | **173** | **0** | **0** | **0** |

New tests exercise schema/Unknown states, all 22 actual fields/raw payloads,
heartbeat history, duplicates, malformed input, out-of-order/gap recovery, 8-bit
rollover without unique-counter assumptions, persisted checkpoints, stream
isolation, multiple bay mappings, transaction rollback, unsupported DB refusal,
bounded history pagination, API faults, independent committed DB changes becoming
visible through APIs, actual broker loss/reconnect, database failure withholding
subscriber ACK, and an actual backend-process restart retaining all 22 rows and
history IDs. The first 25-test backend pass is retained; adding an independent-DB
read API test raised the suite to 26. No backend test failed in either run.

Real-browser tests used actual Microsoft Edge 157.0.4341.42, Playwright 1.65.0,
Node v24.22.1 and Python 3.14.7. For each of all 22 MQTT events, a separate read-only
SQLite connection queried the file, then tests compared its rows/raw bytes with
the original capture, event-history API, availability API and rendered cards/Admin
cells. A02/A03 stayed Unknown. Tests also restarted a separate backend process,
verified a changed PID and identical history/IDs/timestamps, then verified the UI
showed persisted last-known occupancy with freshness false. They exercised actual
broker restart, duplicate/malformed/gap recovery, HTTP and invalid-response faults
and the independent replay/simulation modes. No browser JavaScript errors occurred.

Latest evidence under `integration-validation/demo/evidence/`:

- `20261111T131642574197Z/`: existing Python/JavaScript regression results.
- `mqtt-tests-20261111T131643861042Z/`: all 18 existing MQTT Python tests rerun.
- `browser-2026-11-11T13-16-46-008Z/`: all 12 existing replay Edge tests rerun.
- `mqtt-browser-2026-11-11T13-16-45-157Z/`: all 7 existing memory MQTT Edge tests rerun.
- `backend-tests-20261111T132209326636Z/`: final 26 passing backend tests, SQLite files,
  process-start records with PIDs, real broker/client journals, commit/ACK and
  injected-failure evidence. Initial successful 25-test run is also preserved at
  `backend-tests-20261111T131340031449Z/`; the earlier successful 26-test run
  `backend-tests-20261111T131648255827Z/` is also retained.
- `backend-browser-2026-11-11T13-22-23-314Z/`: final 7 passing real-browser tests, TAP,
  environment, screenshots, traces, per-test persistent DBs, real broker/backend
  journals and independent DB/API/UI comparison records in `controller.jsonl`.
  The first successful browser run at `backend-browser-2026-11-11T13-16-19-246Z/`
  remains available. The final rerun followed a small consistency fix to make
  health fields use the same snapshot as their sensor indicators.
- `backend-demo-broker.jsonl`, `backend-demo-publisher.jsonl`,
  `backend-demo-journal.jsonl`: standalone reference demo's real MQTT traffic and
  22 committed events, each followed by subscriber acknowledgement.
- `backend-audit-20261111T132356201665Z/`: final aggregate results and source hashes,
  availability/health/history snapshots and a self-contained SQLite backup named
  `database-snapshot.sqlite3`. The audit matched broker/publisher/DB/API payloads
  to the captured lines, checked all 22 commit-before-ACK observations, verified
  `PRAGMA integrity_check = ok` and no foreign-key violations, and checked that
  original frontend/capture hashes still match the earlier run. It additionally
  compared the displayed standalone service's history after an actual process
  termination/restart with `backend-demo-before-restart-history.json`; all 22
  rows, identities, source fields and receive timestamps remained identical.
  The corresponding before-restart availability JSON is retained as well.
  After this restart, A01 remains Occupied with counter 21 but freshness is false,
  as no new source event was invented. Initial audit
  `backend-audit-20261111T131832521180Z/` is retained.

Example screenshots (visually inspected during implementation):

- [Occupied after real MQTT event 21](docs/EVIDENCE.md)
- [Persisted Occupied after backend process restart](docs/EVIDENCE.md)

To re-run all suites, leave the original replay server on port 8765 running, then:

```powershell
Set-Location D:\Smart-Parking-System
& 'python' integration-validation/demo/run_checks.py
node integration-validation/demo/browser/run.cjs
& 'python' integration-validation/demo/mqtt/run_transport_checks.py
node integration-validation/demo/mqtt/run_browser.cjs
& 'python' integration-validation/demo/backend/run_backend_checks.py
node integration-validation/demo/backend/run_browser.cjs
```

New transport/browser tests own separate broker/backend processes, temporary
ports and evidence databases; they do not restart or mutate the shared demo.
Browser tests reuse the installed Edge and `demo/browser/` Playwright package.
Each runner writes a new timestamped evidence directory. An optional
`backend/verify_evidence.py` re-audits the specific standalone demo and latest
suite results; it expects the included demo's `capture-1` database and its 22-event
journals, so collect a new audit set rather than reinterpreting them after a new
demonstration. JavaScript syntax check passed as well.

### Exact changed files and remaining missing components

Modified existing file: **`INTEGRATION_DEMO_README.md` only**.

New source/config/test files, all under `integration-validation/demo/backend/`:

- `.gitignore`
- `schema.sql`
- `store.py`
- `backend_server.py`
- `backend.js`
- `test_backend.py`
- `run_backend_checks.py`
- `browser_fixture.py`
- `browser.test.cjs`
- `run_browser.cjs`
- `verify_evidence.py`

Generated: `backend/data/parking-reference.sqlite3` (plus SQLite-managed WAL/SHM
sidecars when present), Python `__pycache__`, and the new evidence files/directories
listed above. Existing replay/MQTT implementations, teammate frontend code,
capture, old tests and prior evidence files were preserved. No academic report,
presentation, commit, push or deployment was made.

Remaining limits: Saaket's production backend/database, authoritative production
schema/topics, real ESP32 Wi-Fi/MQTT, HC-SR04 input, production authentication/TLS,
durable broker queuing and globally durable source event/session identity remain
missing. The reference backend now demonstrates real **local database persistence**,
not production backend/database acceptance. Persisted observations can be old;
local freshness is labelled separately and does not measure physical connectivity.
Strict sequence rejection requires resending missing events or explicitly choosing
a new stream; there is no reordering buffer or guessed boot reset. SQLite v1 has
no production migration/retention policy. Storage failure requires an explicit
backend restart after repair and publisher replay as needed. Only headless Edge
was tested; no physical sensor accuracy, three-second end-to-end latency, physical
Wi-Fi recovery or full deployed-system acceptance claim is made.

## HC-SR04 Wokwi integration and ESP32 networking investigation

Completed on 11 November 2026. **Actual Wokwi simulated ultrasonic measurements
work. Direct ESP32-to-local-MQTT does not work in the tested networking setup.**
This section distinguishes simulated sensor measurement from real physical
hardware, from saved-event replay, and from the actual local MQTT transport.
It supersedes earlier limitations about the *new variant* not reading HC-SR04;
the original firmware still uses mocks and is unchanged.

### Firmware and wiring

New firmware: `integration-validation/demo/sensor-wokwi/firmware/sketch.ino` and
`diagram.json`. The originals at `wokwi-source/` retain their earlier SHA-256 hashes.
Original `mockMagDelta()` and `mockToFmm()` were inspected; neither reads HC-SR04.
The variant removes both and implements only the ultrasonic source. It makes no
magnetic-fusion claim and uses no hardcoded occupancy cycle.

| HC-SR04 pin | ESP32 connection in isolated diagram |
|---|---|
| VCC | 5V |
| GND | GND.1 |
| TRIG | **GPIO 5**, output |
| ECHO | **GPIO 18**, input |

The sketch drives TRIG low, high for 10 microseconds, then low, and measures the
actual simulated ECHO high duration with `pulseIn(..., 25000)`. Distance in mm is
rounded from `echo_us × 10 / 58`. This follows the simulator's documented trigger
and conversion interface. [Wokwi HC-SR04 reference](https://docs.wokwi.com/parts/wokwi-hc-sr04).

Polling is 100 ms plus measurement time. The rounded measurement has a 20..4100 mm
validity guard; zero, timeout and implausible values are invalid. The upper margin
accommodates the measured Wokwi 400 cm setting: echo 23524 us converts to 4056 mm
under the approximate 58 us/cm convention. This is a simulator/conversion detail,
not a physical sensor calibration or accuracy result.

- Near/Occupied: converted distance **≤120 mm**, continuously confirmed **1500 ms**.
- Far/Free: converted distance **≥220 mm**, continuously confirmed **2500 ms**.
- Between thresholds: keep the last confirmed state and cancel any provisional
  change. An initial reading in this band remains unknown.
- Startup: no occupancy JSON until a valid state is confirmed. The first confirmed
  observation is a heartbeat/baseline, not a fabricated physical transition.
- Invalid/timeout: cancel confirmation, retain last-known occupancy internally,
  mark the reading untrusted/faulted, and suppress occupancy JSON/heartbeats.
  Recovery requires confirmation again. Timeout is never interpreted as Free.
- Healthy unchanged observations emit heartbeats at a 5000 ms interval after the
  last message; confirmed changes emit transition records. Timers use unsigned
  subtraction, with wraparound covered by the compiled tests.

The six JSON fields remain `spot_id`, `occupied`, `batt_mv`, `status`, `ctr`,
`heartbeat`. `spot_id=1001`; `ctr` is uint8 and advances only for emitted JSON.
`status` carries the occupancy bit for trusted events. **`batt_mv=3600` is an
unmeasured placeholder**, not an ADC measurement or battery validation.
`[SENSOR]` diagnostics include simulation milliseconds, echo duration, converted
distance, validity, known/trusted state and fault. They are not new MQTT event fields.

To preserve the existing backend contract, faulted measurements are not sent as
healthy six-field events. No new fault-bit protocol was silently introduced:
the existing source-aware backend rejects unexpected fault bits. Consequently,
the current backend cannot receive a sensor-timeout health signal from this
variant's JSON alone; its last-known-data semantics remain essential. Extending
the production health schema remains future work. No HEX/BLE transmission is
claimed for this new variant.

### Actual Wokwi execution and captured output

Playwright drove **real Wokwi in Microsoft Edge**, compiling the isolated source
and changing the HC-SR04 slider while simulation ran. No project was saved,
shared, committed or deployed. Wokwi's anonymous build queue was allowed to finish;
it was not bypassed. No local Wokwi CLI/token or VS Code Wokwi extension was found.

The final scenario starts at 350 cm and changes the virtual distance through
**10 → 17 → 35 → 9 → 35 → 400 cm**. The 17 cm band held the Occupied state.
Raw echo values changed with the controls; 400 cm remained a valid far reading.
Python checks independently verified the pulse-to-distance arithmetic and that
each of the four occupancy changes followed the required confirmation interval.
Those are simulator-time observations, not real-hardware latency measurements.

Final capture contains **7 JSON messages**, counters **0..6**:

| Counter | Occupied | Event type |
|---|---|---|
| 0 | false | initial confirmed Free baseline heartbeat |
| 1 | true | Occupied transition |
| 2 | true | heartbeat preserving occupancy |
| 3 | false | Free transition |
| 4 | true | Occupied transition |
| 5 | false | Free transition |
| 6 | false | heartbeat preserving occupancy |

This is a **new measured-simulator capture**, separate from the old 22-event
mocked-source capture. Both are preserved. Serial text was exported from the real
browser's rendered Serial output, with normalized line endings; event JSON was
not recreated from test expectations. Source files actually uploaded for each run,
screenshots, browser diagnostics, action values and a Playwright trace are retained.

`capture_adapter.py` reuses `wokwi_serial_adapter.validate_capture` for its strict
JSON, field/type/range, status, counter and heartbeat/transition checks. It selects
the applicable checks and explicitly labels the HC-SR04 variant, rather than
reusing the original firmware's source-review hashes or old “sensor never read”
conclusions. It additionally checks pulse/distance diagnostic consistency.

A separate real Wokwi run disconnected ECHO in that run's isolated diagram:
`pulseIn` returned zero, diagnostics remained untrusted/faulted, and **no occupancy
JSON** was emitted. Recovery and threshold edge cases were tested in the same
compiled C++ logic, including a test firmware run inside Wokwi. No wire was removed
from the original or final healthy diagrams.

### Direct ESP32 MQTT: observed limitation

The isolated `network-probe/sketch.ino` joined `Wokwi-GUEST`. Actual Serial output:

```text
[NETWORK] wifi_ip=10.10.0.2
[NETWORK] host=host.wokwi.internal port=18884 tcp_connected=0
[NETWORK] DONE; no MQTT packets transmitted by this probe
```

The Windows loopback broker was running, but the simulator used the **public
gateway**. That gateway cannot access the computer's local network. A simulator's
`127.0.0.1` is not Windows localhost. Wokwi documents `host.wokwi.internal` for its
**private gateway**, which runs locally and requires an eligible paid setup; no
private gateway/account was configured here. [Wokwi ESP32 networking](https://docs.wokwi.com/guides/esp32-wifi).

Wi-Fi association alone therefore does not demonstrate MQTT delivery. Since TCP
failed before MQTT was possible, **no direct ESP32 MQTT publisher/reconnect path
was claimed or marked passing**. The main measured-sensor sketch remains Serial
only; the network probe is separate. Direct firmware MQTT publishing and its
reconnect/queue behavior remain unimplemented/unverified pending a usable private
route. A future client must match this harness's MQTT 3.1.1/QoS 1/retain=false policy;
a default QoS 0 publisher would not satisfy it.

No broker was made public, no bind address was widened, no firewall/router rule
was changed, and no tunnel/public broker was deployed. With an authorized private
gateway, repeat the probe first; observed broker traffic and persisted receipts
would still be required before reporting direct publishing success.

### Safe local alternative, verified

The new captured ultrasonic JSON can be replayed **locally** through the actual
MQTT broker using `publish_sensor_capture.py`. The verified path is:

```text
Wokwi HC-SR04 trigger/echo measurement
  → saved new 7-event Serial capture
  → Python capture publisher (explicit replay)
  → real loopback MQTT broker
  → existing reference backend validation and SQLite commit
  → availability API
```

The new integration test used its own broker and database, received all 7 events,
compared every persisted payload against the capture and checked the API: A01
Available at counter 6, A02/A03 Unknown. Broker, PUBACK, subscriber commit/ACK,
SQLite file and API evidence are saved. This is **not** live ESP32-to-MQTT.
The existing 173-test regression includes real-browser persisted-state rendering;
the new seven-event alternative was specifically checked through its database/API,
not a separate seven-event dashboard browser scenario.

### Reproduce the real Wokwi runs

Existing Playwright/Edge setup is reused. From this workspace:

```powershell
Set-Location D:\Smart-Parking-System
node integration-validation/demo/sensor-wokwi/run_wokwi.cjs capture
node integration-validation/demo/sensor-wokwi/run_wokwi.cjs timeout
node integration-validation/demo/sensor-wokwi/run_wokwi.cjs selftest
node integration-validation/demo/sensor-wokwi/run_wokwi.cjs network
```

Each invocation opens a new unsaved Wokwi ESP32 editor, inserts only the isolated
files and produces a new timestamped evidence directory. Network access to Wokwi,
its build service and installed Edge/Playwright are required; queues can take
minutes. `selftest` compiles with `SENSOR_SELF_TEST=1`; normal measurement keeps it
0. `timeout` removes the ECHO wire only in the uploaded test diagram. `network`
uses only the independent Wi-Fi probe. All browsers close after their run.

For manual verification, open `https://wokwi.com/projects/new/esp32`, copy the two
isolated firmware files into its sketch/diagram tabs, start simulation, click the
HC-SR04 and set its slider. Use 10 cm long enough to confirm Occupied and 35 cm
long enough to confirm Free. Copy Serial output to a **new** evidence file. Do not
replace `wokwi-source/` or the original `captures/wokwi_serial_actual.txt`.

Optional host compiler installation for the compiled C++ checks:

```powershell
& 'python' -m pip install --target integration-validation/demo/sensor-wokwi/tools -r integration-validation/demo/sensor-wokwi/requirements-host.txt
& 'python' integration-validation/demo/sensor-wokwi/run_checks.py
& 'python' integration-validation/demo/sensor-wokwi/summarize_evidence.py
```

Zig 0.15.1 supplies an isolated Windows native C++ compiler. Host GPIO/clock stubs
are explicit fixtures, never described as Wokwi or hardware evidence. The host
runner includes the actual sketch and runs 20 logic assertions plus one GPIO/API
contract assertion. Its synthetic JSON output is labelled separately. The Python
suite uses the pinned recorded real Wokwi evidence, so rerunning it verifies those
records; it does not itself run Wokwi. The four browser commands above execute new
simulations. The same 20 logic cases also passed inside Wokwi; they are **not
counted twice** in the combined assertion total.

To run the local replay alternative without touching the existing databases,
start these in separate terminals (same working directory):

```powershell
node integration-validation/demo/mqtt/broker.mjs 18885
```

```powershell
& 'python' integration-validation/demo/backend/backend_server.py --mqtt-port 18885 --port 8768 --db integration-validation/demo/sensor-wokwi/data/hcsr04-reference.sqlite3 --stream hcsr04-capture-1
```

```powershell
& 'python' integration-validation/demo/sensor-wokwi/publish_sensor_capture.py integration-validation/demo/evidence/sensor-wokwi-capture-2026-11-11T13-43-58-176Z/serial_actual.txt --port 18885 --interval 1
```

The optional dashboard would be `http://127.0.0.1:8768/backend/`. Those persistent
alternative-demo processes are not left running by the tests: their own temporary
broker/backend objects were cleaned up. For repeated full replays, choose a new
`--stream` or new database path; keep previous data. The existing brokers,
databases and modes on 8765/8766/8767 remain independent.

### Final results and evidence

| Automated checks | Passed | Failed | Errors | Skipped |
|---|---:|---:|---:|---:|
| All prior Python/JavaScript/real-browser regressions | 173 | 0 | 0 | 0 |
| Compiled actual-sketch host logic and GPIO assertions | 21 | 0 | 0 | 0 |
| New sensor-capture/measurement/network-limit/MQTT-SQLite Python tests | 9 | 0 | 0 | 0 |
| **Total** | **203** | **0** | **0** | **0** |

Additionally, the four real Wokwi scenario runs succeeded as described: sensor
controls/capture, timeout, 20-case firmware selftest and a network probe documenting
the expected local-connectivity failure. The network result is **not an MQTT
success**, and unavailable physical/direct transport acceptance tests are not
counted as skipped automated tests or as passing integration paths.

Evidence directories under `integration-validation/demo/evidence/`:

- `sensor-wokwi-capture-2026-11-11T13-43-58-176Z/`: final actual seven-event capture,
  uploaded source/diagram, slider actions, measurements, screenshots and trace.
- `sensor-wokwi-timeout-2026-11-11T13-40-00-359Z/`: actual disconnected-ECHO output,
  uploaded test diagram and trace. This run preceded only the upper-range-margin
  change; zero-timeout logic is unchanged and was rechecked in the final selftests.
- `sensor-wokwi-selftest-2026-11-11T13-43-59-425Z/`: 20/20 actual simulated-ESP32
  firmware assertions, including maximum-range guard and millis wraparound.
- `sensor-wokwi-network-2026-11-11T13-38-36-024Z/`: actual simulated Wi-Fi address
  and failed local TCP probe, source, screenshot and trace.
- `sensor-tests-20261111T134610488617Z/`: final host compiler output, 21 host passes,
  9 Python passes, source-aware capture validation, real local MQTT broker/client
  journals, seven-event SQLite database and API snapshot.
- `sensor-summary-20261111T134624316763Z/`: aggregate **203/0/0/0** results, capture
  validation and preserved-original hashes; final uploaded sketch matches the
  local isolated sketch byte-for-byte, and diagrams match structurally.
- Regression reruns: `20261111T133510483858Z/` (81+16 Python, 6 JS),
  `mqtt-tests-20261111T133511889763Z/` (18),
  `backend-tests-20261111T133516150655Z/` (26),
  `browser-2026-11-11T13-35-23-725Z/` (12),
  `mqtt-browser-2026-11-11T13-36-05-946Z/` (7),
  `backend-browser-2026-11-11T13-36-38-712Z/` (7).

Earlier successful captures, initial build-queue inspection and previous host/
firmware test runs are retained. No old captured messages or database rows were
substituted for the new ultrasonic observations.

Screenshot examples:

- [Wokwi at 10 cm with measured Occupied output](docs/EVIDENCE.md)
- [Wokwi at 35 cm with measured Free output](docs/EVIDENCE.md)

### Changed files and remaining limitations

Modified existing file: `INTEGRATION_DEMO_README.md` only. Added under
`integration-validation/demo/sensor-wokwi/`:

- `firmware/sketch.ino`, `firmware/diagram.json`
- `network-probe/sketch.ino`
- `host/Arduino.h`, `host/main.cpp`
- `capture_adapter.py`, `publish_sensor_capture.py`
- `test_sensor.py`, `run_checks.py`, `summarize_evidence.py`
- `run_wokwi.cjs`, `probe_browser.cjs`
- `requirements-host.txt`, `.gitignore`

Generated: browser-access inspection JSON/PNG, ignored compiler/tools/cache and
native executable/PDB, Python cache, and the new timestamped evidence above.
The original firmware, diagram, old capture, frontend, reference backend,
database and existing tests/modes remain preserved. No academic report or
presentation was edited. No project save, Git commit/push or external deployment
was performed.

Still unverified/unimplemented: physical HC-SR04 accuracy/electrical setup, actual
ESP32 hardware, second-sensor fusion, measured battery, private gateway route,
direct firmware MQTT publish/reconnect/queue behavior, production backend acceptance
and physical end-to-end latency/recovery. Sensor faults are visible in Serial but
not exported as a new backend health protocol. Wokwi simulation timestamps are not
wall-clock latency evidence. These limits do not invalidate the observed simulated
trigger/echo measurements or the separately verified local replay transport.

## Five-stage completion and final technical audit

Completed on 11 November 2026. **Ready for a local simulated-sensor demonstration**
with the dependencies and network access described here. This is not physical
sensor acceptance, production backend acceptance or direct ESP32 Wi-Fi MQTT.

### Stage 1 — live Wokwi Serial bridge: implemented and verified

```text
running Wokwi ESP32 + actual virtual HC-SR04 trigger/echo measurement
  → newly rendered Serial event in the local Edge browser
  → live Serial cursor (complete frames only; no saved capture input)
  → stdin to local Python MQTT worker
  → real loopback MQTT 3.1.1 / QoS 1 / retain=false
  → reference subscriber / transactional SQLite commit
  → SQLite-backed API
  → real Edge Dashboard / Admin View
```

The browser bridge starts a fresh, unsaved Wokwi editor using the existing isolated
HC-SR04 firmware. It reads newly emitted Serial lines while the simulation runs.
It never opens `serial_actual.txt` or another saved capture as an input. Evidence
journals record actual observations and publish acknowledgements; they are outputs,
not replay inputs. Raw received event bytes match the source observation and the
database/history API in the real-browser test.

Changing the HC-SR04 slider from initial Far to **10 cm**, then **35 cm**, changed
the Dashboard **Available → Occupied → Available**. A01 maps to 1001; A02/A03 stay
Unknown. The firmware, original frontend and existing captured-replay modes were
not rewritten. The only firmware file read by this live bridge is the preserved
isolated measured-sensor variant, used to compile a new simulation.

This is a **live simulated-sensor Serial-to-MQTT bridge**. It is neither captured
event replay nor direct ESP32 network publishing. The Wokwi public-gateway
limitation remains; the bridge works because the local browser/host reads Serial
and the local Python client connects to the local broker.

Complete JSON frames are required before forwarding. UART output can render in
fragments: a partial final frame waits for completion. A broken completed frame,
Serial reset/truncation or more than 256 pending events stops the bridge explicitly
instead of dropping data or restarting a replay. The cursor tracks **Serial line
ordinal**, not uint8 counter identity, so wraparound is not mistaken for an old
globally unique event. Backend validation remains authoritative for schema,
duplicates, gaps, ordering and state transitions.

The worker retries a temporarily unavailable MQTT connection for up to 30 seconds
without discarding the pending event. There is no durable outbox or guaranteed
lossless delivery across process crashes. Broker PUBACK is not proof of a database
commit; the integration tests separately inspect committed rows and the UI.

### Stage 2 — backend/database validation and live health

Saaket's actual backend/database is still absent. The existing **reference backend**
is reused and labelled; no unavailable production component was represented as
integrated. Its schema/current-history/checkpoint logic remains as documented above.
The live wrapper adds only input-mode labels and bridge-health handling.

Source events still use the existing six-field event topic:
`smart-parking/integration-test/wokwi/node-1/events`.
Bridge health uses a separate local harness topic:
`smart-parking/integration-test/wokwi/node-1/events/bridge-health`.
Both use QoS 1, retain=false and the existing local broker namespace policy.
Health messages do **not** become parking-state history rows.

The live API adds `input_mode: LIVE_WOKWI_SERIAL_BRIDGE`, `replay: false` and
`bridge` information. The health states include `streaming`, `sensor_untrusted`,
`source_stalled`, `offline`, `health_stale`, `unknown`, and `broker_disconnected`.
An unchanged diagnostic stream for more than 5 host-wall seconds is marked
`source_stalled`; health receipts older than 10 seconds are marked `health_stale`.
These refer to observed browser/bridge activity, **not physical sensor connectivity**.
The worker has an MQTT offline will and also publishes offline on normal shutdown.

The UI displays this health separately from persisted last-known occupancy. A
stopped/untrusted bridge clears freshness and labels last-known state; it does not
invent Free or delete history. HTTP/backend failure shows Unknown. New sensor
receipts restore freshness. The live browser test verifies Offline after stopping
the source while preserving its last committed Available state.

Validation covers strict message schema, malformed input, equal-counter duplicates,
same counter with different payload, repeated heartbeats, gaps/reordering,
counter wrap, actual broker loss/reconnect, Unknown bays, durable checkpoints,
backend process restart, transaction rollback and recovery. The original reference
database and original captures remain intact; new tests use isolated databases,
ports and stream namespaces.

### Stage 3 — consolidated automated verification

Single full-workflow command:

```powershell
Set-Location D:\Smart-Parking-System
& 'python' integration-validation/demo/run_system_checks.py
```

The runner executes each existing suite plus live/audit/startup tests, captures
their logs and connects each result to a **new directory created by that specific
execution**. It does not silently aggregate old “latest” successes. Nonzero child
exit codes, missing result artifacts, timeouts, failures and errors cause overall
FAIL. Later unaffected suites continue so the final report records available
results. It can start an owned replay server on 8765 if missing; it reuses the
matching existing replay service read-only and never kills an unrelated listener.

The full run requires Windows, the installed Python, Node, Paho/Aedes, Edge,
Playwright, optional-host-test compiler and internet access to Wokwi. Build queues
can take minutes. `--without-live` explicitly omits the live Wokwi E2E and startup
suite, records them **NOT RUN**, and sets `full_verification=false`; it must not be
reported as full verification. Unavailable physical acceptance work is not counted
as a skipped automated test or as a pass.

**Final actual results:**

| Suite | Passed | Failed | Errors | Skipped |
|---|---:|---:|---:|---:|
| Original validation Python | 81 | 0 | 0 | 0 |
| Existing replay Python | 16 | 0 | 0 | 0 |
| Existing JavaScript DOM/HTTP | 6 | 0 | 0 | 0 |
| Existing MQTT Python | 18 | 0 | 0 | 0 |
| Existing backend/database Python | 26 | 0 | 0 | 0 |
| Existing sensor native C++ assertions | 21 | 0 | 0 | 0 |
| Existing sensor Python | 9 | 0 | 0 | 0 |
| Existing replay real Edge | 12 | 0 | 0 | 0 |
| Existing memory MQTT real Edge | 7 | 0 | 0 | 0 |
| Existing persisted-backend real Edge | 7 | 0 | 0 | 0 |
| New live/backend audit Python | 11 | 0 | 0 | 0 |
| New Serial cursor/framing Node tests | 8 | 0 | 0 | 0 |
| New live Wokwi-to-Dashboard real Edge test | 1 | 0 | 0 | 0 |
| New PowerShell startup/shutdown tests | 7 | 0 | 0 | 0 |
| **Total** | **230** | **0** | **0** | **0** |

The first ten rows are exactly the prior **203 checks**, all rerun. The remaining
27 are new. As before, the 20 firmware logic assertions also verified inside Wokwi
are not counted twice. Browser startup tests additionally invoke Edge internally;
those assertions belong to their listed Python test case, not another invented
TAP count.

Measured metric: in the final live test, three observations took **174.7 / 423.1 /
454.3 ms** from the browser bridge observing a complete Serial event to the tested
Dashboard observation. These use the same Node process's monotonic wall clock.
They exclude source sensing/debounce and simulator/build timing and are only a
three-sample local software-path observation. They establish neither physical-to-web
latency nor a three-second acceptance guarantee. No physical accuracy was measured.

Final consolidated evidence:
`integration-validation/demo/evidence/system-20261111T141902223336Z/results.json`.
This manifest names all individual run directories, counts, commands, exit codes,
durations, original-file hashes and per-suite console logs.

Key accompanying evidence:

- `live-browser-20261111T142111942417Z/`: real new Wokwi Serial observations,
  raw publishes, real broker log, database, API/history/UI proof, offline-health
  verification, metrics, screenshots and Wokwi/Edge trace.
- `live-tests-20261111T142107109592Z/`: final 11 Python + 8 Node checks, real MQTT
  fault/recovery records and audit regressions.
- `startup-tests-20261111T142134922536Z/`: seven passing actual PowerShell startup
  tests, manifests, stdout/stderr, graceful child exit codes, persistence/restore,
  port conflict/dependency checks and live-cycle Dashboard screenshot.
- `technical-audit-20261111T142458988068Z/audit.json`: read-only final technical
  audit of that exact consolidated run, verified live proof, source hashes,
  original frontend Git-clean status, metrics and unresolved limitations.

Earlier evidence is preserved. The first consolidated run was 218/0/0/0 before
the UART, launcher and final audit additions. Startup run
`startup-tests-20261111T141103269755Z/` genuinely recorded 5 passed/1 failed due
to the Windows manifest-sharing bug. The next run at
`startup-tests-20261111T141253999940Z/` exposed partial UART forwarding and was
aborted after its exited-service wait failed to terminate promptly; it is an
incomplete run, not a passing test count. Its trace/logs remain. Audit run
`live-tests-20261111T141759960036Z/` recorded 1 failure and 2 errors in newly added
regressions before the corresponding fixes. Final passing runs are separate;
no failed evidence was overwritten or reclassified as success.

Example final live proof screenshot:
[Live bridge stopped, labelled last-known state retained](docs/EVIDENCE.md).

### Stage 4 — one-command Windows startup and clean shutdown

From `D:\Smart-Parking-System`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-LocalDemo.ps1 -Mode Live
```

The execution-policy option applies to this script process; no persistent Windows
policy is changed. The default Live command starts a fresh local broker on
**127.0.0.1:18890**, a managed live reference backend/dashboard on
**http://127.0.0.1:8780/backend/** and an interactive Wokwi Edge window. The browser
compiles the measured-sensor sketch and waits for real simulation output. No old
capture is seeded in Live mode. “Services ready” does not mean that Wokwi's build
has finished; the health banner shows the actual source state.

Select the HC-SR04 in the Wokwi window and set 10 cm to confirm Occupied or 35 cm to
confirm Free. Open the Dashboard URL and Admin View to inspect committed rows,
counter, heartbeat/transition, receipt time and bridge health. `-Headless` runs the
browser without its interactive window. `-DemoCycle` is an explicit automated
**virtual slider** demonstration (10 then 35 cm); it still measures simulated
trigger/echo and never synthesizes occupancy JSON in JavaScript.

The script checks Python/Node and required local files/dependencies, rejects
occupied ports and missing dependencies clearly, waits for broker/subscriber/HTTP
readiness and owns only its created child processes. It does not automatically
install dependencies, expose services, change firewall rules or kill existing
listeners. Helpers run without extra console windows; the Live Wokwi window is
intentionally interactive. If startup fails, owned services are cleaned up.

If default ports are occupied, reuse the running demo, stop its own session, choose
different values, or let Windows choose free ports:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-LocalDemo.ps1 -Mode Live -BrokerPort 0 -HttpPort 0
```

The exact chosen URL/ports are printed and stored in a timestamped `session.json`.
Default database is `integration-validation/demo/local_stack/data/local-demo.sqlite3`.
Each default startup uses a new stream namespace in the same file, preserving old
history and avoiding a restarted sensor's counter-zero being mistaken for a
continuation. To restore an existing dataset without creating a source, use
Reference mode with the same `-Database` and `-StreamId`, without `-SeedCapture`.
Live/seeded startup refuses a nonempty existing stream instead of silently replaying
counter zero into it.

Useful independent modes:

```powershell
# Explicit capture replay through MQTT and persistent reference backend:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-LocalDemo.ps1 -Mode Reference -SeedCapture
# Restore/reference API only, without automatically publishing anything:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-LocalDemo.ps1 -Mode Reference -Database <path> -StreamId <existing-stream>
# Independent memory MQTT mode, file replay, or original frontend simulation:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-LocalDemo.ps1 -Mode Memory
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-LocalDemo.ps1 -Mode Replay
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-LocalDemo.ps1 -Mode Simulation
```

Reference `-SeedCapture` is deliberately labelled captured-event replay and uses a
new stream by default. The old manual component commands on ports 8765/8766/8767
still work independently. The launcher does not discard their modifications/data.
Options also include `-PythonPath`, `-SessionDirectory`, `-DurationSeconds`,
`-Database`, `-StreamId`, `-BrokerPort` and `-HttpPort`.

Dependencies are the already documented Python 3.14.7, Node v24.22.1, isolated
Paho 2.1.0/Aedes 1.2.0, Playwright 1.65.0 and installed Edge 157.0.4341.42 tested
here. Live mode needs Wokwi internet/build access; Reference replay does not.
Install the existing pinned npm/pip requirements from earlier sections when
missing. Optional Zig is needed for the full sensor host-test suite, not to launch
the demo. A different Python can be selected with `-PythonPath` or `PARKING_PYTHON`.

Clean stop: Ctrl+C in the foreground launcher, or use its printed session directory
from a second terminal:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Stop-LocalDemo.ps1 -SessionDirectory <printed-session-directory>
```

Stop sends an owned stop request. The bridge stops reading, publishes offline and
closes its browser/worker; the backend stops its HTTP and MQTT loops; the broker
closes afterward. Data and evidence are retained. Startup tests verify normal
zero child exit codes, released listener ports, cancellation during Wokwi startup
and database restoration. A graceful bridge timeout is recorded and returns an
error rather than claiming a clean success. The session manifest records any
failure/forced cleanup; inspect it if shutdown was abnormal.

**Current handoff session** (started and observed streaming after the tests):

- Dashboard: **http://127.0.0.1:8780/backend/**
- Broker: loopback **18890**
- Stream: `session-d7ee33e5c19d44f3`
- Manifest/logs: `integration-validation/demo/evidence/local-handoff-20261111T142343Z/`
- Database: `integration-validation/demo/local_stack/data/local-demo.sqlite3`
- The Wokwi window is interactive; bridge health was `streaming`, with no rejected
  or duplicate source events when checked. Process persistence after this coding
  session depends on the Windows host.

Exact stop for this running handoff before reusing its default ports:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Stop-LocalDemo.ps1 -SessionDirectory .\integration-validation\demo\evidence\local-handoff-20261111T142343Z
```

### Stage 5 — final technical audit and demonstrated fixes

| Finding | Demonstrated effect | Final resolution |
|---|---|---|
| Windows session manifest read/replace race | startup failed with WinError 5 while a reader briefly held `session.json` | bounded atomic-replace retry, plus cleanup that runs even when manifest updates fail; regression passes |
| Partial Wokwi UART JSON treated as malformed | live bridge forwarded `{"spot_id":1001,"occupi` and exited | buffer until complete frame, reject genuinely broken completed frames, retain ordering; two new framing regressions pass |
| Foreign DB refusal changed its journal mode | an unrelated fixture DB became WAL before being rejected | read-only schema inspection precedes write pragmas; its journal/data remain unchanged |
| Optional evidence-log write failure interrupted post-commit ACK | durable event was committed but an OSError escaped the subscriber callback | optional text journaling is isolated from durable receipt commit/ACK; health exposes `journal_warning`; regressions pass |

The subscriber still refuses ACK on a **database commit failure**. The optional
text-log fix does not convert DB failure into success: durable auditing lives in
SQLite transactions, while text-journal failure is visible as a separate warning.
No physical accuracy, sensor-to-web three-second limit, live ESP32 network path or
production database correctness was fabricated.

Open integration/design limits:

- No physical HC-SR04/ESP32 acceptance; battery remains a placeholder and no actual
  second magnetic sensor/fusion source exists.
- Direct ESP32 Wi-Fi MQTT remains blocked in this public-gateway setup. The working
  live route is the local browser Serial bridge, not an ESP32 MQTT firmware client.
- Saaket's actual production backend/database, production contracts, TLS/auth,
  durable broker/outbox and globally durable source event/session IDs are missing.
- Wokwi UI/build availability and rendered Serial format are dependencies. Resets,
  truncation, excess backlog or extended MQTT outage fail closed. There is no
  automatic relabelling of a saved capture as live or a lossless-delivery claim.
- Last-known state is intentionally retained and labelled; local bridge/receipt
  health is not physical connectivity. A backend outage while the in-memory clean-
  session broker continues can require replaying missing records or starting a
  new stream; no exactly-once guarantee is made.
- Only this Windows/Edge setup was verified. Long-duration production operation,
  other browser engines and destructive storage/hardware failure are not accepted.

### Exact files created or modified in this five-stage task

Modified existing files:

- `INTEGRATION_DEMO_README.md`
- `integration-validation/demo/backend/store.py` — focused database-preservation
  and optional-journal fixes; no teammate source was edited.

Created at workspace root:

- `Start-LocalDemo.ps1`
- `Stop-LocalDemo.ps1`

Created under `integration-validation/demo/`:

- `run_system_checks.py`
- `audit_system.py`

Created under `integration-validation/demo/live/`:

- `.gitignore`, `bridge.cjs`, `bridge.test.cjs`, `mqtt_worker.py`
- `live_backend.py`, `run_live.cjs`, `verify_live.cjs`, `run_e2e.py`
- `test_live.py`, `run_checks.py`

Created under `integration-validation/demo/local_stack/`:

- `.gitignore`, `managed_broker.mjs`, `managed_backend.py`, `supervisor.py`
- `verify_stack.cjs`, `test_startup.py`, `run_checks.py`

Generated state: new ignored live/local-stack databases and Python caches, plus
the new timestamped evidence/session logs listed above. Original firmware/diagram,
old Serial captures, original frontend and previous databases/evidence were
preserved. Read-only audit confirmed the teammate frontend remains Git-clean and
the original reference service still reported 22 accepted, 0 duplicate, 0 rejected
events. No university report, presentation, Git commit/push, firewall exposure or
external deployment occurred.
