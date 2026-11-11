"""Run offline tests and generate machine- and human-readable reports."""

import json
import platform
import re
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

from test_catalog import SIMULATION_TEST_CATALOG
from evidence_utils import archive_existing


SCRIPT_DIR = Path(__file__).resolve().parent
JSON_REPORT_PATH = SCRIPT_DIR / "simulation_test_report.json"
SUMMARY_PATH = SCRIPT_DIR / "VALIDATION_REPORT.md"


class JsonReportResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.case_results = []
        self._started_at = {}
        self._subtest_errors = {}

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            outcome = "FAIL" if issubclass(err[0], test.failureException) else "ERROR"
            self._subtest_errors.setdefault(test, []).append((outcome, str(subtest) + "\n" + self._exc_info_to_string(err, test)))

    def stopTest(self, test):
        errors = self._subtest_errors.pop(test, [])
        if errors:
            outcome = "ERROR" if any(e[0] == "ERROR" for e in errors) else "FAIL"
            self._record(test, outcome, "\n".join(e[1] for e in errors))
        super().stopTest(test)

    def startTest(self, test):
        self._started_at[test] = datetime.now(timezone.utc)
        super().startTest(test)

    def _record(self, test, outcome, details=""):
        existing = next((case for case in self.case_results if case["test_name"] == test.id()), None)
        if existing is not None:
            existing["details"] += "\n" + details
            existing["outcome"] = "ERROR" if "ERROR" in (existing["outcome"], outcome) else outcome
            return
        started = self._started_at.pop(test, datetime.now(timezone.utc))
        match = re.search(r"\.test_(sim_\d{3})_", test.id())
        test_id = match.group(1).upper().replace("_", "-") if match else None
        if test_id is None:
            test_id = test.id()  # Stable fully qualified ID for non-SIM cases.
        catalog_entry = SIMULATION_TEST_CATALOG.get(test_id, {})
        self.case_results.append(
            {
                "test_id": test_id,
                "related_test_plan_ids": catalog_entry.get("plan", []),
                "test_name": test.id(),
                "title": catalog_entry.get("title", ""),
                "outcome": outcome,
                "started_at": started.isoformat(),
                "duration_seconds": round(
                    (datetime.now(timezone.utc) - started).total_seconds(), 6
                ),
                "details": details,
                "evidence_type": ("SOURCE_DERIVED_MODEL" if "SourceDerivedModelTests" in test.id()
                                  else "WOKWI_SERIAL_FIXTURE" if "test_wokwi_serial_adapter" in test.id()
                                  else "LOCAL_SYNTHETIC_OR_MOCK_FIXTURE"),
            }
        )

    def addSuccess(self, test):
        super().addSuccess(test)
        self._record(test, "PASS")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._record(test, "FAIL", self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self._record(test, "ERROR", self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._record(test, "SKIP", reason)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self._record(test, "EXPECTED_FAILURE", self._exc_info_to_string(err, test))

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self._record(test, "UNEXPECTED_SUCCESS")


def build_summary(result):
    outcome_counts = {
        outcome: sum(case["outcome"] == outcome for case in result.case_results)
        for outcome in (
            "PASS", "FAIL", "ERROR", "SKIP", "EXPECTED_FAILURE",
            "UNEXPECTED_SUCCESS",
        )
    }
    return {
        "tests_run": result.testsRun,
        "passed": outcome_counts["PASS"],
        "failed": outcome_counts["FAIL"],
        "errors": outcome_counts["ERROR"],
        "skipped": outcome_counts["SKIP"],
        "expected_failures": outcome_counts["EXPECTED_FAILURE"],
        "unexpected_successes": outcome_counts["UNEXPECTED_SUCCESS"],
    }


def write_reports(result):
    generated_at = datetime.now(timezone.utc).isoformat()
    summary = build_summary(result)
    test_ids = sorted(
        {case["test_id"] for case in result.case_results if case["test_id"]}
    )
    report = {
        "report_type": "SIMULATED_AND_LOCAL_FIXTURES_ONLY",
        "generated_at": generated_at,
        "command": '"' + sys.executable + '" "' + str(Path(__file__).resolve()) + '"',
        "environment": {
            "python_version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
        "test_plan_references": sorted(
            {
                plan_id
                for case in result.case_results
                for plan_id in case["related_test_plan_ids"]
            }
        ),
        "test_ids": test_ids,
        "simulation_test_ids": [value for value in test_ids if value.startswith("SIM-")],
        "real_system_validated": False,
        "scope": (
            "Synthetic event validation, in-memory network recovery simulation, "
            "measurement utility checks, and local mocked/SQLite fixture adapter "
            "tests, including the source-reviewed Wokwi Serial adapter with handcrafted "
            "text fixtures. No real ESP32, broker, backend, production database, or web "
            "application was exercised."
        ),
        "summary": summary,
        "test_cases": result.case_results,
        "real_integration_status": "NOT RUN",
    }
    archive_existing([JSON_REPORT_PATH, SUMMARY_PATH])
    JSON_REPORT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    human_summary = f"""# Validation Report

## Execution record

- **Run type:** Local simulation and fixture tests only
- **Generated (UTC):** {generated_at}
- **Command:** `{report["command"]}`
- **Python:** {platform.python_version()} ({platform.python_implementation()})
- **Platform:** {platform.platform()}
- **Automated tests:** {summary["tests_run"]} run; {summary["passed"]} passed; {summary["failed"]} failed; {summary["errors"]} errors; {summary["skipped"]} skipped.
- **Machine-readable detail:** [simulation_test_report.json](./simulation_test_report.json)
- **Real integration result register:** [test_results.csv](./test_results.csv), retained as **NOT RUN**.

## Scope and interpretation

The executed suite covers synthetic parking event validation, per-space ordering,
disconnection/reconnection behavior in an in-memory fixture, utility functions,
and adapter checks using mocks, a temporary in-memory SQLite fixture, and
handcrafted Wokwi Serial text. Wokwi adapter fixture checks follow the reviewed source contract; they do not
establish actual firmware execution or deployed-system conformance. Test IDs
run: {", ".join(test_ids) if test_ids else "none"}.

These are simulated/local checks. They do **not** validate the deployed sensor,
ESP32, Wi-Fi/MQTT delivery, backend, production database, or web application.
Local processing time and mock HTTP round-trip time are not true sensor-to-web
latency measurements. The timestamp-interval helper assesses the 3-second target
only when its caller explicitly confirms genuine observations and comparable
clocks; the helper cannot verify those claims. No real detection-accuracy value
has been measured.

## Acceptance target status

| Requirement | Target | Current evidence/status |
|---|---|---|
| Parking detection accuracy | At least 95% | **NOT RUN** against sensor observations. A labelled-data calculation helper was unit-tested only. |
| Real sensor-to-web update latency | No more than 3 seconds | **NOT RUN**. Only a timestamp-difference helper was unit-tested; no system latency was measured. |
| Correct database space ID, status, timestamp | Match approved schema and event | **NOT RUN** against production database. SQLite adapter tested against a temporary fixture schema only. |
| Web availability consistency | Display agrees with latest accepted state | **NOT RUN** against project web application. Snapshot comparison helper tested locally only. |
| Connection failure and recovery | Detect and recover per agreed design | **NOT RUN** on deployed components. An in-memory queue fixture was tested. |

## Remaining dependencies

Real validation requires the teammates' component source/builds and an agreed
interface contract; configured parking-space identifiers; sensor/ESP32 hardware;
Wi-Fi and broker access plus approved topics/payload/QoS; backend URL and API
contract; database access, schema and read-only inspection method; web URL,
response fields and update mechanism; controlled failure/recovery procedures;
labelled physical ground truth; synchronized/comparable clocks; and permission
to collect logs/screenshots. Do not add credentials to this repository.
"""
    SUMMARY_PATH.write_text(human_summary, encoding="utf-8")
    return report


def main():
    suite = unittest.defaultTestLoader.discover(
        start_dir=str(SCRIPT_DIR),
        pattern="test_*.py",
        top_level_dir=str(SCRIPT_DIR),
    )
    runner = unittest.TextTestRunner(
        stream=sys.stdout,
        verbosity=2,
        resultclass=JsonReportResult,
    )
    result = runner.run(suite)
    report = write_reports(result)
    print("Machine-readable report: " + str(JSON_REPORT_PATH))
    print("Human-readable summary: " + str(SUMMARY_PATH))
    print("Summary: " + json.dumps(report["summary"], sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
