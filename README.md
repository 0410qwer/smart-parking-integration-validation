# Smart Parking Integration & Validation

UTS 31261 local integration reference: three independently measured **virtual** Wokwi HC-SR04 sensors feed a real local MQTT broker, SQLite reference backend and Web Dashboard.

```text
Wokwi virtual sensors -> live browser Serial bridge -> durable outbox
  -> loopback TCP MQTT QoS 1 -> reference backend -> SQLite -> API -> Dashboard/Admin
```

This is an integration/validation harness. It is not Saaket's production backend, physical sensor validation or direct ESP32-to-MQTT integration. Saved 22-event replay and the original frontend simulation remain separate fallback modes.

## Fresh clone and installation — Windows PowerShell

Install Git, Node.js (tested with 24.22.1), Python (tested with 3.14.7) and Microsoft Edge. The live virtual source requires internet access to Wokwi's website/compiler. GitHub access is required for this private repository and the separately obtained frontend.

```powershell
git clone https://github.com/0410qwer/smart-parking-integration-validation.git
Set-Location smart-parking-integration-validation
$env:PARKING_PYTHON = (py -3 -c 'import sys; print(sys.executable)').Trim()
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Setup-LocalDemo.ps1 -PythonPath $env:PARKING_PYTHON -IncludeTestCompiler
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-LocalDemo.ps1 -Mode Multi -PythonPath $env:PARKING_PYTHON
```

If `py` is unavailable, assign `$env:PARKING_PYTHON` your installed interpreter's absolute path. Keep this environment variable set in the launching terminal so Node bridge/test children use the same interpreter. Windows Store aliases are unsuitable. Each new terminal needs the assignment again. Setup does not install Python/Node/Edge or persist credentials or machine paths.

Setup obtains the original frontend from **https://github.com/hxnwls/smart-parking-web**, pinned to `9546209475df899161187155fc3d6deab822eece`. Its local checkout is ignored by this repository; it is not uploaded as a nested Git repository. Existing checkouts are inspected and never reset/discarded. The teammate remote is never pushed or modified.

Dependencies are installed locally using existing lockfiles: Aedes 1.2.0, Playwright (lockfile version), Paho MQTT 2.1.0. `-IncludeTestCompiler` also installs Zig 0.15.1 to the path expected by the existing native sensor tests; omit that option if only running the demonstration. Tools, packages and caches are ignored.

## Demonstration and shutdown

Open **http://127.0.0.1:8780/backend/**. The launcher owns the local broker (127.0.0.1:18890), backend/dashboard and live bridge. Allow Wokwi compilation to finish; bays remain Unknown until valid observations arrive. In its interactive Edge window select a sensor and set 10 cm for Occupied or 35 cm for Free. Mapping: 1001/A01 (TRIG5/ECHO18), 1002/A02 (TRIG19/ECHO21), 1003/A03 (TRIG22/ECHO23). Debounce remains 1500/2500 ms.

Stop with Ctrl+C in the launcher terminal or use the exact directory printed by startup:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Stop-LocalDemo.ps1 -SessionDirectory '<printed session directory>'
```

Restart with the same Start command. It creates a new session namespace/evidence manifest; prior database history is retained. Do not reuse an existing session manifest directory. If ports are busy, use `-BrokerPort 18891 -HttpPort 8781`; unrelated processes are not killed.

Other explicit modes: `Live` (single-bay live), `Reference -SeedCapture` (persisted capture replay over MQTT), `Memory -SeedCapture`, `Replay`, `Simulation`. Stop the current instance or select different ports. Multi never silently substitutes a capture file for live virtual Serial observations.

## Verification

The preserved final regression was **255 passed, 0 failed, 0 errors, 0 skipped**, including real Microsoft Edge checks. See [sanitized regression results](docs/regression-summary.json), [performance/stability summary](docs/verification-summary.json) and [controlled trials](docs/controlled-trials.json). These are historical measured results, not an assertion that this fresh clone has rerun them.

To generate new ignored evidence after installing test dependencies:

```powershell
& $env:PARKING_PYTHON integration-validation/demo/run_system_checks.py
& $env:PARKING_PYTHON integration-validation/demo/multi/run_performance.py --rounds 10 --soak-seconds 180
& $env:PARKING_PYTHON integration-validation/demo/multi/run_volume.py
```

At 200 ms polling, 30 trials each: Occupied median 1861 ms / p95 1972 ms; Free median 2902 ms / p95 3039 ms. Six Free trials exceeded 3 seconds; no general three-second compliance claim. The extended bounded run matched 199 observed Serial events to 199 committed keys including 77 heartbeats. The separate 900-message stress is harness-generated traffic, not sensor measurements.

## Ownership, data and publication scope

Project integration source, adapters, broker/bridge, reference schema, isolated firmware variants, tests and launchers are included. `wokwi-source/` is the unchanged supplied legacy firmware input retained for baseline hash tests, not the live three-bay implementation. The latter is `integration-validation/demo/multi/firmware/`.

Only small actual capture fixtures needed by existing tests are retained under their original relative paths. Capture metadata and published technical documents are sanitized. Four machine-specific Python fallback strings are made portable (`python`) in this export; the documented PARKING_PYTHON setting remains the preferred execution path. Original stabilized workspace source/evidence was not edited. [Publication manifest](docs/publication-manifest.json) records those adaptations and fixture hashes.

Runtime SQLite/WAL/SHM, node_modules, vendor/toolchains, virtual environments, raw large evidence, traces/screenshots, generated logs/reports, credentials/.env files and academic reports/presentations are excluded. See [evidence policy](docs/EVIDENCE.md). The source workspace retains those artifacts. Historical audit post-processing utilities need their omitted original archives and are not demo/test prerequisites.

## Remaining limitations

Ready for a bounded local three-bay virtual-sensor demonstration. Browser-driver Node memory growth remains unresolved; hours/days endurance and leak-free operation are not established. Admin history shows its first 50-event page; use API pagination for later events. There is no physical accuracy/latency validation, verified direct ESP32 MQTT, teammate production backend, or production authentication/TLS/operations acceptance. Services bind loopback; that does not make this production-secure.

Further technical detail: [INTEGRATION_DEMO_README.md](INTEGRATION_DEMO_README.md), [FINAL_TECHNICAL_AUDIT.md](FINAL_TECHNICAL_AUDIT.md), [production interface](integration-validation/demo/multi/PRODUCTION_INTERFACE.md).
