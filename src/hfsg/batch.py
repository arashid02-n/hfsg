"""Step 9 batch generation: G2 dry run and G3 production batch.

Implements MODEL.md sections 26-28 and OPERATIONS.md sections 16-18:

- planned runs per Standard-8 scenario (plus CUSTOM) from ``config.batch``;
- one ``master_seed`` per batch, deterministic child seed per run
  (``derive_child_seed(master_seed, scenario_id, run_index)``);
- append-aware, scenario_id-partitioned ZSTD Parquet output (one part file
  per simulation run per dataset, so files align with runs);
- checkpoint / resume so an interrupted Batch never restarts at zero;
- bounded memory (one run's frames in RAM at a time);
- per-run invariant checks during generation, and Batch-level validation of
  the written dataset via ``validate_batch_outputs`` (memory bounded).

The complete Dataset is never held in RAM.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from .config import Configuration, ConfigurationLoader
from .context import SimulationContext
from .events import EVENT_DEATH, EVENT_DISCHARGE, EVENT_TRANSFER
from .output import (
    AGGREGATE_STOCK_COLUMNS,
    SUMMARY_COLUMNS,
    aggregate_frame,
    check_post_serialization,
    count_part_files,
    dataset_manifest,
    events_frame,
    match_aggregate_to_replay,
    patients_frame,
    replay_operational_stocks,
    summary_frame,
    write_csv,
    write_json,
    write_partition_append,
    write_yaml,
)
from .patient_validation import PatientValidator
from .pipeline import DATASET_VERSION, LICENSE_ID, PRODUCT_ID, SCENARIO_PACK
from .scenarios import ScenarioManager, hash_yaml
from .seeds import derive_child_seed
from .simulation import SimulationDriver
from .units import DEATH_FLOWS, DISCHARGE_FLOWS, TRANSFER_NAMES

CHECKPOINT_VERSION = 1
INITIAL_UNITS = ("ed", "specialty", "general", "icu")

# Approved deviation from MODEL.md section 26 (>= 1,000,000 planned records):
# the Project Owner instructed on 2026-09-05 to cap this Batch at 100,000
# patients because the build workstation cannot feasibly produce 1M records.
PRODUCTION_TARGET_NOTES = [
    "MODEL.md section 26 plans a production Batch of >= 1,000,000 patient "
    "records.",
    "This Batch targets 100,000 patient records per explicit Project Owner "
    "instruction on 2026-09-05; the current build workstation (3.7 GiB RAM, "
    "~1.3 GiB free disk, 2 CPU cores) cannot feasibly hold, write or validate "
    "the full 1,000,000-record dataset, and 100,000 patients was approved as "
    "sufficient for this deliverable.",
    "Validation, reconciliation, reproducibility, Standard-8 coverage and "
    "all output-format requirements apply unchanged to this 100,000-record "
    "Batch; only the volume target is reduced.",
]


class BatchError(RuntimeError):
    """Raised when a Batch cannot proceed (critical invariant failure)."""


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_batch_id() -> str:
    return "HFSG-BATCH-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


# ----------------------------------------------------------------------
# Run record
# ----------------------------------------------------------------------

@dataclass
class RunRecord:
    """Immutable record of one completed simulation run."""

    simulation_id: str
    scenario_id: str
    run_index: int
    master_seed: int
    child_seed: int
    patient_count: int
    event_count: int
    total_arrivals: int
    total_transfers: int
    total_discharges: int
    total_deaths: int
    final_ed: int
    final_specialty: int
    final_general: int
    final_icu: int
    final_discharged: int
    final_deceased: int
    mean_active_census: float
    max_active_census: float
    max_abs_mbe: float
    reconciliation_issues: int
    event_quota_mismatches: int
    patient_invariant_critical: int
    completed_full_horizon: bool
    configuration_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return dict(
            simulation_id=self.simulation_id,
            scenario_id=self.scenario_id,
            run_index=self.run_index,
            master_seed=self.master_seed,
            child_seed=self.child_seed,
            patient_count=self.patient_count,
            event_count=self.event_count,
            total_arrivals=self.total_arrivals,
            total_transfers=self.total_transfers,
            total_discharges=self.total_discharges,
            total_deaths=self.total_deaths,
            final_ed=self.final_ed,
            final_specialty=self.final_specialty,
            final_general=self.final_general,
            final_icu=self.final_icu,
            final_discharged=self.final_discharged,
            final_deceased=self.final_deceased,
            mean_active_census=self.mean_active_census,
            max_active_census=self.max_active_census,
            max_abs_mbe=self.max_abs_mbe,
            reconciliation_issues=self.reconciliation_issues,
            event_quota_mismatches=self.event_quota_mismatches,
            patient_invariant_critical=self.patient_invariant_critical,
            completed_full_horizon=self.completed_full_horizon,
            configuration_hash=self.configuration_hash,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunRecord":
        return cls(**data)

    def summary_row(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "scenario_id": self.scenario_id,
            "run_index": self.run_index,
            "master_seed": self.master_seed,
            "child_seed": self.child_seed,
            "total_patients": self.patient_count,
            "total_events": self.event_count,
            "total_arrivals": self.total_arrivals,
            "total_transfers": self.total_transfers,
            "total_discharges": self.total_discharges,
            "total_deaths": self.total_deaths,
            "final_ed": self.final_ed,
            "final_specialty": self.final_specialty,
            "final_general": self.final_general,
            "final_icu": self.final_icu,
            "final_discharged": self.final_discharged,
            "final_deceased": self.final_deceased,
            "mean_active_census": round(self.mean_active_census, 4),
            "max_active_census": round(self.max_active_census, 4),
            "max_abs_mbe": round(self.max_abs_mbe, 6),
            "reconciliation_issues": self.reconciliation_issues,
            "configuration_hash": self.configuration_hash,
        }


# ----------------------------------------------------------------------
# Batch runner
# ----------------------------------------------------------------------

class BatchRunner:
    """Deterministic, checkpointed generator of the production Batch.

    The schedule is round-robin: for each round ``0..planned_runs-1`` every
    scenario in ``schedule`` produces one run. Runs already recorded in the
    checkpoint are skipped on resume, so an interrupted Batch continues from
    the checkpoint instead of restarting at zero.
    """

    def __init__(
        self,
        base_config: Configuration,
        out_dir: str | Path,
        *,
        target_patients: Optional[int] = None,
        planned_runs_per_scenario: Optional[int] = None,
        scenario_ids: Optional[Sequence[str]] = None,
        master_seed: Optional[int] = None,
        patient_chunk_rows: Optional[int] = None,
        event_chunk_rows: Optional[int] = None,
    ) -> None:
        self._config = base_config
        self._manager = ScenarioManager(base_config)
        self._out_dir = Path(out_dir)

        batch = base_config.batch or {}
        self._target = (
            int(target_patients) if target_patients is not None
            else int(batch["target_patient_records"])
        )
        self._planned = (
            int(planned_runs_per_scenario) if planned_runs_per_scenario is not None
            else int(batch["planned_runs_per_scenario"])
        )
        self._patient_chunk = (
            int(patient_chunk_rows) if patient_chunk_rows is not None
            else int(batch["patient_chunk_rows"])
        )
        self._event_chunk = (
            int(event_chunk_rows) if event_chunk_rows is not None
            else int(batch["event_chunk_rows"])
        )

        required = list(batch.get("required_standard_scenarios") or [])
        custom = "CUSTOM" if "CUSTOM" not in required else None
        self._schedule = tuple(
            scenario_ids if scenario_ids is not None
            else (required + ([custom] if custom else []))
        )
        known = set(self._manager.scenario_ids())
        for sid in self._schedule:
            if sid not in known:
                raise BatchError(f"unknown scenario in Batch schedule: {sid!r}")

        self._master_seed = (
            int(master_seed) if master_seed is not None
            else int(base_config.reproducibility["master_seed"])
        )

        self._checkpoint_path = self._out_dir / "batch_checkpoint.json"
        self._batch_id = _new_batch_id()
        self._records: List[RunRecord] = []
        self._completed: set = set()
        self._cumulative_patients = 0
        self._cumulative_events = 0
        self._counters: Dict[Tuple[str, str], int] = {}
        self.finished = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> List[RunRecord]:
        """Execute the planned schedule, checkpointing after every run."""
        self._out_dir.mkdir(parents=True, exist_ok=True)
        self._load_checkpoint()

        for round_index in range(self._planned):
            for scenario_id in self._schedule:
                if (scenario_id, round_index) in self._completed:
                    continue
                record = self._run_one(scenario_id, round_index)
                self._records.append(record)
                self._completed.add((record.scenario_id, record.run_index))
                self._cumulative_patients += record.patient_count
                self._cumulative_events += record.event_count
                self._checkpoint()
            if self._at_target():
                break

        # A Batch is finished only when the patient target is met (MODEL.md
        # section 26: completion requires target volume + Standard-8 coverage).
        self.finished = self._cumulative_patients >= self._target
        self._checkpoint()
        return self._records

    def _at_target(self) -> bool:
        """Stop after a full round once the patient target is reached."""
        return self._cumulative_patients >= self._target

    @property
    def schedule(self) -> Tuple[str, ...]:
        return self._schedule

    @property
    def master_seed(self) -> int:
        return self._master_seed

    @property
    def cumulative_patients(self) -> int:
        return self._cumulative_patients

    @property
    def cumulative_events(self) -> int:
        return self._cumulative_events

    @property
    def out_dir(self) -> Path:
        return self._out_dir

    # ------------------------------------------------------------------
    # Single run (mirrors pipeline._run_one but with child-seed engine rng)
    # ------------------------------------------------------------------

    def _run_one(self, scenario_id: str, run_index: int) -> RunRecord:
        effective = self._manager.effective_configuration(scenario_id)
        child_seed = derive_child_seed(self._master_seed, scenario_id, run_index)
        ctx = SimulationContext(
            scenario_id=scenario_id,
            run_index=run_index,
            master_seed=self._master_seed,
            child_seed=child_seed,
            model_version=str(effective.version),
            configuration_version=str(effective.version),
        )
        rng = np.random.default_rng(child_seed)

        driver = SimulationDriver(
            effective,
            ctx,
            rng=rng,
            patient_rng=np.random.default_rng(child_seed),
        )
        run = driver.run()

        issues = driver.reconciler.result().issues
        recon_critical = [i for i in issues if i.severity == "critical"]
        if recon_critical:
            raise BatchError(
                f"{scenario_id} run {run_index}: critical reconciliation "
                f"failure: {recon_critical[0].message}"
            )
        if not run.completed_full_horizon:
            raise BatchError(
                f"{scenario_id} run {run_index}: simulation did not complete "
                "the full horizon"
            )

        pv = PatientValidator().validate(run.patients, run.events, run.horizon_steps - 1)
        pv_critical = len(pv.critical_issues)
        if pv_critical:
            raise BatchError(
                f"{scenario_id} run {run_index}: patient invariant failure "
                f"({pv_critical} critical issue(s))"
            )

        max_mbe = self._max_abs_mbe(run)
        event_mismatch = self._event_quota_mismatches(run)
        totals = self._totals(run)
        censuses = [outcome.after.active_total for outcome in run.outcomes]
        mean_census = float(np.mean(censuses)) if censuses else 0.0
        max_census = float(np.max(censuses)) if censuses else 0.0
        final = run.final
        config_hash = self._configuration_hash(effective)

        # Write this run's partitions immediately (bounded memory).
        p_frame = patients_frame(ctx.simulation_id, scenario_id, run.patients)
        e_frame = events_frame(ctx.simulation_id, scenario_id, run.events)
        a_frame = aggregate_frame(ctx.simulation_id, scenario_id, run.outcomes)

        write_partition_append(
            self._out_dir, "patients", scenario_id, p_frame, self._patient_chunk,
            self._counters,
        )
        write_partition_append(
            self._out_dir, "patient_events", scenario_id, e_frame, self._event_chunk,
            self._counters,
        )
        write_partition_append(
            self._out_dir, "aggregate_timeseries", scenario_id, a_frame, 5000,
            self._counters,
        )

        return RunRecord(
            simulation_id=ctx.simulation_id,
            scenario_id=scenario_id,
            run_index=run_index,
            master_seed=self._master_seed,
            child_seed=child_seed,
            patient_count=len(run.patients),
            event_count=len(run.events),
            total_arrivals=totals["arrivals"],
            total_transfers=totals["transfers"],
            total_discharges=totals["discharges"],
            total_deaths=totals["deaths"],
            final_ed=final.ed,
            final_specialty=final.specialty,
            final_general=final.general,
            final_icu=final.icu,
            final_discharged=final.discharged,
            final_deceased=final.deceased,
            mean_active_census=round(mean_census, 4),
            max_active_census=round(max_census, 4),
            max_abs_mbe=round(max_mbe, 6),
            reconciliation_issues=len(issues),
            event_quota_mismatches=event_mismatch,
            patient_invariant_critical=pv_critical,
            completed_full_horizon=run.completed_full_horizon,
            configuration_hash=config_hash,
        )

    # ------------------------------------------------------------------
    # Metrics helpers (mirrors pipeline.py)
    # ------------------------------------------------------------------

    @staticmethod
    def _max_abs_mbe(run) -> float:
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

    @staticmethod
    def _event_quota_mismatches(run) -> int:
        mismatches = 0
        for outcome in run.outcomes:
            ev = outcome.step_events
            transfer = sum(1 for e in ev if e.event_type == EVENT_TRANSFER)
            discharge = sum(1 for e in ev if e.event_type == EVENT_DISCHARGE)
            death = sum(1 for e in ev if e.event_type == EVENT_DEATH)
            realized = outcome.realized_flow
            rt = sum(realized.get(f, 0) for f in TRANSFER_NAMES)
            rd = sum(realized.get(f, 0) for f in ("T_EH", *DISCHARGE_FLOWS))
            rdm = sum(realized.get(f, 0) for f in DEATH_FLOWS)
            mismatches += int(transfer != rt) + int(discharge != rd) + int(death != rdm)
        return mismatches

    @staticmethod
    def _totals(run) -> Dict[str, int]:
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

    @staticmethod
    def _configuration_hash(effective: Configuration) -> str:
        from .scenarios import configuration_hash

        return configuration_hash(effective)

    # ------------------------------------------------------------------
    # Checkpoint / resume
    # ------------------------------------------------------------------

    def _checkpoint(self) -> None:
        payload = {
            "version": CHECKPOINT_VERSION,
            "batch_id": self._batch_id,
            "master_seed": self._master_seed,
            "target_patients": self._target,
            "planned_runs_per_scenario": self._planned,
            "schedule": list(self._schedule),
            "patient_chunk_rows": self._patient_chunk,
            "event_chunk_rows": self._event_chunk,
            "cumulative_patients": self._cumulative_patients,
            "cumulative_events": self._cumulative_events,
            "finished": self.finished,
            "updated_at": _utc_stamp(),
            "counters": {
                f"{prefix}|{scenario_id}": index
                for (prefix, scenario_id), index in sorted(self._counters.items())
            },
            "records": [r.to_dict() for r in self._records],
        }
        write_json(self._checkpoint_path, payload)

    def _load_checkpoint(self) -> None:
        if not self._checkpoint_path.is_file():
            self._counters = count_part_files(self._out_dir)
            return
        with self._checkpoint_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if payload.get("version") != CHECKPOINT_VERSION:
            raise BatchError(
                f"unsupported checkpoint version {payload.get('version')}"
            )
        if tuple(payload.get("schedule") or []) != self._schedule:
            raise BatchError(
                "existing checkpoint schedule differs from the requested schedule: "
                f"{payload.get('schedule')} vs {list(self._schedule)}"
            )
        if int(payload["master_seed"]) != self._master_seed:
            raise BatchError(
                "existing checkpoint master_seed differs: "
                f"{payload['master_seed']} vs {self._master_seed}"
            )
        self._batch_id = payload["batch_id"]
        self._records = [RunRecord.from_dict(r) for r in payload.get("records", [])]
        self._completed = {
            (r.scenario_id, r.run_index) for r in self._records
        }
        self._cumulative_patients = int(payload.get("cumulative_patients", 0))
        self._cumulative_events = int(payload.get("cumulative_events", 0))
        self.finished = bool(payload.get("finished", False))

        loaded = {
            tuple(item.split("|", 1)): int(index)
            for item, index in (payload.get("counters") or {}).items()
        }
        disk = count_part_files(self._out_dir)
        self._counters = {
            key: max(loaded.get(key, 0), disk.get(key, 0)) for key in loaded
        }
        for key, index in disk.items():
            self._counters.setdefault(key, index)

    # ------------------------------------------------------------------
    # Derived artifacts
    # ------------------------------------------------------------------

    def _used_configuration(self) -> Dict[str, Any]:
        overrides = {
            sid: self._manager.scenario_definition(sid) for sid in self._schedule
        }
        return {
            "base_configuration": self._config.data,
            "scenario_overrides": overrides,
            "batch": {
                "batch_id": self._batch_id,
                "target_patients": self._target,
                "planned_runs_per_scenario": self._planned,
                "schedule": list(self._schedule),
                "master_seed": self._master_seed,
                "patient_chunk_rows": self._patient_chunk,
                "event_chunk_rows": self._event_chunk,
            },
        }

    def build_summary_frame(self) -> pd.DataFrame:
        rows = [r.summary_row() for r in self._records]
        if not rows:
            return pd.DataFrame(columns=list(SUMMARY_COLUMNS))
        return pd.DataFrame(rows)[list(SUMMARY_COLUMNS)]

    def build_scenario_comparison(self) -> pd.DataFrame:
        rows = []
        for sid in self._schedule:
            runs = [r for r in self._records if r.scenario_id == sid]
            if not runs:
                continue
            rows.append(
                {
                    "scenario_id": sid,
                    "run_count": len(runs),
                    "total_patients": sum(r.patient_count for r in runs),
                    "total_events": sum(r.event_count for r in runs),
                    "total_arrivals": sum(r.total_arrivals for r in runs),
                    "total_transfers": sum(r.total_transfers for r in runs),
                    "total_discharges": sum(r.total_discharges for r in runs),
                    "total_deaths": sum(r.total_deaths for r in runs),
                    "final_discharged": sum(r.final_discharged for r in runs),
                    "final_deceased": sum(r.final_deceased for r in runs),
                    "mean_active_census": round(
                        np.mean([r.mean_active_census for r in runs]), 4
                    ),
                    "max_active_census": max(r.max_active_census for r in runs),
                    "max_abs_mbe": max(r.max_abs_mbe for r in runs),
                    "reconciliation_issues": sum(
                        r.reconciliation_issues for r in runs
                    ),
                    "event_quota_mismatches": sum(
                        r.event_quota_mismatches for r in runs
                    ),
                    "patient_invariant_critical": sum(
                        r.patient_invariant_critical for r in runs
                    ),
                    "configuration_hash": runs[0].configuration_hash,
                    "reference_child_seed": runs[0].child_seed,
                }
            )
        return pd.DataFrame(rows)

    def write_artifacts(self, validation_status: str = "VALIDATION") -> Dict[str, Any]:
        """Write derived artifact files and return the dataset manifest."""
        out = self._out_dir

        summary = self.build_summary_frame()
        pq.write_table(
            pa.Table.from_pandas(summary, preserve_index=False),
            out / "simulation_summary.parquet",
            compression="zstd",
        )

        comparison = self.build_scenario_comparison()
        write_csv(out / "scenario_comparison.csv", comparison)

        used = self._used_configuration()
        write_yaml(out / "used_configuration.yaml", used)
        config_hash = hash_yaml(used)

        import hfsg

        manifest = dataset_manifest(
            product_id=PRODUCT_ID,
            dataset_id=self.dataset_id(),
            dataset_version=DATASET_VERSION,
            engine_version=hfsg.__version__,
            scenario_pack=SCENARIO_PACK,
            patient_count=self._cumulative_patients,
            event_count=self._cumulative_events,
            configuration_hash=config_hash,
            validation_status=validation_status,
            license_id=LICENSE_ID,
        )
        manifest["target_patient_records"] = self._target
        manifest["production_target_notes"] = PRODUCTION_TARGET_NOTES
        write_json(out / "dataset_manifest.json", manifest)
        return manifest

    def dataset_id(self) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"HFSG-DS-STD8-2026-{stamp}"


# ----------------------------------------------------------------------
# Batch validation (memory bounded, reads part files one run at a time)
# ----------------------------------------------------------------------

def _list_part_files(root: Path, prefix: str) -> Dict[str, List[Path]]:
    base = root / prefix
    result: Dict[str, List[Path]] = {}
    for part_dir in sorted(base.glob("scenario_id=*")) if base.is_dir() else []:
        scenario_id = part_dir.name.split("=", 1)[1]
        result[scenario_id] = sorted(part_dir.glob("part-*.parquet"))
    return result


def _read_frame(path: Path) -> pd.DataFrame:
    return pq.read_table(path).to_pandas()


def _initial_conditions(used: Dict[str, Any], scenario_id: str) -> Dict[str, int]:
    base = used.get("base_configuration") or {}
    initial = dict(base.get("initial_conditions") or {})
    overrides = (used.get("scenario_overrides") or {}).get(scenario_id) or {}
    initial.update(
        {
            f"{unit}_census": val
            for unit, val in overrides.items()
            if f"{unit}_census" in overrides
        }
    )
    return {
        unit: int(initial.get(f"{unit}_census", 0)) for unit in INITIAL_UNITS
    }


def _initial_set(initial: Dict[str, int]) -> bool:
    return any(v > 0 for v in initial.values())


def _sum_realized(agg_df: pd.DataFrame, flow_names) -> int:
    cols = [f"{f}_realized" for f in flow_names if f"{f}_realized" in agg_df.columns]
    if not cols:
        return 0
    return int(agg_df[cols].sum().sum())


def _series_realized(agg_df: pd.DataFrame, flow_names):
    """Per-row realized flow sum (Series), or None if no flow columns."""
    cols = [f"{f}_realized" for f in flow_names if f"{f}_realized" in agg_df.columns]
    if not cols:
        return None
    return agg_df[cols].sum(axis=1)


def _capacity_source_violations(agg_df: pd.DataFrame, initial: Dict[str, int]) -> List[str]:
    violations: List[str] = []
    if agg_df.empty:
        return ["aggregate frame is empty"]
    for col in AGGREGATE_STOCK_COLUMNS:
        if col not in agg_df.columns:
            continue
        if agg_df[col].isna().any():
            violations.append(f"aggregate column {col} contains NaN")
        if pd.api.types.is_numeric_dtype(agg_df[col]) and (agg_df[col] < 0).any():
            violations.append(f"aggregate column {col} drops below zero")
    required_cols = TRANSFER_NAMES + ("T_EH", *DISCHARGE_FLOWS, *DEATH_FLOWS)
    realized_cols = [
        f"{f}_realized" for f in required_cols if f"{f}_realized" in agg_df.columns
    ]
    for col in realized_cols:
        if (agg_df[col] < 0).any():
            violations.append(f"realized flow {col} is negative")

    # Realized outflows from a unit must never exceed the stock available at
    # the beginning of the timestep (arrivals are not eligible in their own
    # timestep, MODEL.md section 12), so the inflow term is intentionally left
    # out here.
    if all(c in agg_df.columns for c in ("ed_census", "arrivals_accepted")):
        before_ed = agg_df["ed_census"].shift(1).fillna(float(initial["ed"]))
        out_ed = _series_realized(agg_df, TRANSFER_NAMES[:3] + ("T_EH",))
        if out_ed is not None and (out_ed > before_ed + 1e-9).any():
            violations.append("ED outflows exceed available ED source stock")
    for unit, census_col, out_flows in (
        ("specialty", "specialty_census", ("T_CG", "T_CI", "D_C", "M_C")),
        ("general", "general_census", ("T_GI", "D_G", "M_G")),
        ("icu", "icu_census", ("D_I", "M_I")),
    ):
        if census_col not in agg_df.columns:
            continue
        before = agg_df[census_col].shift(1).fillna(float(initial[unit]))
        out = _series_realized(agg_df, out_flows)
        if out is not None and (out > before + 1e-9).any():
            violations.append(f"{unit} outflows exceed available source stock")
    return violations


def validate_batch_outputs(
    out_dir: str | Path,
    *,
    schedule: Optional[Sequence[str]] = None,
    planned_runs_per_scenario: Optional[int] = None,
    target_patients: Optional[int] = None,
    master_seed: Optional[int] = None,
) -> Dict[str, Any]:
    """Validate a written Batch dataset in bounded memory.

    Reads the partitioned Parquet files one simulation run at a time and
    returns a validation report. A non-empty ``critical_failures`` list means
    the Dataset must not be released.
    """
    out_dir = Path(out_dir)
    checkpoint_path = out_dir / "batch_checkpoint.json"
    meta: Dict[str, Any] = {}
    if checkpoint_path.is_file():
        with checkpoint_path.open("r", encoding="utf-8") as handle:
            meta = json.load(handle)
    schedule = tuple(
        schedule if schedule is not None
        else (meta.get("schedule") or [])
    )
    target_patients = (
        int(target_patients) if target_patients is not None
        else int(meta.get("target_patients") or 0)
    )
    planned_runs = (
        int(planned_runs_per_scenario) if planned_runs_per_scenario is not None
        else int(meta.get("planned_runs_per_scenario") or 0)
    )
    master_seed = (
        int(master_seed) if master_seed is not None
        else int(meta.get("master_seed") or 0)
    )
    batch_id = meta.get("batch_id", "")

    used_yaml_path = out_dir / "used_configuration.yaml"
    used = {}
    if used_yaml_path.is_file():
        with used_yaml_path.open("r", encoding="utf-8") as handle:
            used = yaml.safe_load(handle)

    failures: List[str] = []
    checks: Dict[str, Any] = {}

    # -- scenario coverage + file presence --------------------------------
    patients = _list_part_files(out_dir, "patients")
    events = _list_part_files(out_dir, "patient_events")
    aggregates = _list_part_files(out_dir, "aggregate_timeseries")
    present = sorted(set(patients) | set(events) | set(aggregates))
    required = list(schedule) or present

    files_by_dataset = {
        "patients": patients,
        "patient_events": events,
        "aggregate_timeseries": aggregates,
    }
    for prefix, mapping in files_by_dataset.items():
        for sid in list(mapping):
            if not mapping[sid]:
                failures.append(f"{prefix}: scenario {sid} has no part files")
                del mapping[sid]

    missing_scenarios = [s for s in required if s not in present]
    if missing_scenarios:
        failures.append(f"missing scenario coverage: {missing_scenarios}")

    # -- per-run validation ------------------------------------------------
    total_patients = 0
    total_events = 0
    total_agg_rows = 0
    part_pairs = 0
    uniqueness_violations = 0
    temporal_violations = 0
    replay_violations = 0
    mbe_max = 0.0
    mbe_violations = 0
    quota_violations = 0
    capacity_violations = 0
    readability_failures: List[str] = []
    run_count_checks: List[str] = []

    summary_path = out_dir / "simulation_summary.parquet"
    summary_records: Dict[Tuple[str, int], Dict[str, Any]] = {}
    if summary_path.is_file():
        df = _read_frame(summary_path)
        for _, row in df.iterrows():
            key = (str(row["scenario_id"]), int(row["run_index"]))
            summary_records[key] = row.to_dict()

    run_counts: Dict[str, int] = {}
    for sid in sorted(present):
        p_files = patients.get(sid, [])
        e_files = events.get(sid, [])
        a_files = aggregates.get(sid, [])
        if not (len(p_files) == len(e_files) == len(a_files)):
            failures.append(
                f"scenario {sid}: part file counts differ "
                f"(patients={len(p_files)}, events={len(e_files)}, "
                f"aggregates={len(a_files)})"
            )
            continue
        expected = len(p_files)
        run_counts[sid] = expected
        if expected < 1:
            failures.append(f"scenario {sid}: no runs present")
        initial = _initial_conditions(used, sid) if used else {}

        for part_index in range(expected):
            p_path, e_path, a_path = (
                p_files[part_index],
                e_files[part_index],
                a_files[part_index],
            )
            part_pairs += 1
            try:
                p_df = _read_frame(p_path)
                e_df = _read_frame(e_path)
                a_df = _read_frame(a_path)
            except Exception as exc:  # noqa: BLE001
                readability_failures.append(
                    f"scenario {sid} part {part_index}: read failed: {exc}"
                )
                continue

            total_patients += len(p_df)
            total_events += len(e_df)
            total_agg_rows += len(a_df)

            sim_ids = set(p_df["simulation_id"]) if "simulation_id" in p_df else set()
            if len(sim_ids) != 1:
                readability_failures.append(
                    f"scenario {sid} part {part_index}: patient file has "
                    f"{len(sim_ids)} distinct simulation_ids"
                )
                continue
            sim_id = next(iter(sim_ids))
            if "simulation_id" in e_df and set(e_df["simulation_id"]) != sim_ids:
                readability_failures.append(
                    f"scenario {sid} part {part_index}: event file "
                    "simulation_id does not match patient file"
                )
            if "simulation_id" in a_df and set(a_df["simulation_id"]) != sim_ids:
                readability_failures.append(
                    f"scenario {sid} part {part_index}: aggregate file "
                    "simulation_id does not match patient file"
                )

            # post-serialization invariants (uniqueness + temporal).
            post = check_post_serialization(p_df, e_df)
            uniqueness_violations += sum(
                "duplicate" in v or "no events" in v for v in post
            )
            temporal_violations += sum(
                "chronolog" in v or "terminal" in v or "ARRIVAL" in v for v in post
            )
            for v in post:
                failures.append(f"{sid} run {part_index}: {v}")

            # aggregate <-> patient replay reconciliation (requires the
            # preserved initial conditions from used_configuration.yaml).
            if used and _initial_set(initial) and "simulation_id" in e_df and not e_df.empty:
                replay = replay_operational_stocks(
                    e_df, initial, sid, patients_df=p_df
                )
                replay_violations += len(match_aggregate_to_replay(a_df, replay, sid))
                for v in match_aggregate_to_replay(a_df, replay, sid):
                    failures.append(f"{sid} run {part_index}: {v}")

            # mass balance from the written aggregate frame.
            n0 = _n0_from_aggregate(a_df, initial)
            mb = _mass_balance(a_df, n0)
            if mb is not None:
                mbe_max = max(mbe_max, float(abs(mb).max()))
                mbe_violations += int((mb.abs() > 1e-6).sum())

            # capacity / source-stock invariants.
            if used and _initial_set(initial):
                cap = _capacity_source_violations(a_df, initial)
                capacity_violations += len(cap)
                for v in cap:
                    failures.append(f"{sid} run {part_index}: {v}")

            # event quota reconciliation (written counts vs aggregate realized).
            quota = _event_quota_from_frames(e_df, a_df)
            quota_violations += sum(quota.values())
            for label, mismatched in quota.items():
                if mismatched:
                    failures.append(
                        f"{sid} run {part_index}: event quota mismatch {label}"
                    )

            # cross-check with recorded summary rows.
            recorded = summary_records.get((sid, part_index))
            if recorded is not None:
                run_count_checks.append((sid, part_index))
                if int(recorded["total_patients"]) != len(p_df) or int(
                    recorded["total_events"]
                ) != len(e_df):
                    failures.append(
                        f"{sid} run {part_index}: summary counts differ from "
                        "written files"
                    )
                recorded_mbe = float(recorded["max_abs_mbe"])
                if mb is not None and abs(recorded_mbe - float(abs(mb).max())) > 1e-6:
                    failures.append(
                        f"{sid} run {part_index}: summary max_abs_mbe "
                        f"({recorded_mbe}) differs from recomputed "
                        f"({float(abs(mb).max())})"
                    )

    checks["parquet_readability"] = {
        "patients_files": sum(len(v) for v in patients.values()),
        "events_files": sum(len(v) for v in events.values()),
        "aggregate_files": sum(len(v) for v in aggregates.values()),
        "failures": readability_failures,
    }
    checks["part_pairs_checked"] = part_pairs
    checks["row_counts"] = {
        "patients": total_patients,
        "events": total_events,
        "aggregate_rows": total_agg_rows,
    }
    checks["scenario_coverage"] = {
        "required": required,
        "present": present,
        "missing": missing_scenarios,
    }
    if target_patients:
        checks["target_patients"] = {
            "required": target_patients,
            "achieved": total_patients,
            "met": total_patients >= target_patients,
        }
        if total_patients < target_patients:
            failures.append(
                f"patient target not met: {total_patients} < {target_patients}"
            )
    # Round-robin schedule invariant: every scenario ran the same number of
    # runs (the runner stops each round only when the patient target is met).
    if run_counts:
        distinct = set(run_counts.values())
        if len(distinct) > 1:
            failures.append(
                "run counts are not round-robin consistent across scenarios: "
                f"{run_counts}"
            )
    checks["runs"] = {
        "per_scenario_run_counts": run_counts,
        "total_runs": part_pairs,
        "planned_runs_per_scenario": planned_runs,
    }

    checks["uniqueness"] = {"total_violations": uniqueness_violations}
    checks["temporal_consistency"] = {"total_violations": temporal_violations}
    checks["aggregate_replay"] = {"total_violations": replay_violations}
    checks["mass_balance"] = {"max_abs_mbe": mbe_max, "violations": mbe_violations}
    checks["event_quota_reconciliation"] = {"total_violations": quota_violations}
    checks["capacity_source_invariants"] = {"total_violations": capacity_violations}
    checks["summary_alignment"] = {
        "run_count_checked": len(run_count_checks),
        "total_runs": part_pairs,
    }

    # -- manifest and configuration hash ----------------------------------
    manifest_status = {}
    manifest_path = out_dir / "dataset_manifest.json"
    if manifest_path.is_file():
        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        if int(manifest.get("patient_record_count", -1)) != total_patients:
            failures.append(
                "manifest patient_record_count does not match written files: "
                f"{manifest.get('patient_record_count')} vs {total_patients}"
            )
        if int(manifest.get("patient_event_count", -1)) != total_events:
            failures.append(
                "manifest patient_event_count does not match written files: "
                f"{manifest.get('patient_event_count')} vs {total_events}"
            )
        recomputed_hash = hash_yaml(used) if used else None
        manifest_status = {
            "dataset_id": manifest.get("dataset_id"),
            "patient_record_count": manifest.get("patient_record_count"),
            "patient_event_count": manifest.get("patient_event_count"),
            "configuration_hash": manifest.get("configuration_hash"),
            "recomputed_configuration_hash": recomputed_hash,
            "configuration_hash_match": bool(
                recomputed_hash
                and manifest.get("configuration_hash") == recomputed_hash
            ),
            "validation_status": manifest.get("validation_status"),
            "license_id": manifest.get("license_id"),
        }
        if recomputed_hash and manifest.get("configuration_hash") != recomputed_hash:
            failures.append(
                "manifest configuration_hash does not match the re-hash of "
                "used_configuration.yaml"
            )
    checks["manifest"] = manifest_status

    # -- reproducibility sample (run_index 0 of every scenario) ------------
    repro = _reproducibility_sample(out_dir, used, schedule or present, master_seed)
    checks["reproducibility"] = repro
    if repro["failures"]:
        for f in repro["failures"]:
            failures.append(f"reproducibility: {f}")

    # -- decisive flags -----------------------------------------------------
    decision_required: List[str] = []
    spec_conflict: List[str] = []

    # License ID HFSG-EULA-1.0 was approved by the Project Owner, so it is no
    # longer a required pipeline decision.
    reported_license = manifest_status.get("license_id")
    if reported_license != LICENSE_ID:
        decision_required.append("LICENSE_ID_VALUE")

    validation_status = "VALIDATED" if not failures else "FAILED"

    return {
        "batch_id": batch_id,
        "master_seed": master_seed,
        "schedule": list(schedule or present),
        "target_patient_records": target_patients,
        "production_target_notes": PRODUCTION_TARGET_NOTES,
        "validation_status": validation_status,
        "critical_failures": failures,
        "warnings": [],
        "decision_required": decision_required,
        "spec_conflict": spec_conflict,
        "checks": checks,
    }


def _n0_from_aggregate(agg_df: pd.DataFrame, initial: Dict[str, int]) -> Optional[int]:
    """Derive the initial population size n0 from the written aggregate frame.

    The hour-0 row is the state *after* processing hour 0. The engine mass
    balance identity is total_h = n0 + cumulative_arrivals_h for every hour,
    so n0 = total_0 - cumulative_arrivals_0.
    """
    if agg_df.empty:
        return None
    cols = ["ed_census", "specialty_census", "general_census", "icu_census",
            "discharged", "deceased", "cumulative_arrivals"]
    if not all(c in agg_df.columns for c in cols):
        return None
    first = agg_df.iloc[0]
    total_0 = sum(int(first[c]) for c in cols[:-1])
    n0 = total_0 - int(first["cumulative_arrivals"])
    return n0 if n0 else None


def _mass_balance(agg_df: pd.DataFrame, n0: Optional[int]):
    """Return the per-hour mass balance Series for one run, or None."""
    if n0 is None or agg_df.empty:
        return None
    cols = ["ed_census", "specialty_census", "general_census", "icu_census",
            "discharged", "deceased", "cumulative_arrivals"]
    if not all(c in agg_df.columns for c in cols):
        return None
    total = agg_df[["ed_census", "specialty_census", "general_census", "icu_census",
                    "discharged", "deceased"]].sum(axis=1)
    expected = float(n0) + agg_df["cumulative_arrivals"]
    return (total - expected).abs()


def _event_quota_from_frames(e_df: pd.DataFrame, a_df: pd.DataFrame) -> Dict[str, int]:
    transfers = int((e_df["event_type"] == EVENT_TRANSFER).sum()) if "event_type" in e_df else 0
    discharges = int((e_df["event_type"] == EVENT_DISCHARGE).sum()) if "event_type" in e_df else 0
    deaths = int((e_df["event_type"] == EVENT_DEATH).sum()) if "event_type" in e_df else 0
    rt = _sum_realized(a_df, TRANSFER_NAMES)
    rd = _sum_realized(a_df, ("T_EH", *DISCHARGE_FLOWS))
    rdm = _sum_realized(a_df, DEATH_FLOWS)
    return {
        "transfers": int(transfers != rt),
        "discharges": int(discharges != rd),
        "deaths": int(deaths != rdm),
    }


def _reproducibility_sample(
    out_dir: Path, used: Dict[str, Any], scenarios: Sequence[str], master_seed: int
) -> Dict[str, Any]:
    """Re-run run_index 0 of every scenario and compare patient/event IDs with
    the written part file for that run."""
    failures: List[str] = []
    checked = 0
    if not used or not master_seed:
        return {
            "checked_runs": checked,
            "failures": ["used configuration or master seed unavailable"],
        }
    base = used.get("base_configuration") or {}
    loader = ConfigurationLoader()
    config = loader.from_data(base, source="used_configuration")

    manager = ScenarioManager(config)
    for sid in scenarios:
        patients_dir = out_dir / "patients" / f"scenario_id={sid}"
        if not patients_dir.is_dir():
            failures.append(f"{sid}: no patient partition to compare against")
            continue
        first_part = sorted(patients_dir.glob("part-*.parquet"))
        if not first_part:
            failures.append(f"{sid}: no patient part files to compare against")
            continue
        written = _read_frame(first_part[0])

        effective = manager.effective_configuration(sid)
        child_seed = derive_child_seed(master_seed, sid, 0)
        ctx = SimulationContext(
            scenario_id=sid,
            run_index=0,
            master_seed=master_seed,
            child_seed=child_seed,
            model_version=str(effective.version),
            configuration_version=str(effective.version),
        )
        driver = SimulationDriver(
            effective,
            ctx,
            rng=np.random.default_rng(child_seed),
            patient_rng=np.random.default_rng(child_seed),
        )
        run = driver.run()

        written_ids = [str(x) for x in written["patient_id"]]
        rerun_ids = [str(p.patient_id) for p in run.patients]
        checked += 1
        if written_ids != rerun_ids:
            failures.append(
                f"{sid}: run_index 0 patient_id sequence differs from re-run"
            )

        events_dir = out_dir / "patient_events" / f"scenario_id={sid}"
        if events_dir.is_dir():
            e_part = sorted(events_dir.glob("part-*.parquet"))
            if e_part:
                written_events = _read_frame(e_part[0])
                written_event_ids = [str(x) for x in written_events["event_id"]]
                rerun_event_ids = [str(e.event_id) for e in run.events]
                if written_event_ids != rerun_event_ids:
                    failures.append(
                        f"{sid}: run_index 0 event_id sequence differs from re-run"
                    )
    return {"checked_runs": checked, "failures": failures}