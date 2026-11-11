"""Configurable standard-library adapters for later system integration.

No endpoint, MQTT topic, credential, or production schema is assumed. Supply
values from the project team before using any adapter against a real component.
"""

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from simulation_validator import ParkingEventValidator, parse_event_json


class HttpJsonClient:
    """Small configurable JSON-over-HTTP client using Python's urllib."""

    def __init__(self, base_url, timeout_seconds=5.0):
        if not base_url or "REPLACE_WITH" in base_url:
            raise ValueError("provide a project-approved HTTP base URL")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def request_json(self, method, path, body=None, headers=None):
        if not path or "REPLACE_WITH" in path:
            raise ValueError("provide a project-approved HTTP path")
        url = self.base_url + "/" + path.lstrip("/")
        payload = None if body is None else json.dumps(body).encode("utf-8")
        request_headers = {"Accept": "application/json"}
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
        request_headers.update(headers or {})
        request = Request(
            url,
            data=payload,
            headers=request_headers,
            method=method.upper(),
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                status_code = response.status
                raw_body = response.read()
        except HTTPError as exc:
            raise RuntimeError("HTTP request returned status " + str(exc.code)) from exc
        except URLError as exc:
            raise RuntimeError("HTTP request failed: " + str(exc.reason)) from exc

        if not raw_body:
            return status_code, None
        try:
            return status_code, json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("HTTP response body was not valid JSON") from exc

    def get_json(self, path, headers=None):
        return self.request_json("GET", path, headers=headers)

    def post_json(self, path, body, headers=None):
        return self.request_json("POST", path, body=body, headers=headers)


def validate_http_event_response(status_code, response_body, event, expected_codes=(200, 201, 202)):
    """Check configurable HTTP acceptance and optional event ID echo."""
    if status_code not in expected_codes:
        raise ValueError("HTTP status code was not accepted")
    if response_body is not None and not isinstance(response_body, dict):
        raise ValueError("HTTP response must be a JSON object or empty")
    if isinstance(response_body, dict):
        response_event_id = response_body.get("event_id")
        if response_event_id is not None and response_event_id != event.get("event_id"):
            raise ValueError("HTTP response event_id does not match request")


def validate_web_status(snapshot, parking_space_id, expected_status,
                        space_field="parking_space_id", status_field="status"):
    """Compare a configured web/API snapshot with the expected parking state."""
    if not isinstance(snapshot, dict):
        raise ValueError("web snapshot must be a JSON object")
    if snapshot.get(space_field) != parking_space_id:
        raise ValueError("web snapshot parking space does not match")
    if snapshot.get(status_field) != expected_status:
        raise ValueError("web snapshot status does not match")


class SQLiteRecordAdapter:
    """Validate a record using a configured SQLite table and column mapping.

    The adapter does not define the project's production database schema.
    Table and column names must be supplied by the team and are identifier-checked;
    values, including event IDs, are passed as SQL parameters.
    """

    _IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

    def __init__(self, connection, table, columns):
        self.connection = connection
        self.table = self._validate_identifier(table)
        required = {"event_id", "parking_space_id", "status", "timestamp"}
        if set(columns) != required:
            raise ValueError("columns must map event_id, parking_space_id, status, timestamp")
        self.columns = {
            key: self._validate_identifier(value) for key, value in columns.items()
        }

    @classmethod
    def _validate_identifier(cls, value):
        if not isinstance(value, str) or not cls._IDENTIFIER.fullmatch(value):
            raise ValueError("SQL table and column names must be simple identifiers")
        return value

    def find_event(self, event_id):
        selected = ", ".join(
            self.columns[key]
            for key in ("event_id", "parking_space_id", "status", "timestamp")
        )
        query = (
            "SELECT " + selected + " FROM " + self.table
            + " WHERE " + self.columns["event_id"] + " = ?"
        )
        rows = self.connection.execute(query, (event_id,)).fetchmany(2)
        if not rows:
            return None
        if len(rows) > 1:
            raise ValueError("multiple database records found for event_id")
        row = rows[0]
        return dict(zip(
            ("event_id", "parking_space_id", "status", "timestamp"), row
        ))

    def validate_event_record(self, event):
        record = self.find_event(event["event_id"])
        if record is None:
            raise ValueError("database record was not found")
        validate_event_record(record, event)
        return record


def validate_event_record(record, event):
    """Check event identity, space, status, and timestamp fields."""
    fields = ("event_id", "parking_space_id", "status", "timestamp")
    if not isinstance(record, dict) or not isinstance(event, dict):
        raise ValueError("database record and event must be mappings")
    if any(field not in record or field not in event for field in fields):
        raise ValueError("database record and event require all identity/state/time fields")
    mismatches = [field for field in fields if record.get(field) != event.get(field)]
    if mismatches:
        raise ValueError("database record differs in: " + ", ".join(mismatches))


def validate_mqtt_payload(payload, validator=None):
    """Decode and validate an MQTT event payload without connecting to a broker."""
    event = parse_event_json(payload)
    (validator or ParkingEventValidator()).accept(event)
    return event


class OptionalMqttPublisher:
    """Optional paho-mqtt publishing adapter, disabled unless explicitly enabled."""

    def __init__(self, enabled=False, host=None, port=None, topic=None):
        self.enabled = enabled
        self.host = host
        self.port = port
        self.topic = topic
        self._client = None

    def connect(self):
        if not self.enabled:
            raise RuntimeError("MQTT adapter is disabled by default")
        if not self.host or not self.port or not self.topic:
            raise ValueError("provide project-approved MQTT host, port, and topic")
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:
            raise RuntimeError(
                "optional paho-mqtt dependency is required when MQTT is enabled"
            ) from exc
        self._client = mqtt.Client()
        self._client.connect(self.host, self.port)
        self._client.loop_start()

    def publish(self, event):
        if not self.enabled or self._client is None:
            raise RuntimeError("connect the explicitly enabled MQTT adapter first")
        payload = json.dumps(event)
        result = self._client.publish(self.topic, payload)
        result.wait_for_publish()
        if result.rc != 0:
            raise RuntimeError("MQTT publish failed with result code " + str(result.rc))

    def close(self):
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None
