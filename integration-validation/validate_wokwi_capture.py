"""CLI for offline captures; no network or hardware access."""

import argparse
import json
from pathlib import Path

from wokwi_serial_adapter import render_summary, validate_capture
from evidence_utils import archive_existing


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--sample", action="store_true", help="explicitly label synthetic input")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--counter-modulus", type=int, default=256, choices=[256], help="source-defined uint8 modulus (256 only)")
    args = parser.parse_args(argv)
    try:
        text = args.capture.read_text(encoding="utf-8-sig")
        kind = "SAMPLE_FIXTURE" if args.sample or "SAMPLE_FIXTURE" in text else "UNVERIFIED_CAPTURE"
        report = validate_capture(text, evidence_kind=kind, counter_modulus=args.counter_modulus)
        report["input_path"] = str(args.capture.resolve())
        # Prevent accidental destruction of an input named like an output report.
        outputs = [args.output_dir / name for name in ("wokwi_validation_report.json", "WOKWI_VALIDATION_REPORT.md")]
        if args.capture.resolve() in [p.resolve() for p in outputs]:
            raise ValueError("input capture must not be an output report path")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        archive_existing(outputs)
        outputs[0].write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        outputs[1].write_text(render_summary(report), encoding="utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        parser.exit(2, f"Input/output error: {exc}\n")
    print(render_summary(report))
    # 0: no assessed check failures; 1: check failure; 2: usage/I/O error.
    return 1 if report["overall_result"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
