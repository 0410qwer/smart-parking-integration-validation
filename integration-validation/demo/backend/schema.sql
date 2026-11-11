PRAGMA user_version = 1;
CREATE TABLE streams (
    stream_id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    accepted INTEGER NOT NULL DEFAULT 0,
    last_payload_json TEXT,
    last_event_id INTEGER
);
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_uuid TEXT NOT NULL UNIQUE,
    stream_id TEXT NOT NULL REFERENCES streams(stream_id),
    ordinal INTEGER NOT NULL,
    spot_id INTEGER NOT NULL,
    occupied INTEGER NOT NULL CHECK (occupied IN (0,1)),
    status INTEGER NOT NULL CHECK (status BETWEEN 0 AND 7),
    batt_mv INTEGER NOT NULL CHECK (batt_mv BETWEEN 0 AND 65535),
    ctr INTEGER NOT NULL CHECK (ctr BETWEEN 0 AND 255),
    heartbeat INTEGER NOT NULL CHECK (heartbeat IN (0,1)),
    payload_json TEXT NOT NULL,
    raw_payload BLOB NOT NULL,
    topic TEXT NOT NULL,
    qos INTEGER NOT NULL,
    retained INTEGER NOT NULL,
    mqtt_dup INTEGER NOT NULL,
    mqtt_mid INTEGER,
    source_timestamp TEXT CHECK (source_timestamp IS NULL),
    received_at TEXT NOT NULL,
    backend_run TEXT NOT NULL,
    connection_epoch TEXT NOT NULL,
    UNIQUE (stream_id, ordinal)
);
CREATE TABLE bay_current (
    stream_id TEXT NOT NULL REFERENCES streams(stream_id),
    spot_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL REFERENCES events(id),
    PRIMARY KEY (stream_id, spot_id)
);
CREATE TABLE receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_uuid TEXT NOT NULL UNIQUE,
    stream_id TEXT NOT NULL REFERENCES streams(stream_id),
    outcome TEXT NOT NULL CHECK (outcome IN ('accepted','duplicate','rejected')),
    event_id INTEGER REFERENCES events(id),
    reason TEXT,
    raw_payload BLOB NOT NULL,
    raw_size INTEGER NOT NULL,
    topic TEXT NOT NULL,
    qos INTEGER NOT NULL,
    retained INTEGER NOT NULL,
    mqtt_dup INTEGER NOT NULL,
    mqtt_mid INTEGER,
    received_at TEXT NOT NULL,
    backend_run TEXT NOT NULL,
    connection_epoch TEXT NOT NULL
);
CREATE TABLE connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stream_id TEXT NOT NULL REFERENCES streams(stream_id),
    backend_run TEXT NOT NULL,
    connection_epoch TEXT NOT NULL,
    connected INTEGER NOT NULL,
    observed_at TEXT NOT NULL
);
CREATE INDEX event_history ON events(stream_id, id);
CREATE INDEX receipt_outcomes ON receipts(stream_id, outcome);
