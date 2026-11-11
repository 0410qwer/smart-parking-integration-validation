"""Validation helpers for synthetic parking event payloads."""

import json
import re
from datetime import datetime


REQUIRED_FIELDS = frozenset(
    {"event_id", "parking_space_id", "status", "timestamp"}
)
VALID_STATUSES = frozenset({"AVAILABLE", "OCCUPIED"})
DEFAULT_SPACE_ID_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}"


def parse_event_json(payload):
    """Decode a JSON event object, raising ValueError for malformed input."""
    def reject_duplicate_keys(pairs):
        decoded = {}
        for key, value in pairs:
            if key in decoded:
                raise ValueError("duplicate JSON object key: " + key)
            decoded[key] = value
        return decoded

    def reject_nonstandard_constant(value):
        raise ValueError("non-standard JSON constant: " + value)

    try:
        event = json.loads(
            payload,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_nonstandard_constant,
        )
    except (TypeError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("payload must contain valid JSON") from exc
    if not isinstance(event, dict):
        raise ValueError("event JSON must be an object")
    return event


def parse_event_timestamp(value):
    """Parse an ISO 8601 timestamp that includes an explicit timezone."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a non-empty ISO 8601 string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        timestamp = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("timestamp must be a valid ISO 8601 datetime") from exc
    if timestamp.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return timestamp


class ParkingEventValidator:
    """Validate event fields and strictly increasing per-space timestamps.

    Identical status updates are accepted when their event IDs are unique and
    timestamps increase. Every change between AVAILABLE and OCCUPIED is valid;
    no occupancy policy beyond the two-state model is assumed.
    """

    def __init__(self, space_id_pattern=DEFAULT_SPACE_ID_PATTERN):
        try:
            self._space_id_re = re.compile(space_id_pattern)
        except (re.error, TypeError) as exc:
            raise ValueError("space_id_pattern must be a valid regular expression") from exc
        self._event_ids = set()
        self._latest_timestamp_by_space = {}
        self._latest_status_by_space = {}

    @property
    def latest_status_by_space(self):
        return dict(self._latest_status_by_space)

    @property
    def latest_timestamp_by_space(self):
        return dict(self._latest_timestamp_by_space)

    def validate_event(self, event):
        """Validate fields and current history without recording the event."""
        if not isinstance(event, dict):
            raise ValueError("event must be a JSON object")

        missing_fields = REQUIRED_FIELDS - event.keys()
        if missing_fields:
            raise ValueError(
                "missing required fields: " + ", ".join(sorted(missing_fields))
            )

        for field in REQUIRED_FIELDS:
            if not isinstance(event[field], str) or not event[field].strip():
                raise ValueError(field + " must be a non-empty string")

        space_id = event["parking_space_id"]
        if not self._space_id_re.fullmatch(space_id):
            raise ValueError("parking_space_id has an invalid format")

        if event["status"] not in VALID_STATUSES:
            raise ValueError("status must be AVAILABLE or OCCUPIED")

        event_id = event["event_id"]
        if event_id in self._event_ids:
            raise ValueError("duplicate event_id: " + event_id)

        timestamp = parse_event_timestamp(event["timestamp"])
        previous_timestamp = self._latest_timestamp_by_space.get(space_id)
        if previous_timestamp is not None and timestamp <= previous_timestamp:
            raise ValueError(
                "timestamp must be later than the previous event for " + space_id
            )
        return timestamp

    def accept(self, event):
        """Validate and record one event, or raise ValueError without mutation."""
        timestamp = self.validate_event(event)
        event_id = event["event_id"]
        space_id = event["parking_space_id"]

        self._event_ids.add(event_id)
        self._latest_timestamp_by_space[space_id] = timestamp
        self._latest_status_by_space[space_id] = event["status"]


class SimulatedEventChannel:
    """Small deterministic queue model for disconnection and recovery tests.

    While disconnected, events are buffered. On reconnection, buffered events
    are delivered in per-space timestamp order, then validated by the consumer.
    This is a test fixture behavior, not a claim about the deployed device.
    """

    def __init__(self, validator=None):
        self.validator = validator if validator is not None else ParkingEventValidator()
        self.connected = True
        self._buffer = []
        self.delivered = []

    @property
    def buffered_count(self):
        return len(self._buffer)

    def disconnect(self):
        self.connected = False

    def reconnect(self):
        self.connected = True
        queued = sorted(
            self._buffer,
            key=lambda event: (
                event["parking_space_id"],
                parse_event_timestamp(event["timestamp"]),
                event["event_id"],
            ),
        )
        newly_delivered = []
        for event in queued:
            self._deliver(event)
            self._buffer.remove(event)
            newly_delivered.append(dict(event))
        return newly_delivered

    def send(self, event):
        self.validator.validate_event(event)
        if self.connected:
            self._deliver(event)
        else:
            event_copy = dict(event)
            event_id = event_copy["event_id"]
            if any(queued["event_id"] == event_id for queued in self._buffer):
                raise ValueError("duplicate buffered event_id: " + event_id)
            self._buffer.append(event_copy)

    def _deliver(self, event):
        self.validator.accept(event)
        self.delivered.append(dict(event))
