"""Step 9 tests: batch runner, checkpoint/resume, append writes, validation."""

from __future__ import annotations

import json

import pandas as pd
import pyarrow.parquet as pq
import pytest

from hfsg.batch import BatchRunner, RunRecord, validate_batch_outputs
from hfsg.config import ConfigurationLoader
from hfsg.output import count_part_files, write_partition_append

BITES = "config/base.yaml"

SCHEDULE = ["S1", "S7"]


@pytest.fixture(scope="module")
def config():
    return ConfigurationLoader().load(BITES)


def _part_files(root, prefix, scenario_id):
    return sorted((root / prefix / f"scenario_id={scenario_id}").glob("part-*.parquet"))


def _run_batch(config, out_dir, planned, seed=20260905, scenarios=SCHEDULE,
               target=4_000):
    runner = BatchRunner(
        config,
        out_dir,
        target_patients=target,
        planned_runs_per_scenario=planned,
        scenario_ids=scenarios,
        master_seed=seed,
    )
    records = runner.run()
    runner.write_artifacts(validation_status="VALIDATED")
    return runner, records


# ----------------------------------------------------------------------
# Append-aware partition writing
# ----------------------------------------------------------------------

def test_write_partition_append_continues_numbering(config, tmp_path):
    root = tmp_path
    counters = {}
    df1 = pd.DataFrame({"simulation_id": ["a"] * 10, "scenario_id": ["S1"] * 10,
                        "x": list(range(10))})
    df2 = pd.DataFrame({"simulation_id": ["b"] * 5, "scenario_id": ["S1"] * 5,
                        "x": list(range(100, 105))})
    n = write_partition_append(root, "patients", "S1", df1, 10000, counters)
    assert n == 10
    n = write_partition_append(root, "patients", "S1", df2, 10000, counters)
    assert n == 5
    parts = _part_files(root, "patients", "S1")
    assert len(parts) == 2
    assert parts[0].name == "part-0000.parquet"
    assert parts[1].name == "part-0001.parquet"
    combined = pd.concat([pq.read_table(p).to_pandas() for p in parts], ignore_index=True)
    assert list(combined["x"]) == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 100, 101, 102, 103, 104]

    disk = count_part_files(root)
    assert disk[("patients", "S1")] == 2


def test_count_part_files_empty(tmp_path):
    assert count_part_files(tmp_path) == {}


def test_write_partition_append_chunking(config, tmp_path):
    counters = {}
    df = pd.DataFrame({"x": list(range(250_000))})
    written = write_partition_append(tmp_path, "big", "S1", df, 100_000, counters)
    assert written == 250_000
    parts = sorted((tmp_path / "big" / "scenario_id=S1").glob("part-*.parquet"))
    assert len(parts) == 3
    assert counters[("big", "S1")] == 3


# ----------------------------------------------------------------------
# Batch run + artifacts + validation
# ----------------------------------------------------------------------

def test_batch_small_run_validates(config, tmp_path):
    runner, records = _run_batch(config, tmp_path, planned=2)
    assert len(records) == 4
    assert all(r.reconciliation_issues == 0 for r in records)
    assert all(r.max_abs_mbe == 0.0 for r in records)
    assert len({r.simulation_id for r in records}) == 4

    report = validate_batch_outputs(tmp_path)
    assert report["validation_status"] == "VALIDATED"
    assert report["critical_failures"] == []
    assert report["decision_required"] == []
    assert report["checks"]["reproducibility"]["failures"] == []
    assert report["checks"]["manifest"]["configuration_hash_match"] is True
    assert report["checks"]["mass_balance"]["max_abs_mbe"] == 0.0
    assert report["checks"]["mass_balance"]["violations"] == 0
    assert report["checks"]["aggregate_replay"]["total_violations"] == 0
    assert report["checks"]["event_quota_reconciliation"]["total_violations"] == 0
    assert report["checks"]["capacity_source_invariants"]["total_violations"] == 0
    assert report["checks"]["uniqueness"]["total_violations"] == 0
    assert report["checks"]["temporal_consistency"]["total_violations"] == 0

    # Row counts in files must match manifest + summary totals.
    manifest = json.loads((tmp_path / "dataset_manifest.json").read_text())
    assert manifest["patient_record_count"] == report["checks"]["row_counts"]["patients"]
    assert manifest["patient_event_count"] == report["checks"]["row_counts"]["events"]
    summary = pq.read_table(tmp_path / "simulation_summary.parquet").to_pandas()
    assert len(summary) == 4
    assert summary["scenario_id"].nunique() == 2


def test_batch_resume_does_not_duplicate(config, tmp_path):
    _, first = _run_batch(config, tmp_path, planned=2)
    first_rounds = {(r.scenario_id, r.run_index) for r in first}
    assert first_rounds == {("S1", 0), ("S1", 1), ("S7", 0), ("S7", 1)}

    second, resumed = _run_batch(config, tmp_path, planned=3, target=6_000)
    rounds = {(r.scenario_id, r.run_index) for r in resumed}
    assert rounds == {
        ("S1", 0), ("S1", 1), ("S1", 2),
        ("S7", 0), ("S7", 1), ("S7", 2),
    }
    assert len({r.simulation_id for r in resumed}) == 6
    assert len(_part_files(tmp_path, "patients", "S1")) == 3
    assert len(_part_files(tmp_path, "patients", "S7")) == 3

    report = validate_batch_outputs(tmp_path)
    assert report["validation_status"] == "VALIDATED"
    assert report["checks"]["runs"]["total_runs"] == 6
    assert report["checks"]["runs"]["per_scenario_run_counts"] == {"S1": 3, "S7": 3}


def test_batch_no_double_work_when_finished(config, tmp_path):
    _, records = _run_batch(config, tmp_path, planned=2)
    n_parts_before = len(_part_files(tmp_path, "patients", "S1"))

    runner = BatchRunner(
        config, tmp_path, target_patients=4_000, planned_runs_per_scenario=1,
        scenario_ids=SCHEDULE, master_seed=20260905,
    )
    again = runner.run()
    assert len(again) == 4
    assert len(_part_files(tmp_path, "patients", "S1")) == n_parts_before
    runner.write_artifacts(validation_status="VALIDATED")
    report = validate_batch_outputs(tmp_path)
    assert report["validation_status"] == "VALIDATED"


def test_summary_and_comparison_artifacts(config, tmp_path):
    _, records = _run_batch(config, tmp_path, planned=2)
    summary = pd.read_parquet(tmp_path / "simulation_summary.parquet")
    comparison = pd.read_csv(tmp_path / "scenario_comparison.csv")
    assert list(summary.columns) == [
        "simulation_id", "scenario_id", "run_index", "master_seed", "child_seed",
        "total_patients", "total_events", "total_arrivals", "total_transfers",
        "total_discharges", "total_deaths", "final_ed", "final_specialty",
        "final_general", "final_icu", "final_discharged", "final_deceased",
        "mean_active_census", "max_active_census", "max_abs_mbe",
        "reconciliation_issues", "configuration_hash",
    ]
    assert summary["child_seed"].nunique() == 4
    assert list(comparison["scenario_id"]) == SCHEDULE
    assert comparison["run_count"].tolist() == [2, 2]
    for sid in SCHEDULE:
        expected_patients = summary.loc[summary["scenario_id"] == sid, "total_patients"].sum()
        actual = comparison.loc[comparison["scenario_id"] == sid, "total_patients"].iloc[0]
        assert actual == expected_patients


def test_run_record_roundtrip():
    record = RunRecord(
        simulation_id="sim", scenario_id="S1", run_index=0, master_seed=42,
        child_seed=7, patient_count=10, event_count=30, total_arrivals=9,
        total_transfers=4, total_discharges=4, total_deaths=1, final_ed=1,
        final_specialty=2, final_general=3, final_icu=1, final_discharged=4,
        final_deceased=1, mean_active_census=6.0, max_active_census=8.0,
        max_abs_mbe=0.0, reconciliation_issues=0, event_quota_mismatches=0,
        patient_invariant_critical=0, completed_full_horizon=True,
        configuration_hash="hash",
    )
    restored = RunRecord.from_dict(record.to_dict())
    assert restored == record


def test_license_approved_yields_no_decision(config, tmp_path):
    _run_batch(config, tmp_path, planned=2)
    report = validate_batch_outputs(tmp_path)
    assert report["decision_required"] == []


def test_license_missing_flags_decision(config, tmp_path):
    _run_batch(config, tmp_path, planned=2)
    manifest_path = tmp_path / "dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["license_id"] = ""
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    report = validate_batch_outputs(tmp_path)
    assert report["decision_required"] == ["LICENSE_ID_VALUE"]


def test_mass_balance_recompute_matches_engine(config, tmp_path):
    """Recomputed mass balance from written aggregate == recorded engine mbe."""
    runner = BatchRunner(
        config, tmp_path, target_patients=1_000, planned_runs_per_scenario=1,
        scenario_ids=SCHEDULE, master_seed=20260905,
    )
    records = runner.run()
    runner.write_artifacts(validation_status="VALIDATED")
    s7 = next(r for r in records if r.scenario_id == "S7")
    agg = pd.read_parquet(tmp_path / "aggregate_timeseries/scenario_id=S7/part-0000.parquet")
    n0 = (agg["ed_census"] + agg["specialty_census"] + agg["general_census"]
          + agg["icu_census"] + agg["discharged"] + agg["deceased"]).iloc[0] \
         - agg["cumulative_arrivals"].iloc[0]
    total = (agg["ed_census"] + agg["specialty_census"] + agg["general_census"]
             + agg["icu_census"] + agg["discharged"] + agg["deceased"])
    recomputed = (total - (n0 + agg["cumulative_arrivals"])).abs().max()
    assert recomputed == pytest.approx(s7.max_abs_mbe, abs=1e-6)