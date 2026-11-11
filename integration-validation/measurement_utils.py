"""Reusable timing, ordering, timestamp, and labelled-accuracy utilities."""

from datetime import timezone
from time import perf_counter

from simulation_validator import parse_event_timestamp


def measure_local_processing(operation, *args, **kwargs):
    """Return (operation result, elapsed monotonic seconds) for local work."""
    started = perf_counter()
    result = operation(*args, **kwargs)
    return result, perf_counter() - started


def measure_http_request(request_operation, *args, **kwargs):
    """Measure one HTTP request/response round trip, not sensor-to-web latency."""
    return measure_local_processing(request_operation, *args, **kwargs)


def validate_timestamp(value):
    """Return a timezone-aware parsed timestamp or raise ValueError."""
    return parse_event_timestamp(value)


def event_delivery_order(events):
    """Return event IDs in stable timestamp order; does not infer network order."""
    return [
        event["event_id"]
        for event in sorted(
            events,
            key=lambda event: (
                event["parking_space_id"],
                parse_event_timestamp(event["timestamp"]),
                event["event_id"],
            ),
        )
    ]


def recovery_duration(disconnected_at, recovered_at):
    """Calculate elapsed seconds between two monotonic-clock readings."""
    duration = recovered_at - disconnected_at
    if duration < 0:
        raise ValueError("recovery time cannot precede disconnection time")
    return duration


def duplicate_event_decision(seen_event_ids, event_id):
    """Return whether an event is new; update the supplied set for new events."""
    if event_id in seen_event_ids:
        return False
    seen_event_ids.add(event_id)
    return True


def calculate_detection_accuracy(observations):
    """Calculate labelled classification accuracy as a percentage.

    Each item must contain ``expected`` and ``observed`` labels. Empty samples
    and malformed rows are rejected rather than being treated as 100% accurate.
    """
    rows = list(observations)
    if not rows:
        raise ValueError("at least one labelled observation is required")
    correct = 0
    for row in rows:
        if not isinstance(row, dict) or "expected" not in row or "observed" not in row:
            raise ValueError("each observation needs expected and observed labels")
        if not isinstance(row["expected"], str) or row["expected"] not in {
            "AVAILABLE", "OCCUPIED"
        }:
            raise ValueError("expected label must be AVAILABLE or OCCUPIED")
        if not isinstance(row["observed"], str) or row["observed"] not in {
            "AVAILABLE", "OCCUPIED"
        }:
            raise ValueError("observed label must be AVAILABLE or OCCUPIED")
        correct += row["expected"] == row["observed"]
    return {
        "correct": correct,
        "total": len(rows),
        "accuracy_percent": (correct / len(rows)) * 100,
        "evidence_type": "LABELLED_INPUT_REQUIRED",
    }


def measure_true_sensor_to_web_latency(
    sensor_detected_at,
    web_updated_at,
    *,
    observations_are_real=False,
    clocks_comparable=False,
):
    """Calculate a timestamp interval, assessing the target only with evidence.

    This function cannot verify evidence authenticity or clock synchronization.
    Unless the caller explicitly confirms both, it reports the interval without
    deciding whether the system met its end-to-end target.
    """
    if not isinstance(observations_are_real, bool) or not isinstance(
        clocks_comparable, bool
    ):
        raise ValueError("evidence confirmations must be boolean")
    start = parse_event_timestamp(sensor_detected_at).astimezone(timezone.utc)
    end = parse_event_timestamp(web_updated_at).astimezone(timezone.utc)
    duration = (end - start).total_seconds()
    if duration < 0:
        raise ValueError("web update timestamp precedes sensor detection")
    result = {
        "measurement_type": "TIMESTAMP_BASED_SENSOR_TO_WEB_INTERVAL",
        "latency_seconds": duration,
        "evidence_required": True,
        "observations_are_real": observations_are_real,
        "clocks_comparable": clocks_comparable,
    }
    if observations_are_real and clocks_comparable:
        result["project_target_seconds"] = 3.0
        result["meets_target"] = duration <= 3.0
    else:
        result["target_assessment"] = "NOT ASSESSED: real observations and comparable clocks required"
    return result
