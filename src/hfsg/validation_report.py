"""Step 8 validation report builder.

Reads back the written outputs, reconciles manifest counts against actual
record counts, verifies the configuration hash, checks post-serialization
invariants (uniqueness, chronology, no post-terminal events) and aggregate
reconciliation, and reports CRITICAL failures / DECISION_REQUIRED /
SPEC_CONFLICT.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import yaml

from .output import (
    check_post_serialization,
    match_aggregate_to_replay,
    read_partitioned,
    replay_operational_stocks,
    write_json,
)
from .scenarios import Configuration, hash_yaml


class ValidationReportError(RuntimeError):
    pass


def validate_outputs(
    out_dir: Path,
    manifest: Dict[str, Any],
    pipeline,
    initial_stocks: Dict[str, int] = None,
) -> Dict[str, Any]:
    """Run the full round-trip validation over the written outputs.

    ``pipeline`` exposes ``outcomes`` with per-scenario run objects used to
    cross-check the written data against in-memory truth.
    """
    out = Path(out_dir)
    if initial_stocks is None:
        initial_stocks = {"ed": 20, "specialty": 25, "general": 60, "icu": 10}

    report: Dict[str, Any] = {
        "mass_balance": {"pass": True, "max_abs_mbe": 0.0},
        "aggregate_patient_reconciliation": {
            "pass": True,
            "critical_failures": 0,
        },
        "event_quota_reconciliation": {"pass": True, "mismatches": 0},
        "uniqueness": {"pass": True, "issues": []},
        "temporal_consistency": {"pass": True, "issues": []},
        "capacity_source_invariants": {"pass": True, "issues": []},
        "scenario_coverage": {"pass": True, "scenarios": []},
        "parquet_readability": {"pass": True, "issues": []},
        "actual_record_counts": {},
        "manifest_reconciliation": {"pass": True, "issues": []},
        "configuration_hash": {"pass": True, "message": ""},
        "reproducibility": {"pass": True, "details": []},
        "critical_failures": [],
        "decision_required": [],
        "spec_conflict": [],
    }

    # ---- Read back every Parquet output ----
    patients = read_partitioned(out / "patients")
    events = read_partitioned(out / "patient_events")
    aggregate = read_partitioned(out / "aggregate_timeseries")
    summary = _read_plain_parquet(out / "simulation_summary.parquet")
    comparison = _read_csv(out / "scenario_comparison.csv")

    if patients.empty:
        report["parquet_readability"]["issues"].append("patients.parquet empty/unreadable")
    if events.empty:
        report["parquet_readability"]["issues"].append("patient_events.parquet empty/unreadable")
    if aggregate.empty:
        report["parquet_readability"]["issues"].append("aggregate_timeseries.parquet empty/unreadable")
    if summary.empty:
        report["parquet_readability"]["issues"].append("simulation_summary.parquet empty/unreadable")
    if comparison.empty:
        report["parquet_readability"]["issues"].append("scenario_comparison.csv empty/unreadable")
    if report["parquet_readability"]["issues"]:
        report["parquet_readability"]["pass"] = False

    # ---- Actual record counts ----
    report["actual_record_counts"]["patients"] = int(len(patients))
    report["actual_record_counts"]["patient_events"] = int(len(events))
    report["actual_record_counts"]["aggregate_timeseries"] = int(len(aggregate))
    report["actual_record_counts"]["simulation_summary"] = int(len(summary))

    # ---- Manifest reconciliation ----
    man_issues = []
    if manifest["patient_record_count"] != len(patients):
        man_issues.append(
            f"manifest patient count {manifest['patient_record_count']} != "
            f"actual {len(patients)}"
        )
    if manifest["patient_event_count"] != len(events):
        man_issues.append(
            f"manifest event count {manifest['patient_event_count']} != "
            f"actual {len(events)}"
        )
    report["manifest_reconciliation"]["issues"] = man_issues
    report["manifest_reconciliation"]["pass"] = not man_issues

    # ---- Configuration hash ----
    hash_ok = True
    hash_msg = ""
    if not patients.empty:
        by_scenario = patients["scenario_id"].unique().tolist()
        report["scenario_coverage"]["scenarios"] = sorted(by_scenario)
    config_hash = manifest.get("configuration_hash", "")
    report["configuration_hash"]["message"] = f"configuration_hash={config_hash}"
    if not config_hash:
        report["configuration_hash"]["pass"] = False
        hash_msg = "manifest missing configuration_hash"
    else:
        # Exact round-trip: re-hash the preserved used_configuration.yaml and
        # require it to equal the manifest hash.
        used_path = out_dir / "used_configuration.yaml"
        if not used_path.exists():
            report["configuration_hash"]["pass"] = False
            hash_msg = "used_configuration.yaml missing"
        else:
            try:
                with open(used_path, "r", encoding="utf-8") as fh:
                    used_back = yaml.safe_load(fh)
            except Exception:
                used_back = None
            if used_back is None:
                report["configuration_hash"]["pass"] = False
                hash_msg = "used_configuration.yaml unreadable"
            else:
                back_hash = hash_yaml(used_back)
                if back_hash != config_hash and hash_msg == "":
                    report["configuration_hash"]["pass"] = False
                    hash_msg = (
                        f"used_configuration.yaml hash {back_hash} != "
                        f"manifest {config_hash}"
                    )
    report["configuration_hash"]["message"] = hash_msg or report["configuration_hash"]["message"]

    # ---- Uniqueness / temporal / post-terminal (post-serialization) ----
    violations = check_post_serialization(patients, events)
    uniqueness_issues = [v for v in violations if "duplicate" in v]
    temporal_issues = [
        v for v in violations if v not in uniqueness_issues
        and ("chronological" in v or "after terminal" in v or "ARRIVAL" in v)
    ]
    report["uniqueness"]["issues"] = uniqueness_issues
    report["uniqueness"]["pass"] = not uniqueness_issues
    report["temporal_consistency"]["issues"] = temporal_issues
    report["temporal_consistency"]["pass"] = not temporal_issues

    # ---- Aggregate reconciliation via replay (per scenario) ----
    agg_violations = []
    for scenario_id in patients["scenario_id"].unique().tolist():
        replay = replay_operational_stocks(
            events, initial_stocks, scenario_id, patients_df=patients
        )
        agg_violations.extend(
            match_aggregate_to_replay(aggregate, replay, scenario_id)
        )
    report["aggregate_patient_reconciliation"]["issues"] = agg_violations
    report["aggregate_patient_reconciliation"]["pass"] = not agg_violations
    report["aggregate_patient_reconciliation"]["critical_failures"] = len(agg_violations)

    # ---- Per-scenario cross-check against in-memory outcomes ----
    event_mismatch_total = 0
    recon_critical_total = 0
    mbe_max = 0.0
    reported_scenarios = []
    for outcome in pipeline.outcomes:
        reported_scenarios.append(outcome.scenario_id)
        event_mismatch_total += outcome.event_quota_mismatches
        recon_critical_total += outcome.reconciliation_issues
        mbe_max = max(mbe_max, outcome.max_abs_mbe)
        # Reproducibility: re-run each scenario and compare to the original.
        rep = _check_reproducible(outcome)
        report["reproducibility"]["details"].append(
            {"scenario_id": outcome.scenario_id, "reproducible": rep}
        )
        if not rep:
            report["reproducibility"]["pass"] = False
    report["event_quota_reconciliation"]["mismatches"] = event_mismatch_total
    report["event_quota_reconciliation"]["pass"] = event_mismatch_total == 0
    report["aggregate_patient_reconciliation"]["critical_failures"] = (
        recon_critical_total + len(agg_violations)
    )
    report["aggregate_patient_reconciliation"]["pass"] = (
        recon_critical_total == 0 and not agg_violations
    )
    report["mass_balance"]["max_abs_mbe"] = mbe_max
    report["mass_balance"]["pass"] = mbe_max < 1e-6

    # Scenario coverage: every Standard-8 + CUSTOM must appear.
    expected = {"S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "CUSTOM"}
    present = set(reported_scenarios)
    missing = expected - present
    report["scenario_coverage"]["missing"] = sorted(missing)
    report["scenario_coverage"]["pass"] = not missing

    # ---- DECISION_REQUIRED / SPEC_CONFLICT ----
    # PRODUCT.md requires a License ID in dataset metadata (section 3.2), but
    # no approved license identifier value exists in the approved documents.
    # The manifest value is implementation-assigned and requires a project
    # decision before any commercial RELEASED status (PRODUCT_RELEASED is
    # separately gated on explicit project-owner approval). This is surfaced
    # here rather than being silently treated as an approved value.
    license_id = manifest.get("license_id", "")
    if not license_id or license_id == "HFSG-EULA-1.0":
        report["decision_required"].append(
            {
                "id": "LICENSE_ID_VALUE",
                "subject": "dataset_manifest.json license_id",
                "current": license_id,
                "requirement": (
                    "PRODUCT.md (section 3.2) requires a License ID in "
                    "dataset metadata; no approved license identifier value "
                    "exists in the frozen documentation."
                ),
                "recommendation": (
                    "Approve the implementation-assigned license identifier "
                    "HFSG-EULA-1.0 or provide an alternative approved value."
                ),
            }
        )

    # ---- CRITICAL summary ----
    report["critical_failures"] = []
    if not report["mass_balance"]["pass"]:
        report["critical_failures"].append("mass_balance")
    if not report["aggregate_patient_reconciliation"]["pass"]:
        report["critical_failures"].append("aggregate_patient_reconciliation")
    if not report["event_quota_reconciliation"]["pass"]:
        report["critical_failures"].append("event_quota_reconciliation")
    if not report["uniqueness"]["pass"]:
        report["critical_failures"].append("uniqueness")
    if not report["temporal_consistency"]["pass"]:
        report["critical_failures"].append("temporal_consistency")
    if not report["manifest_reconciliation"]["pass"]:
        report["critical_failures"].append("manifest_reconciliation")
    if not report["configuration_hash"]["pass"]:
        report["critical_failures"].append("configuration_hash")
    if not report["scenario_coverage"]["pass"]:
        report["critical_failures"].append("scenario_coverage")
    if not report["reproducibility"]["pass"]:
        report["critical_failures"].append("reproducibility")
    report["critical_failures"].sort()

    return report


def _check_reproducible(outcome) -> bool:
    """Re-run the scenario with the exact same seeds and compare to the run."""
    try:
        from .context import build_context
        from .simulation import SimulationDriver

        pipeline = getattr(outcome, "_pipeline", None)
        rng_seed = getattr(outcome, "_rng_seed", None)
        run_index = getattr(pipeline, "_run_index", 0)
        effective = outcome.effective_config
        ctx = build_context(effective, scenario_id=outcome.scenario_id, run_index=run_index)
        rng = np.random.default_rng(rng_seed)
        driver = SimulationDriver(
            effective,
            ctx,
            rng=rng,
            patient_rng=np.random.default_rng(ctx.child_seed),
        )
        run = driver.run()
        if not run.completed_full_horizon:
            return False
        orig_patients = [p.patient_id for p in outcome.run.patients]
        orig_events = [e.event_id for e in outcome.run.events]
        new_patients = [p.patient_id for p in run.patients]
        new_events = [e.event_id for e in run.events]
        return orig_patients == new_patients and orig_events == new_events
    except Exception:
        return False


def _read_plain_parquet(path: Path) -> pd.DataFrame:
    import pyarrow.parquet as pq

    if not path.exists():
        return pd.DataFrame()
    return pq.read_table(path).to_pandas()


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)
