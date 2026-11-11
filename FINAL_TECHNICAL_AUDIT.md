> Publication copy: host-specific paths and archived evidence links are sanitized. Start with [README.md](README.md) for fresh-clone setup. Original local documents and evidence are preserved.

# Final technical audit: local three-bay virtual-sensor prototype

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

Final complete regression: **255 passed, 0 failed, 0 errors, 0 skipped**. All original 247 tests are included. The earlier interrupted-workflow run completed with 254/0/0/0; the later denied-SUBACK test is included in this fresh final run.

The first resumed full run, `system-20261111T185541768436Z`, recorded **254 passed, 1 failed, 0 errors, 0 skipped**. Its three-channel MQTT test could publish before initial untrusted health had been superseded at the subscriber; a late startup health message correctly cleared freshness. The fixture now waits for actual subscribed online health before injecting events. Occupancy, persistence and freshness assertions remain unchanged. That failed evidence is preserved; the final counts above are from a subsequent complete rerun.

| Suite | Passed | Failed | Errors | Skipped |
| --- | ---: | ---: | ---: | ---: |
| regression | 103 | 0 | 0 | 0 |
| mqtt | 18 | 0 | 0 | 0 |
| backend | 26 | 0 | 0 | 0 |
| sensor | 30 | 0 | 0 | 0 |
| replay_browser | 12 | 0 | 0 | 0 |
| mqtt_browser | 7 | 0 | 0 | 0 |
| backend_browser | 7 | 0 | 0 | 0 |
| live_contract | 19 | 0 | 0 | 0 |
| multi_contract | 23 | 0 | 0 | 0 |
| live_e2e | 1 | 0 | 0 | 0 |
| startup | 8 | 0 | 0 | 0 |
| multi_browser | 1 | 0 | 0 | 0 |

Supplementary preserved runs: final controlled performance 1 passed; extended performance/stability 1 passed; high-volume transport 1 passed, each with zero failed/cancelled/skipped (volume zero errors). These are separate scenario executions, not inflated per-assertion counts. [Full regression results](docs/verification-summary.json), [final machine-readable audit](docs/verification-summary.json).

Actual Microsoft Edge verifies independently changing A01/A02/A03, concurrent transitions, real virtual ECHO failure, unknown/last-known separation, Dashboard/Admin consistency, history filters, API failure/recovery, responsive layout, broker outage, backend restart and persisted rows. Root launcher start, browser check, graceful stop with all three children exit 0, restart on the same ports and second real-browser check are recorded in [start/stop evidence](docs/verification-summary.json) and [restarted handoff](docs/verification-summary.json). No physical or direct ESP32 MQTT acceptance claim is made.

## Performance: 30 Occupied and 30 Free trials

Final instrumented run: [raw trials](docs/verification-summary.json), [statistics](docs/verification-summary.json). Each direction has n=30 at 200 ms Dashboard polling, distributed across all three bays, with 0/30 propagation failures (15-second observation timeout). p95 uses nearest rank. Durations below are milliseconds.

| Metric | Minimum | Median | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Occupied virtual control -> DOM | 1666.60 | 1861.40 | 1971.50 | 2002.00 |
| Available virtual control -> DOM | 2723.30 | 2902.30 | 3038.80 | 3059.70 |
| Occupied observed confirmed Serial -> DOM | 49.60 | 185.45 | 259.00 | 264.80 |
| Available observed confirmed Serial -> DOM | 68.30 | 189.90 | 282.20 | 294.60 |

The first metric begins immediately before the browser sets the virtual distance control and ends after the Dashboard DOM contains the matching committed event ID. It includes virtual measurement/debounce and all host processing. The second begins when the bridge observes the already-confirmed Serial JSON on the host; it excludes any earlier simulated UART/browser rendering delay. Exact firmware-confirmation-to-host elapsed time cannot be obtained by subtracting unsynchronized firmware millis from host UTC. DOM completion is measured, not display paint or physical sensing latency. Physical end-to-end latency remains unverified.

There were **0/30 Occupied and 6/30 Free observations over 3000 ms**. These target exceedances are distinct from propagation failure. No universal three-second compliance is claimed.

Boundary evidence separates the main contributors:

| Boundary | Minimum | Median | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Occupied / simulated_confirmation_ms | 1531.00 | 1546.00 | 1548.00 | 1549.00 |
| Occupied / control_to_serial_ms | 1600.00 | 1657.00 | 1773.00 | 1819.00 |
| Occupied / publish_to_receive_ms | 1.05 | 1.22 | 1.63 | 1.85 |
| Occupied / validation_transaction_ms | 10.32 | 13.02 | 15.93 | 21.24 |
| Occupied / commit_to_dom_ms | 10.93 | 91.20 | 163.04 | 180.11 |
| Occupied / api_fetch_parse_ms | 10.00 | 11.15 | 21.50 | 24.70 |
| Occupied / dom_build_ms | 0.20 | 0.30 | 0.40 | 0.40 |
| Available / simulated_confirmation_ms | 2548.00 | 2580.00 | 2588.00 | 2588.00 |
| Available / control_to_serial_ms | 2626.00 | 2726.50 | 2842.00 | 2859.00 |
| Available / publish_to_receive_ms | 1.10 | 1.27 | 1.59 | 2.71 |
| Available / validation_transaction_ms | 11.10 | 12.62 | 18.59 | 25.57 |
| Available / commit_to_dom_ms | 21.71 | 92.91 | 173.99 | 181.21 |
| Available / api_fetch_parse_ms | 9.30 | 11.25 | 12.70 | 12.80 |
| Available / dom_build_ms | 0.20 | 0.30 | 0.40 | 0.40 |

The historical 3136 ms sample was a Free transition and necessarily included its configured 2500 ms debounce. Historical instrumentation cannot attribute its remaining 636 ms exactly. Current firmware-clock confirmation deltas, host Serial observation, publish/receive, transaction commit, HTTP fetch/parse and DOM-build times show debounce dominates Free latency; MQTT/SQLite/DOM building are small contributors in this sample. Validation/transaction timing includes locking and durable SQLite work, not an isolated disk benchmark. commit-to-DOM combines polling wait, HTTP and DOM work; commit-to-poll-start can be negative when a request was already in flight at commit. Host wall-clock cross-process timings are distinct from firmware simulation-clock deltas.

At the preserved 500 ms comparison cadence (n=9 per direction), control-to-DOM medians were 2022.40 ms Occupied and 3118.40 ms Free. At 200 ms (n=30) they were 1861.40 and 2902.30 ms. This observed improvement is consistent with reduced polling quantization. These are sequential, unequal-size local samples with background test load, not a randomized benchmark or population-level guarantee. busy guards prevent overlapping polls; debounce and integrity checks are unchanged. Default requests increase from about 2 to 5 per second per tab, a deliberate local-demo tradeoff.

## Bounded stability, memory and high volume

The extended run lasted 371.595 seconds including online compiler/startup and controlled trials, with 184.427 seconds in its dedicated stability phase. It observed 199 live Serial events, 77 heartbeats and 199 distinct committed keys. Missing observed events: 0; SQLite integrity: ok; transport retry records: 1. Real broker interruption/reconnect and backend process restart were exercised during the same source session. [Stability evidence](docs/verification-summary.json), [resource samples](docs/verification-summary.json), [screenshot](docs/EVIDENCE.md).

| Process role | Initial RSS MiB | Final RSS MiB | Peak RSS MiB |
| --- | ---: | ---: | ---: |
| backend | 36.2 | 36.7 | 36.9 |
| broker | 62.3 | 64.8 | 64.8 |
| runner | 101.3 | 297.4 | 329.0 |
| serial_worker | 35.4 | 35.8 | 35.8 |

The Node runner combines the live browser bridge, Playwright transport, full Serial DOM polling, metric arrays and test log parsing; it is not the browser Dashboard process. Its material RSS growth is unresolved. Sampled heap used started at 42.2 MiB, peaked at 184.5 MiB and ended at 123.9 MiB. That decline shows allocation/GC and reserved heap contribute, but no heap-retention profile proves the absence of a leak. Backend/broker/worker RSS stayed near their initial ranges in this bounded sample; backend and broker role samples span intentional process restarts, not a single continuous PID lifetime. This does not establish long-term memory stability. Edge child-tree RSS was not measured. Serial history and evidence logs grow with run length; do not treat this as an hours/days endurance qualification. Restart between bounded demonstrations.

Database-family sampled bytes (including transient WAL/SHM): initial 65536, final 323584, peak 1947640. These are race-tolerant sampled file sizes, not atomic disk-accounting snapshots. Durable event/history growth is expected; production retention is not implemented.

The separate [volume test](docs/verification-summary.json) uses explicitly HARNESS-GENERATED messages, not sensor measurements: 900 transmitted through actual MQTT/outbox/backend, 900 accepted rows, 3 duplicate deliveries without added event rows, 6 malformed/out-of-order rejections, zero missing accepted events, integrity ok. Each bay processes 300 frames, crosses counter wrap and ends at ctr43. 25 resource samples were collected. An initial volume attempt passed transport assertions but its resource monitor died while a WAL/SHM file disappeared; that incomplete monitoring evidence is retained at volume-20261111T161943586162Z and is not used to claim memory stability. File sampling was fixed and the monitored test rerun successfully.

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
Set-Location D:\Smart-Parking-System
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-LocalDemo.ps1 -Mode Multi
```

Open http://127.0.0.1:8780/backend/. Wait for 3/3 online; all bays are Unknown until valid sourced observations arrive. Select each HC-SR04 in the interactive Wokwi window: 10 cm produces Occupied, 35 cm produces Available after unchanged debounce. Check Admin mapping, latest ctr/heartbeat and persisted history. Fault switches independently ground ECHO and make that bay Unknown while preserving labeled last-known state. The currently verified handoff directory is `integration-validation/demo/evidence/stabilization-handoff-20261112`; it uses a fresh stream within the existing multi-demo.sqlite3 file without overwriting older rows.

Stop the current handoff:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Stop-LocalDemo.ps1 -SessionDirectory .\integration-validation\demo\evidence\stabilization-handoff-20261112
```

For a subsequent launcher, use its printed session directory or Ctrl+C. Restart with the simple startup command to create a fresh manifest and firmware namespace; do not reuse an existing session manifest. Ports 8780/18890 are checked; unrelated listeners are never killed. Other modes require their explicit Mode selection and separate ports or a stopped instance.

Reproduce verification (the first command includes all 247 original tests plus final regressions):

```powershell
& 'python' integration-validation/demo/run_system_checks.py
& 'python' integration-validation/demo/multi/run_performance.py --rounds 10 --soak-seconds 180
& 'python' integration-validation/demo/multi/run_volume.py
```

Every command creates a new evidence directory. Existing captures/databases/results are preserved. Source SHA-256 fingerprints are saved in [integration-validation/demo/evidence/stabilization-audit-20261111T190633584927Z/source_sha256.final.json](docs/verification-summary.json); this is a local reproducibility manifest, not a Git commit or immutable release.

## Exact files created or changed since the 247-test handoff

- `integration-validation/demo/multi/model.py`
- `integration-validation/demo/multi/outbox.py`
- `integration-validation/demo/multi/bridge.cjs`
- `integration-validation/demo/multi/build_firmware.py`
- `integration-validation/demo/multi/firmware/sketch.ino`
- `integration-validation/demo/multi/browser_fixture.py`
- `integration-validation/demo/multi/web/dashboard.js`
- `integration-validation/demo/multi/test_multi.py`
- `integration-validation/demo/multi/performance_tools.py`
- `integration-validation/demo/multi/performance.test.cjs`
- `integration-validation/demo/multi/run_performance.py`
- `integration-validation/demo/multi/run_volume.py`
- `integration-validation/demo/multi/stabilization_audit.py`
- `INTEGRATION_DEMO_README.md`
- `FINAL_TECHNICAL_AUDIT.md`
- `integration-validation/demo/evidence/stabilization-audit-20261111T190633584927Z/results.json`
- `integration-validation/demo/evidence/stabilization-audit-20261111T190633584927Z/source_sha256.json`

New per-run evidence files are contained in the linked evidence directories; they are generated artifacts, not modifications to old results. The regenerated diagram is content-identical to the previous three-sensor layout. Existing startup/stop scripts were verified, not rewritten in this stabilization pass.

## Final assessment and remaining blockers

Ready for a reproducible, bounded local three-bay **virtual-sensor** demonstration with the stated memory/runtime limits. Not production-ready. Remaining blockers are Saaket's absent backend/database/API implementation, physical ESP32/HC-SR04 tests, direct ESP32 MQTT networking, long-duration Node/Edge memory profiling, production identity/auth/TLS/ACLs, monitoring, retention/backups and deployment verification. No physical accuracy, physical-to-web latency, universal three-second response or production exactly-once guarantee is claimed. The reference backend and live browser Serial bridge must retain those labels.

The final source manifest excludes generated evidence, installed dependencies and the vendored Zig compiler tools. The initial broader fingerprint is preserved as source_sha256.json; source_sha256.final.json fingerprints the final project source and handover documents after that audit-helper refinement. Neither snapshot is a new test run.
