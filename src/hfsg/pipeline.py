"""Step 8 orchestrator: run S1-S8 + CUSTOM and write the output pipeline.

Coordinates the ScenarioManager (effective configs), the SimulationDriver
(SAME Core Engine for every scenario), the output writers, the manifest, the
validation report, and post-serialization round-trip validation.

The full Dataset is not held in RAM: each scenario produces its own
patient/event/aggregate/summary frames which are written to their
scenario_id partition immediately after the run.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .config import Configuration
from .context import build_context
from .events import EVENT_DEATH, EVENT_DISCHARGE, EVENT_TRANSFER
from .output import (
    SUMMARY_COLUMNS,
    aggregate_frame,
    dataset_manifest,
    events_frame,
    patients_frame,
    write_csv,
    write_json,
    write_partitioned,
    write_yaml,
)
from .patient_validation import PatientValidator
from .scenarios import (
    CUSTOM_SCENARIO_ID,
    ScenarioManager,
    configuration_hash,
    hash_yaml,
)
from .simulation import SimulationDriver

PRODUCT_ID = "HFSG-DS"
DATASET_VERSION = "1.0"
LICENSE_ID = "HFSG-EULA-1.0"
SCENARIO_PACK = "Standard-8+CUSTOM"

INITIAL_STOCKS = {"ed": 20, "specialty": 25, "general": 60, "icu": 10}


class Step8Error(RuntimeError):
    """Raised when the Step 8 pipeline cannot proceed or a gate fails."""


@dataclass
class ScenarioRunOutcome:
    scenario_id: str
    effective_config: Configuration
    config_hash: str
    run: Any
    patient_count: int
    event_count: int
    reconciliation_issues: int
    max_abs_mbe: float
    event_quota_mismatches: int
    patient_invariant_critical: int
    completed_full_horizon: bool
    summary_row: Dict[str, Any]
    _pipeline: Any = field(default=None, repr=False)
    _rng_seed: int = field(default=0, repr=False)


class Pipeline:
    """Runs all scenarios and writes the approved output bundle."""

    INITIAL_STOCKS = {"ed": 20, "specialty": 25, "general": 60, "icu": 10}

    def __init__(
        self,
        base_config: Configuration,
        out_dir: Path,
        scenario_ids: Optional[List[str]] = None,
        custom_profile: Optional[Dict[str, Any]] = None,
        run_index: int = 0,
        seed=None,
        patient_chunk_rows: int = 50000,
        event_chunk_rows: int = 100000,
    ) -> None:
        self._base_config = base_config
        self._manager = ScenarioManager(base_config)
        self._out_dir = Path(out_dir)
        req = base_config.batch
        self._patient_chunk = int(patient_chunk_rows or 50000)
        self._event_chunk = int(event_chunk_rows or 100000)
        if scenario_ids is None:
            scenario_ids = list(self._manager.scenario_ids())
        if CUSTOM_SCENARIO_ID in scenario_ids and custom_profile is not None:
            self._manager.validate_custom(custom_profile)
            self._custom_profile = dict(custom_profile)
        else:
            self._custom_profile = None
        self._scenario_ids = list(scenario_ids)
        self._run_index = run_index

        # Reproducible per-run seed derived from configuration master seed.
        master_seed = int(base_config.reproducibility["master_seed"])
        self._master_seed = master_seed
        self._seed = seed if seed is not None else derive_run_seed(master_seed, run_index)
        self._outcomes: List[ScenarioRunOutcome] = []
        self._simulation_ids: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> "Pipeline":
        self._out_dir.mkdir(parents=True, exist_ok=True)
        outcomes = []
        for scenario_id in self._scenario_ids:
            outcome = self._run_one(scenario_id)
            outcomes.append(outcome)
            self._outcomes = outcomes
        return self

    @property
    def outcomes(self) -> List[ScenarioRunOutcome]:
        return self._outcomes

    @property
    def engine_version(self) -> str:
        import hfsg

        return hfsg.__version__

    def build_summary_frame(self) -> pd.DataFrame:
        rows = [o.summary_row for o in self._outcomes]
        return pd.DataFrame(rows)[list(SUMMARY_COLUMNS)]

    def build_scenario_comparison(self) -> pd.DataFrame:
        rows = []
        for o in self._outcomes:
            final = o.run.final
            rows.append(
                {
                    "scenario_id": o.scenario_id,
                    "configuration_hash": o.config_hash,
                    "reconciliation_issues": o.reconciliation_issues,
                    "max_abs_mbe": o.max_abs_mbe,
                    "final_active_census": (
                        final.ed + final.specialty + final.general + final.icu
                    ),
                    "final_discharged": final.discharged,
                    "final_deceased": final.deceased,
                    "total_deaths": o.summary_row["total_deaths"],
                    "total_discharges": o.summary_row["total_discharges"],
                    "total_arrivals": o.summary_row["total_arrivals"],
                    "mean_active_census": o.summary_row["mean_active_census"],
                    "max_active_census": o.summary_row["max_active_census"],
                }
            )
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Per-scenario run + write
    # ------------------------------------------------------------------

    def _run_one(self, scenario_id: str) -> ScenarioRunOutcome:
        effective = self._manager.effective_configuration(scenario_id)
        # Build the per-run child seed via the approved context builder so the
        # reproducibility policy is uniform across scenarios.
        ctx = build_context(effective, scenario_id=scenario_id, run_index=self._run_index)
        rng = np.random.default_rng(self._seed)

        driver = SimulationDriver(
            effective,
            ctx,
            rng=rng,
            patient_rng=np.random.default_rng(ctx.child_seed),
        )
        run = driver.run()

        n_patients = len(run.patients)
        n_events = len(run.events)

        # Reconciliation/metrics.
        issues = driver.reconciler.result().issues
        recon_critical = [i for i in issues if i.severity == "critical"]
        max_mbe = self._max_abs_mbe(run)
        event_mismatch = self._event_quota_mismatches(run)
        pv = PatientValidator().validate(run.patients, run.events, run.horizon_steps - 1)
        pv_critical = len(pv.critical_issues)
        completed = run.completed_full_horizon
        final = run.final

        totals = self._totals(run)
        censuses = [outcome.after.active_total for outcome in run.outcomes]
        mean_census = float(np.mean(censuses)) if censuses else 0.0
        max_census = float(np.max(censuses)) if censuses else 0.0

        config_hash = configuration_hash(effective)
        summary_row = {
            "simulation_id": ctx.simulation_id,
            "scenario_id": scenario_id,
            "run_index": self._run_index,
            "master_seed": ctx.master_seed,
            "child_seed": ctx.child_seed,
            "total_patients": n_patients,
            "total_events": n_events,
            "total_arrivals": totals["arrivals"],
            "total_transfers": totals["transfers"],
            "total_discharges": totals["discharges"],
            "total_deaths": totals["deaths"],
            "final_ed": final.ed,
            "final_specialty": final.specialty,
            "final_general": final.general,
            "final_icu": final.icu,
            "final_discharged": final.discharged,
            "final_deceased": final.deceased,
            "mean_active_census": round(mean_census, 4),
            "max_active_census": round(max_census, 4),
            "max_abs_mbe": round(max_mbe, 6),
            "reconciliation_issues": len(issues),
            "configuration_hash": config_hash,
        }

        # Write this scenario's partition immediately (bounded memory).
        p_frame = patients_frame(ctx.simulation_id, scenario_id, run.patients)
        e_frame = events_frame(ctx.simulation_id, scenario_id, run.events)
        a_frame = aggregate_frame(ctx.simulation_id, scenario_id, run.outcomes)

        write_partitioned(
            self._out_dir / "patients",
            "patients",
            [(scenario_id, p_frame)],
            self._patient_chunk,
        )
        write_partitioned(
            self._out_dir / "patient_events",
            "patient_events",
            [(scenario_id, e_frame)],
            self._event_chunk,
        )
        write_partitioned(
            self._out_dir / "aggregate_timeseries",
            "aggregate_timeseries",
            [(scenario_id, a_frame)],
            5000,
        )

        self._simulation_ids[scenario_id] = ctx.simulation_id
        return ScenarioRunOutcome(
            scenario_id=scenario_id,
            effective_config=effective,
            config_hash=config_hash,
            run=run,
            patient_count=n_patients,
            event_count=n_events,
            reconciliation_issues=len(issues),
            max_abs_mbe=max_mbe,
            event_quota_mismatches=event_mismatch,
            patient_invariant_critical=pv_critical,
            completed_full_horizon=completed,
            summary_row=summary_row,
            _pipeline=self,
            _rng_seed=self._seed,
        )

    # ------------------------------------------------------------------
    # Metrics helpers
    # ------------------------------------------------------------------

    def _max_abs_mbe(self, run) -> float:
        n0 = len(run.initial_stocks)
        worst = 0.0
        for outcome in run.outcomes:
            after = outcome.after
            total = (
                after.ed
                + after.specialty
                + after.general
                + after.icu
                + after.discharged
                + after.deceased
            )
            worst = max(worst, abs(total - (n0 + after.cumulative_arrivals)))
        return worst

    def _event_quota_mismatches(self, run) -> int:
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
            rdm = sum(
                outcome.realized_flow.get(f, 0) for f in ("M_C", "M_G", "M_I")
            )
            mismatches += int(transfer != rt) + int(discharge != rd) + int(death != rdm)
        return mismatches

    def _totals(self, run) -> Dict[str, int]:
        transfers = discharges = deaths = arrivals = 0
        for outcome in run.outcomes:
            arrivals += outcome.arrivals_accepted
            for e in outcome.step_events:
                if e.event_type == EVENT_TRANSFER:
                    transfers += 1
                elif e.event_type == EVENT_DISCHARGE:
                    discharges += 1
                elif e.event_type == EVENT_DEATH:
                    deaths += 1
        return {
            "arrivals": arrivals,
            "transfers": transfers,
            "discharges": discharges,
            "deaths": deaths,
        }

    # ------------------------------------------------------------------
    # Post-run artifacts
    # ------------------------------------------------------------------

    def write_outputs(self) -> Dict[str, Any]:
        """Write all derived outputs and return the manifest dict."""
        out = self._out_dir

        # simulation_summary already written per-scenario during run; build the
        # full combined summary for completeness.
        summary = self.build_summary_frame()
        import pyarrow as pa
        import pyarrow.parquet as pq

        pq.write_table(
            pa.Table.from_pandas(summary, preserve_index=False),
            out / "simulation_summary.parquet",
            compression="zstd",
        )

        comparison = self.build_scenario_comparison()
        write_csv(out / "scenario_comparison.csv", comparison)

        # used_configuration: preserve the exact effective configuration.
        # Store the base configuration and per-scenario overrides so the exact
        # used configuration is reproducible.
        used = {
            "base_configuration": self._base_config.data,
            "scenario_overrides": {
                sid: self._manager.scenario_definition(sid)
                for sid in self._scenario_ids
            },
        }
        self._used_configuration = used
        self._dataset_configuration_hash = hash_yaml(used)
        write_yaml(out / "used_configuration.yaml", used)

        return summary

    def finalize_manifest_and_report(self, validation_status: str) -> Dict[str, Any]:
        total_patients = sum(o.patient_count for o in self._outcomes)
        total_events = sum(o.event_count for o in self._outcomes)

        manifest = dataset_manifest(
            product_id=PRODUCT_ID,
            dataset_id=self.dataset_id(),
            dataset_version=DATASET_VERSION,
            engine_version=self.engine_version,
            scenario_pack=SCENARIO_PACK,
            patient_count=total_patients,
            event_count=total_events,
            configuration_hash=self.dataset_configuration_hash(),
            validation_status=validation_status,
            license_id=LICENSE_ID,
        )
        write_json(self._out_dir / "dataset_manifest.json", manifest)
        return manifest

    def dataset_id(self) -> str:
        from datetime import datetime

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"HFSG-DS-STD8-2026-{stamp}"

    def dataset_configuration_hash(self) -> str:
        """Hash of the exact preserved used configuration (raw dataset-level).

        The manifest configuration_hash must match the preserved
        used_configuration.yaml, so the hash is computed over that same dict
        (base configuration + per-scenario overrides).
        """
        used = getattr(self, "_used_configuration", None)
        if used is None:
            used = {
                "base_configuration": self._base_config.data,
                "scenario_overrides": {
                    sid: self._manager.scenario_definition(sid)
                    for sid in self._scenario_ids
                },
            }
        return hash_yaml(used)


def derive_run_seed(master_seed: int, run_index: int) -> int:
    return (int(master_seed) + 100_003 * int(run_index)) & ((1 << 63) - 1)
