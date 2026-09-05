#!/usr/bin/env python3
"""Step 9 batch driver: G2 100k dry run, G3 production batch, validation.

Usage:
  python scripts/run_step9.py --mode dryrun     [--out data/output/step9_dryrun]
  python scripts/run_step9.py --mode production [--out data/output/step9]
  python scripts/run_step9.py --mode resume --planned-runs 10 --out data/output/step9_dryrun
  python scripts/run_step9.py --mode validate   --out data/output/step9

Options:
  --config PATH          approved YAML configuration (default config/base.yaml)
  --out DIR              output directory
  --target N             patient target (default from config.batch)
  --planned-runs N       planned runs per scenario (cap; default from config.batch)
  --seed N               batch master seed (default from config.reproducibility)
  --scenarios LIST       comma-separated scenario IDs (default Standard-8+CUSTOM)
  --chunks N[,M]         patient,event chunk rows (default from config.batch)
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hfsg.batch import BatchRunner, validate_batch_outputs
from hfsg.config import ConfigurationLoader


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True,
                        choices=["dryrun", "production", "resume", "validate"])
    parser.add_argument("--config", default="config/base.yaml")
    parser.add_argument("--out", required=True)
    parser.add_argument("--target", type=int, default=None)
    parser.add_argument("--planned-runs", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--scenarios", default=None)
    args = parser.parse_args()

    out_dir = Path(args.out)
    cfg = ConfigurationLoader().load(args.config)

    scenario_ids = (
        [s.strip() for s in args.scenarios.split(",") if s.strip()]
        if args.scenarios else None
    )

    if args.mode == "validate":
        report = validate_batch_outputs(out_dir, scenario_ids=scenario_ids)
    else:
        if args.mode == "dryrun":
            target = args.target if args.target is not None else 100_000
            planned = args.planned_runs if args.planned_runs is not None else 10
        elif args.mode == "production":
            target = args.target if args.target is not None else int(cfg.batch["target_patient_records"])
            planned = args.planned_runs if args.planned_runs is not None else int(cfg.batch["planned_runs_per_scenario"])
        else:  # resume
            target = args.target if args.target is not None else 100_000
            planned = args.planned_runs if args.planned_runs is not None else 10

        started = time.time()
        runner = BatchRunner(
            cfg,
            out_dir,
            target_patients=target,
            planned_runs_per_scenario=planned,
            scenario_ids=scenario_ids,
            master_seed=args.seed,
        )
        records = runner.run()
        manifest = runner.write_artifacts(validation_status="VALIDATION")
        report = validate_batch_outputs(out_dir)
        elapsed = time.time() - started

        # The manifest is the authoritative final artifact: reflect the
        # validation outcome.
        manifest_path = out_dir / "dataset_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["validation_status"] = report["validation_status"]
        manifest_path.write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

        print(f"batch_id: {runner._batch_id}")
        print(f"schedule: {list(runner.schedule)}")
        print(f"master_seed: {runner.master_seed}")
        print(f"runs completed: {len(records)} (target runs/scenario cap: {planned})")
        print(f"cumulative patients: {runner.cumulative_patients}")
        print(f"cumulative events: {runner.cumulative_events}")
        print(f"elapsed seconds: {elapsed:.1f}")

    report["elapsed_seconds"] = report.get("elapsed_seconds")
    report_path = out_dir / "validation_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    print(f"validation_status: {report['validation_status']}")
    print(f"critical_failures: {len(report['critical_failures'])}")
    print(f"decision_required: {report['decision_required']}")
    print(f"validation_report: {report_path}")

    for failure in report["critical_failures"][:20]:
        print(f"  FAIL: {failure}")

    return 0 if report["validation_status"] == "VALIDATED" else 1


if __name__ == "__main__":
    sys.exit(main())