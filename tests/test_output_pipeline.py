"""Step 8 tests: output writers and the batch pipeline.

Covers: write_partitioned/read_partitioned round-trip (ZSTD, scenario_id
partitioning), patients/events/aggregate/summary frame builders, manifest
counts == actual, dataset-level configuration hash round-trip, aggregate
replay reconciliation, post-serialization invariant checks, and the full
validate_outputs report over an all-scenario short run.
"""

import copy
import glob
import json

import numpy as np
import pandas as pd
import pytest
import yaml

from hfsg.config import ConfigurationLoader
from hfsg.output import (
    aggregate_frame,
    check_post_serialization,
    events_frame,
    match_aggregate_to_replay,
    patients_frame,
    read_partitioned,
    replay_operational_stocks,
    summary_frame,
    write_json,
    write_partitioned,
)
from hfsg.pipeline import Pipeline
from hfsg.scenarios import ScenarioManager, hash_yaml
from hfsg.validation_report import validate_outputs

BASE = "config/base.yaml"
INITIAL_STOCKS = {"ed": 20, "specialty": 25, "general": 60, "icu": 10}


def short_config(tmp_path, simulation_hours=24):
    """base.yaml with a short simulation horizon for fast tests."""
    cfg = ConfigurationLoader().load(BASE)
    data = copy.deepcopy(cfg.data)
    data["simulation_hours"] = simulation_hours
    return ConfigurationLoader().from_data(data, source=str(tmp_path / "short.yaml"))


class TestPartitionedWriteRead:
    def test_roundtrip_preserves_rows_and_scenario(self, tmp_path):
        p1 = pd.DataFrame(
            {
                "patient_id": [1, 2],
                "scenario_id": ["S1", "S1"],
                "simulation_id": ["sim", "sim"],
            }
        )
        p2 = pd.DataFrame(
            {
                "patient_id": [3, 4, 5],
                "scenario_id": ["S2", "S2", "S2"],
                "simulation_id": ["sim", "sim", "sim"],
            }
        )
        write_partitioned(
            tmp_path / "patients",
            "patients",
            [("S1", p1), ("S2", p2)],
            chunk_rows=2,
        )
        # partition dirs per scenario_id
        assert (tmp_path / "patients" / "scenario_id=S1").is_dir()
        assert (tmp_path / "patients" / "scenario_id=S2").is_dir()
        back = read_partitioned(tmp_path / "patients")
        assert len(back) == 5
        assert sorted(back["scenario_id"].unique().tolist()) == ["S1", "S2"]

    def test_zstd_compression(self, tmp_path):
        df = pd.DataFrame(
            {
                "patient_id": [1, 2],
                "scenario_id": ["S1", "S1"],
                "simulation_id": ["sim", "sim"],
            }
        )
        write_partitioned(tmp_path / "p", "p", [("S1", df)], chunk_rows=1)
        import pyarrow.parquet as pq

        part = sorted(glob.glob(str(tmp_path / "p" / "scenario_id=S1" / "*.parquet")))[0]
        meta = pq.read_metadata(part)
        assert meta.row_group(0).column(0).compression == "ZSTD"


class TestFrameBuilders:
    def _run(self, config, scenario_id="S1"):
        from hfsg.context import build_context
        from hfsg.simulation import SimulationDriver

        ctx = build_context(config, scenario_id=scenario_id, run_index=0)
        return (
            ctx,
            SimulationDriver(
                config,
                ctx,
                rng=np.random.default_rng(1),
                patient_rng=np.random.default_rng(ctx.child_seed),
            ).run(),
        )

    def test_patients_frame_shape(self, config):
        ctx, run = self._run(config)
        frame = patients_frame(ctx.simulation_id, "S1", run.patients)
        assert len(frame) == len(run.patients)
        assert set(["patient_id", "scenario_id", "simulation_id"]).issubset(frame.columns)

    def test_events_frame_shape(self, config):
        ctx, run = self._run(config)
        frame = events_frame(ctx.simulation_id, "S1", run.events)
        assert len(frame) == len(run.events)
        assert set(["event_id", "patient_id", "scenario_id", "event_type"]).issubset(frame.columns)

    def test_aggregate_frame_hours(self, config):
        ctx, run = self._run(config)
        frame = aggregate_frame(ctx.simulation_id, "S1", run.outcomes)
        assert len(frame) == len(run.outcomes)
        # one scenario_id column only (no x/y merge pollution)
        assert sum(1 for c in frame.columns if c.startswith("scenario_id")) == 1

    def test_summary_frame(self, config):
        ctx, run = self._run(config)
        row = {
            key: 0
            for key in (
                "run_index", "master_seed", "child_seed", "total_patients",
                "total_events", "total_arrivals", "total_transfers",
                "total_discharges", "total_deaths", "final_ed",
                "final_specialty", "final_general", "final_icu",
                "final_discharged", "final_deceased", "mean_active_census",
                "max_active_census", "max_abs_mbe", "reconciliation_issues",
            )
        }
        row["simulation_id"] = ctx.simulation_id
        row["scenario_id"] = "S1"
        row["configuration_hash"] = "abc"
        frame = summary_frame(row)
        assert "scenario_id" in frame.columns
        assert len(frame) == 1

    @pytest.fixture
    def config(self, tmp_path):
        return short_config(tmp_path)


class TestReplayReconciliation:
    def test_replay_matches_aggregate(self, tmp_path):
        cfg = short_config(tmp_path)
        pipeline = Pipeline(cfg, tmp_path / "out", scenario_ids=["S1"], seed=7).run()
        out = pipeline._out_dir
        events = read_partitioned(out / "patient_events")
        patients = read_partitioned(out / "patients")
        aggregate = read_partitioned(out / "aggregate_timeseries")
        replay = replay_operational_stocks(
            events, INITIAL_STOCKS, "S1", patients_df=patients
        )
        violations = match_aggregate_to_replay(aggregate, replay, "S1")
        assert violations == []

    def test_initial_population_not_double_counted(self, tmp_path):
        """Initial-population ARRIVAL events must not inflate the replay."""
        cfg = short_config(tmp_path)
        pipeline = Pipeline(cfg, tmp_path / "out", scenario_ids=["S1"], seed=7).run()
        out = pipeline._out_dir
        events = read_partitioned(out / "patient_events")
        patients = read_partitioned(out / "patients")
        replay = replay_operational_stocks(
            events, INITIAL_STOCKS, "S1", patients_df=patients
        )
        n0 = sum(INITIAL_STOCKS.values())
        assert replay["cumulative_arrivals"].iloc[0] < n0
        # without the patients frame, initial arrivals double-count
        replay_naive = replay_operational_stocks(events, INITIAL_STOCKS, "S1")
        assert replay_naive["cumulative_arrivals"].iloc[0] >= n0


class TestPipelineOutputs:
    SCENARIOS = ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "CUSTOM"]

    def _run_full(self, tmp_path, seed=11):
        out = tmp_path / "out"
        pipeline = Pipeline(
            short_config(tmp_path),
            out,
            scenario_ids=list(self.SCENARIOS),
            seed=seed,
        ).run()
        pipeline.write_outputs()
        manifest = pipeline.finalize_manifest_and_report("VALIDATING")
        report = validate_outputs(out, manifest, pipeline, INITIAL_STOCKS)
        write_json(out / "validation_report.json", report)
        manifest = pipeline.finalize_manifest_and_report("VALIDATED")
        return pipeline, manifest, out

    def test_all_output_files_written(self, tmp_path):
        _, _, out = self._run_full(tmp_path)
        for name in (
            "patients",
            "patient_events",
            "aggregate_timeseries",
            "simulation_summary.parquet",
            "scenario_comparison.csv",
            "dataset_manifest.json",
            "validation_report.json",
            "used_configuration.yaml",
        ):
            assert (out / name).exists(), name

    def test_manifest_counts_are_actual(self, tmp_path):
        pipeline, manifest, out = self._run_full(tmp_path)
        patients = read_partitioned(out / "patients")
        events = read_partitioned(out / "patient_events")
        assert manifest["patient_record_count"] == len(patients)
        assert manifest["patient_event_count"] == len(events)
        assert manifest["scenario_pack"] == "Standard-8+CUSTOM"

    def test_configuration_hash_roundtrip(self, tmp_path):
        _, manifest, out = self._run_full(tmp_path)
        with open(out / "used_configuration.yaml", "r", encoding="utf-8") as handle:
            used_back = yaml.safe_load(handle)
        assert hash_yaml(used_back) == manifest["configuration_hash"]

    def test_scenario_comparison_covers_all(self, tmp_path):
        _, _, out = self._run_full(tmp_path)
        comparison = pd.read_csv(out / "scenario_comparison.csv")
        assert set(comparison["scenario_id"]) == set(self.SCENARIOS)

    def test_check_post_serialization_clean(self, tmp_path):
        _, _, out = self._run_full(tmp_path)
        patients = read_partitioned(out / "patients")
        events = read_partitioned(out / "patient_events")
        assert check_post_serialization(patients, events) == []

    def test_validate_outputs_full_pass(self, tmp_path):
        pipeline, _, out = self._run_full(tmp_path)
        final_manifest = pipeline.finalize_manifest_and_report("VALIDATED")
        report = validate_outputs(
            out, final_manifest, pipeline, INITIAL_STOCKS
        )
        assert report["critical_failures"] == []
        assert report["scenario_coverage"]["missing"] == []
        assert report["reproducibility"]["pass"] is True
        assert report["mass_balance"]["pass"] is True
        assert report["aggregate_patient_reconciliation"]["pass"] is True


class TestScenarioManagerOnShortConfig:
    def test_effective_configuration_usable_in_run(self, tmp_path):
        cfg = short_config(tmp_path)
        mgr = ScenarioManager(cfg)
        eff = mgr.effective_configuration("S7")
        assert eff.data["arrivals"]["overrides"]["arrivals_wave"]["duration_hours"] == 48

    def test_invalid_custom_rejected_on_pipeline(self, tmp_path):
        from hfsg.scenarios import ScenarioError

        cfg = short_config(tmp_path)
        with pytest.raises(ScenarioError):
            Pipeline(
                cfg,
                tmp_path / "out",
                scenario_ids=["CUSTOM"],
                custom_profile={"arrivals_multiplier": 9.0},
            )


class TestManifestContents(TestPipelineOutputs):
    def test_manifest_required_keys(self, tmp_path):
        _, manifest, _ = self._run_full(tmp_path)
        for key in (
            "product_id",
            "dataset_id",
            "dataset_version",
            "engine_version",
            "scenario_pack",
            "patient_record_count",
            "patient_event_count",
            "generation_timestamp",
            "configuration_hash",
            "license_id",
            "data_type",
            "status",
        ):
            assert manifest[key], key
        assert manifest["data_type"] == "simulated_patient_event_data"

    def test_engine_version_matches_package(self, tmp_path):
        import hfsg

        pipeline, _, _ = self._run_full(tmp_path)
        assert pipeline.engine_version == hfsg.__version__