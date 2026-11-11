# Production handover requirements

This directory is an isolated integration reference, not Saaket's production backend. The workspace inspected on 11 November 2026 contains no usable teammate backend/database implementation. Original `smart-parking-web`, `wokwi-source`, captures and previous database evidence are preserved.

## Verified local boundary

Three HC-SR04 instances on ONE simulated ESP32 produce measured virtual trigger/echo readings. The browser bridge observes new Serial messages, durably queues them, publishes MQTT over local TCP, and waits for an application acknowledgement after the reference backend commits SQLite. The Dashboard reads that backend's read-only HTTP API. Neither saved-capture input nor JavaScript occupancy cycles feed Multi mode.

Mapping: `1001 -> A01`, `1002 -> A02`, `1003 -> A03`. Each source has independent state, rolling counter, heartbeat and health. Firmware JSON contains exactly `spot_id` (integer), `occupied` (boolean), `status` (0 free, 1 occupied), `batt_mv` (integer; 3600 is a placeholder), `ctr` (0..255), `heartbeat` (boolean). Invalid measurements do not invent an occupancy transition. Serial diagnostics provide measured distance/echo and trust separately from that compatible six-field message.

No source timestamp is supplied. SQLite `source_timestamp` stays NULL; `received_at` is host UTC at backend receipt. Bridge observation time and monotonic browser control timings are distinct metadata. Host times do not prove physical latency or synchronized sensor clocks.

MQTT topic: `smart-parking/integration-test/multi/<session>/<spot_id>/events/<bridge_uuid>/<serial_index>`. QoS 1, retain false; each source's order is preserved. The suffix identifies a delivery across transport retries; the 8-bit counter is never a globally unique ID. Health is `<prefix>/<spot_id>/health`; commit acknowledgements use `<prefix>/ack`. The durable outbox marks a delivery complete only after accepted/duplicate commit acknowledgement. This improves local process/broker recovery; it is not a production exactly-once guarantee. A lost browser Serial segment cannot be recovered from the ESP32 by this protocol.

Read-only APIs: `/api/availability`, `/api/health`, `/api/events?spot_id=1002&after=0&limit=50`, `/api/receipts`. History supports ID pagination; limit 1..100. Health is per source, expires after 8 seconds, and broker failure makes current state Unknown while retaining last-known state separately. Restarted backend data is persisted but not declared freshly connected before new observations. No state is fabricated for unsourced bays.

SQLite reuses the existing reference schema (`streams`, `events`, `bay_current`, receipts/checkpoints) and adds transactional `delivery_keys`; the bridge owns a separate durable outbox with stable delivery identity. Existing database evidence is never migrated destructively. A normal launcher restart uses a fresh stream namespace because simulated firmware counters restart. Pending outbox recovery across a bridge restart requires the SAME outbox file and namespace; automatic resumption of arbitrary older browser sessions is not provided.

## Required from Saaket before claiming production integration

Supply backend repository/entry point and dependency lock files; configuration template without secrets; broker topic/QoS/retain conventions and ACLs; exact inbound schema including Task 2 field/type conversion and device identity; timestamp/boot-session/counter rules; API/OpenAPI definition and authentication/authorization model; database migrations/schema and connection instructions; health/retention/recovery policies; integration tests and a non-production configuration. Map the six-field contract explicitly instead of silently renaming fields or treating counters as UUIDs. Validate against that actual implementation before replacing the isolated adapter.

## Networking and operational gaps

Direct simulated ESP32-to-local broker traffic is still unverified/blocked in the tested public-gateway environment. Wokwi documents a private IoT gateway for local network access and `host.wokwi.internal`; this requires the appropriate available setup/subscription. VS Code documents bundled private gateway support and optional RFC2217 serial forwarding. Neither alternative has been configured or verified here. No tunnel, public listener or external broker has been deployed.

Sources: [ESP32 Wi-Fi / gateways](https://docs.wokwi.com/guides/esp32-wifi), [VS Code project configuration](https://docs.wokwi.com/vscode/project-config), [virtual switch pins and controls](https://docs.wokwi.com/parts/wokwi-slide-switch).

All services bind loopback. The Dashboard has self-only content policy, no-store API responses and no-sniff headers, but production authentication, roles, device credentials, TLS, broker ACLs, rate limits, retention, backups and monitoring remain missing. The reference backend is not deployed or production-security certified. Physical ESP32/HC-SR04 accuracy, electrical level shifting, placement, cross-talk between ultrasonic sensors and physical-to-web latency require real hardware tests. Sequential virtual measurements do not establish real multi-sensor interference performance.

The browser adapter depends on Wokwi's UI and online compiler and fails closed when unreadable. Routine long-running demos disable Playwright tracing; bounded tests explicitly enable it. Disk exhaustion, storage errors and arbitrary browser crashes are operational limitations, not hidden recovery guarantees. Storage errors disconnect the subscriber and require diagnosis/restart.
