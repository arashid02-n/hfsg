"""Step 8 run script: Standard-8 + CUSTOM integration and output pipeline.

Usage:
    python scripts/run_step8.py [output_dir] [--scenario S1,S2,...] \
        [--custom '{"arrivals_multiplier":1.25,...}'] [--seed SEED]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from hfsg.config import ConfigurationLoader  # noqa: E402
from hfsg.pipeline import CUSTOM_SCENARIO_ID, Pipeline  # noqa: E402
from hfsg.validation_report import validate_outputs, write_json  # noqa: E402


def main(argv) -> int:
    parser = argparse.ArgumentParser(description="HFSG Step 8 run")
    parser.add_argument("config", nargs="?", default="config/base.yaml")
    parser.add_argument("--out", default="data/output/step8")
    parser.add_argument(
        "--scenario", default=None, help="comma-separated scenario ids (default all)"
    )
    parser.add_argument("--custom", default=None, help="JSON CUSTOM parameter profile")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--run-index", type=int, default=0)
    args = parser.parse_args(argv)

    config = ConfigurationLoader().load(args.config)
    scenarios = None
    if args.scenario:
        scenarios = [s.strip() for s in args.scenario.split(",") if s.strip()]

    custom_profile = None
    if args.custom:
        custom_profile = json.loads(args.custom)
        if CUSTOM_SCENARIO_ID not in (scenarios or []):
            scenarios = list(scenarios or []) + [CUSTOM_SCENARIO_ID]

    pipeline = Pipeline(
        config,
        Path(args.out),
        scenario_ids=scenarios,
        custom_profile=custom_profile,
        run_index=args.run_index,
        seed=args.seed,
    )
    pipeline.run()
    summary = pipeline.write_outputs()

    # Determine validation status from in-memory outcomes.
    outcomes = pipeline.outcomes
    all_ok = all(
        o.completed_full_horizon
        and o.reconciliation_issues == 0
        and o.event_quota_mismatches == 0
        for o in outcomes
    )
    validation_status = "PASS" if all_ok else "FAIL"

    manifest = pipeline.finalize_manifest_and_report(validation_status)

    report = validate_outputs(
        Path(args.out), manifest, pipeline, initial_stocks=Pipeline.INITIAL_STOCKS
    )
    write_json(Path(args.out) / "validation_report.json", report)
    validation_status = "PASS" if not report["critical_failures"] and all_ok else "FAIL"
    manifest = pipeline.finalize_manifest_and_report(validation_status)

    for o in outcomes:
        status = "PASS" if (
            o.completed_full_horizon
            and o.reconciliation_issues == 0
            and o.event_quota_mismatches == 0
        ) else "FAIL"
        print(f"{o.scenario_id:>6} {status}  patients={o.patient_count} "
              f"events={o.event_count} recon_issues={o.reconciliation_issues} "
              f"mbe={o.max_abs_mbe:.6f}")

    print(f"\nvalidation_status = {validation_status}")
    print(f"critical_failures = {report['critical_failures']}")
    if report.get("decision_required"):
        print(f"DECISION_REQUIRED  = {[d.get('id') for d in report['decision_required']]}")
    if report.get("spec_conflict"):
        print(f"SPEC_CONFLICT      = {report['spec_conflict']}")
    return 0 if validation_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
