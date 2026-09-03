"""Manual Smoke Run for Step 7 (Aggregate <-> Patient Reconciliation).

Runs the full coordinated 720-hour S1 simulation using the Model v1.0.1
flow pipeline:

    requested_raw_flow -> constrained_raw_flow -> realized_integer_flow

where ``realized_integer_flow`` is authoritative for BOTH patient-event
generation and operational integer aggregate stock updates. The reconciler
validates (never repairs) aggregate/patient consistency every hour.

Usage:
    python scripts/smoke_reconciliation.py [config_path] [scenario_id] [horizon]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np  # noqa: E402

from hfsg import (  # noqa: E402
    ConfigurationLoader,
    PatientValidator,
    SimulationDriver,
    build_context,
)

DEFAULT_CONFIG = "config/base.yaml"


def _duration_hours(run):
    return run.horizon_steps


def _event_quota_mismatches(run):
    from hfsg.events import EVENT_TRANSFER, EVENT_DISCHARGE, EVENT_DEATH  # noqa: E402
    from hfsg.reconciliation import Reconciler  # noqa: E402

    mismatches = 0
    for outcome in run.outcomes:
        ev = outcome.step_events
        transfer = sum(1 for e in ev if e.event_type == EVENT_TRANSFER)
        discharge = sum(1 for e in ev if e.event_type == EVENT_DISCHARGE)
        death = sum(1 for e in ev if e.event_type == EVENT_DEATH)
        rt = sum(
            outcome.realized_flow.get(f, 0)
            for f in ("T_EC", "T_EG", "T_EI", "T_CG", "T_CI", "T_GI")
        )
        rd = sum(
            outcome.realized_flow.get(f, 0)
            for f in ("T_EH", "D_C", "D_G", "D_I")
        )
        rdm = sum(outcome.realized_flow.get(f, 0) for f in ("M_C", "M_G", "M_I"))
        mismatches += int(transfer != rt) + int(discharge != rd) + int(death != rdm)
    return mismatches


def _max_mbe(run):
    n0 = len(run.initial_stocks)
    worst = 0.0
    for outcome in run.outcomes:
        after = outcome.after
        total = (
            after.ed + after.specialty + after.general + after.icu
            + after.discharged + after.deceased
        )
        expected = n0 + after.cumulative_arrivals
        worst = max(worst, abs(total - expected))
    return worst


def _reproducible(config, seed):
    c1 = build_context(config)
    d1 = SimulationDriver(config, c1, rng=np.random.default_rng(seed))
    r1 = d1.run()
    c2 = build_context(config)
    d2 = SimulationDriver(config, c2, rng=np.random.default_rng(seed))
    r2 = d2.run()
    same_events = len(r1.events) == len(r2.events) and all(
        a.event_id == b.event_id for a, b in zip(r1.events, r2.events)
    )
    same_patients = len(r1.patients) == len(r2.patients) and all(
        a.patient_id == b.patient_id for a, b in zip(r1.patients, r2.patients)
    )
    return same_events and same_patients


def main(argv):
    config_path = argv[0] if len(argv) > 0 else DEFAULT_CONFIG
    scenario_id = argv[1] if len(argv) > 1 else "S1"
    horizon = int(argv[2]) if len(argv) > 2 else 720
    seed = 2026

    config = ConfigurationLoader().load(config_path)
    print(f"config   : {config_path}")
    print(f"scenario : {scenario_id}")
    print(f"horizon  : {horizon} hours (master_seed child derived)")

    driver = SimulationDriver(
        config, build_context(config, scenario_id=scenario_id), rng=np.random.default_rng(seed)
    )
    run = driver.run()

    hours = _duration_hours(run)
    issues = driver.reconciler.result().issues
    critical = [i for i in issues if i.severity == "critical"]
    event_mismatch = _event_quota_mismatches(run)
    max_mbe = _max_mbe(run)
    pv = PatientValidator().validate(run.patients, run.events, hours - 1)
    reproducible = _reproducible(config, seed)

    final = run.final
    n0 = len(run.initial_stocks)

    print("\n----- S1 720h Reconciliation Report -----")
    print(f"completed full horizon     : {run.completed_full_horizon} ({hours}/{horizon})")
    print(f"mass balance max abs MBE   : {max_mbe:.6f} (need < 1e-6)")
    print(f"reconciliation critical    : {len(critical)}")
    print(f"reconciliation total issues: {len(issues)}")
    print(f"event/quota mismatches     : {event_mismatch}")
    print(f"patient invariant critical : {len(pv.critical_issues)}")
    print(f"seed reproducibility       : {reproducible}")
    print(f"patients generated         : {len(run.patients)}")
    print(f"events generated           : {len(run.events)}")
    print(f"population identity        : "
          f"{final.active_total + final.discharged + final.deceased} == "
          f"{n0 + final.cumulative_arrivals}")

    pass_all = (
        run.completed_full_horizon
        and max_mbe < 1e-6
        and not critical
        and event_mismatch == 0
        and not pv.critical_issues
        and reproducible
    )
    print(f"\nRESULT: {'PASS' if pass_all else 'FAIL'}")
    return 0 if pass_all else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))