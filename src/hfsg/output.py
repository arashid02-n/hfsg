"""Output pipeline (Step 8).

Implements the approved outputs with chunked, scenario_id-partitioned Parquet
(ZSTD) writers, plus round-trip readers used for post-serialization
validation and manifest reconciliation.

The complete Dataset is never held in RAM: each scenario run produces its own
patient/event frames which are streamed to a partition via
``pyarrow.parquet.write_to_dataset``.

Schemas follow the approved patient/event models and the aggregate Model B
flow chain (requested -> constrained -> realized integer flow).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from .events import (
    EVENT_ARRIVAL,
    EVENT_DEATH,
    EVENT_DISCHARGE,
    EVENT_TRANSFER,
    PatientEvent,
)
from .patients import Patient
from .simulation import StepOutcome
from .units import DEATH_FLOWS, DISCHARGE_FLOWS, FLOW_NAMES, TRANSFER_NAMES, TRANSFERS


class OutputError(RuntimeError):
    """Raised when an output cannot be written or read back correctly."""


# ----------------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------------

PATIENT_COLUMNS = (
    "simulation_id",
    "scenario_id",
    "patient_id",
    "arrival_datetime",
    "entry_type",
    "initial_unit",
    "age_group",
    "sex",
    "severity_level",
    "arrival_mode",
)

EVENT_COLUMNS = (
    "simulation_id",
    "scenario_id",
    "patient_id",
    "event_id",
    "event_datetime",
    "event_hour",
    "event_type",
    "from_unit",
    "to_unit",
    "quota_flow",
)

AGGREGATE_STOCK_COLUMNS = (
    "simulation_id",
    "scenario_id",
    "hour",
    "ed_census",
    "specialty_census",
    "general_census",
    "icu_census",
    "discharged",
    "deceased",
    "cumulative_arrivals",
)

SUMMARY_COLUMNS = (
    "simulation_id",
    "scenario_id",
    "run_index",
    "master_seed",
    "child_seed",
    "total_patients",
    "total_events",
    "total_arrivals",
    "total_transfers",
    "total_discharges",
    "total_deaths",
    "final_ed",
    "final_specialty",
    "final_general",
    "final_icu",
    "final_discharged",
    "final_deceased",
    "mean_active_census",
    "max_active_census",
    "max_abs_mbe",
    "reconciliation_issues",
    "configuration_hash",
)


# ----------------------------------------------------------------------
# Per-scenario frame builders
# ----------------------------------------------------------------------

def patients_frame(
    simulation_id: str, scenario_id: str, patients: Iterable[Patient]
) -> pd.DataFrame:
    rows = []
    for p in patients:
        rows.append(
            {
                "simulation_id": p.simulation_id,
                "scenario_id": p.scenario_id,
                "patient_id": p.patient_id,
                "arrival_datetime": p.arrival_datetime,
                "entry_type": p.entry_type,
                "initial_unit": p.initial_unit,
                "age_group": p.age_group,
                "sex": p.sex,
                "severity_level": p.severity_level,
                "arrival_mode": p.arrival_mode,
            }
        )
    return pd.DataFrame(rows, columns=PATIENT_COLUMNS)


def events_frame(
    simulation_id: str, scenario_id: str, events: Iterable[PatientEvent]
) -> pd.DataFrame:
    rows = []
    for ev in events:
        rows.append(
            {
                "simulation_id": ev.simulation_id,
                "scenario_id": ev.scenario_id,
                "patient_id": ev.patient_id,
                "event_id": ev.event_id,
                "event_datetime": ev.event_datetime,
                "event_hour": ev.event_hour,
                "event_type": ev.event_type,
                "from_unit": ev.from_unit,
                "to_unit": ev.to_unit,
                "quota_flow": ev.quota_flow,
            }
        )
    return pd.DataFrame(rows, columns=EVENT_COLUMNS)


def aggregate_frame(
    simulation_id: str, scenario_id: str, outcomes: Iterable[StepOutcome]
) -> pd.DataFrame:
    stock_rows = []
    flow_rows = []
    for out in outcomes:
        after = out.after
        stock_rows.append(
            {
                "simulation_id": simulation_id,
                "scenario_id": scenario_id,
                "hour": out.hour,
                "ed_census": after.ed,
                "specialty_census": after.specialty,
                "general_census": after.general,
                "icu_census": after.icu,
                "discharged": after.discharged,
                "deceased": after.deceased,
                "cumulative_arrivals": after.cumulative_arrivals,
            }
        )
        row = {
            "hour": out.hour,
            "arrivals_drawn": out.arrivals_drawn,
            "arrivals_accepted": out.arrivals_accepted,
            "unmet_arrivals": out.unmet_arrivals,
        }
        for f in FLOW_NAMES:
            row[f"{f}_realized"] = out.realized_flow.get(f, 0)
            row[f"{f}_constrained"] = out.constrained_raw.get(f, 0.0)
            row[f"{f}_requested"] = out.requested_raw.get(f, 0.0)
            row[f"{f}_integerization_difference"] = out.integerization_difference.get(
                f, 0.0
            )
        flow_rows.append(row)
    stocks = pd.DataFrame(stock_rows, columns=AGGREGATE_STOCK_COLUMNS)
    flows = pd.DataFrame(flow_rows)
    merged = stocks.merge(flows, on="hour", how="left")
    return merged


def summary_frame(row: Dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame([row])[list(SUMMARY_COLUMNS)]


# ----------------------------------------------------------------------
# Partitioned ZSTD Parquet writer / reader
# ----------------------------------------------------------------------

def write_partitioned(
    root: Path,
    prefix: str,
    scenario_frames: List[tuple],
    chunk_rows: int,
) -> Dict[str, int]:
    """Write per-scenario frames into a scenario_id-partitioned layout.

    Each scenario's rows are written in chunks of ``chunk_rows`` rows into a
    ``scenario_id=<id>/`` directory, compressed with ZSTD. Returns a dict
    mapping scenario_id -> number of rows actually written.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    per_scenario: Dict[str, List[pd.DataFrame]] = {}
    for scenario_id, frame in scenario_frames:
        if frame is None or len(frame) == 0:
            continue
        per_scenario.setdefault(scenario_id, []).append(frame)

    counts: Dict[str, int] = {}
    for scenario_id, frames in per_scenario.items():
        part_dir = root / f"scenario_id={scenario_id}"
        part_dir.mkdir(parents=True, exist_ok=True)
        n = 0
        part = 0
        for frame in frames:
            for i in range(0, len(frame), chunk_rows):
                chunk = frame.iloc[i : i + chunk_rows]
                table = pa.Table.from_pandas(chunk, preserve_index=False)
                pq.write_table(
                    table, part_dir / f"part-{part}.parquet", compression="zstd"
                )
                n += len(chunk)
                part += 1
        counts[scenario_id] = n
    return counts


def read_partitioned(root: Path) -> pd.DataFrame:
    """Read back all scenario_id partitions into one DataFrame."""
    root = Path(root)
    tables = []
    for part_dir in sorted(root.glob("scenario_id=*")):
        for parquet_file in sorted(part_dir.glob("*.parquet")):
            tables.append(pq.read_table(parquet_file))
    if not tables:
        return pd.DataFrame()
    return pd.concat([t.to_pandas() for t in tables], ignore_index=True)


def count_part_files(root: Path) -> Dict[tuple, int]:
    """Return the next part index for each (prefix, scenario_id) on disk.

    Used to resume a Batch without overwriting existing partitions: for every
    ``<prefix>/scenario_id=<id>/part-*.parquet`` file the next index is the
    maximum part index plus one.
    """
    root = Path(root)
    counters: Dict[tuple, int] = {}
    for prefix_dir in sorted(root.iterdir()):
        if not prefix_dir.is_dir():
            continue
        prefix = prefix_dir.name
        for part_dir in sorted(prefix_dir.glob("scenario_id=*")):
            scenario_id = part_dir.name.split("=", 1)[1]
            indices = []
            for parquet_file in part_dir.glob("part-*.parquet"):
                name = parquet_file.name
                try:
                    indices.append(int(name[len("part-") : -len(".parquet")]))
                except ValueError:
                    continue
            if indices:
                counters[(prefix, scenario_id)] = max(indices) + 1
    return counters


def write_partition_append(
    root: Path,
    prefix: str,
    scenario_id: str,
    frame: pd.DataFrame,
    chunk_rows: int,
    counters: Dict[tuple, int],
) -> int:
    """Append one scenario frame to its partition, continuing part numbering.

    ``counters`` maps ``(prefix, scenario_id)`` -> next part index and is
    updated in place. Each part file is written with ZSTD compression. Rows
    for one run are always written as whole parts so a part file corresponds
    to exactly one simulation run (row counts stay below the chunk threshold).
    """
    if frame is None or len(frame) == 0:
        return 0
    root = Path(root)
    part_dir = root / prefix / f"scenario_id={scenario_id}"
    part_dir.mkdir(parents=True, exist_ok=True)
    index = counters.get((prefix, scenario_id), 0)
    written = 0
    for start in range(0, len(frame), chunk_rows):
        chunk = frame.iloc[start : start + chunk_rows]
        pq.write_table(
            pa.Table.from_pandas(chunk, preserve_index=False),
            part_dir / f"part-{index:04d}.parquet",
            compression="zstd",
        )
        written += len(chunk)
        index += 1
    counters[(prefix, scenario_id)] = index
    return written


def write_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


# ----------------------------------------------------------------------
# Post-serialization validation helpers
# ----------------------------------------------------------------------

def _event_type_counts(events_df: pd.DataFrame, flow: str, quota_flow_col="quota_flow") -> int:
    return int((events_df[quota_flow_col] == flow).sum())


def check_post_serialization(patients_df, events_df) -> List[str]:
    """Return a list of invariant violations found after read-back.

    Checks enforce uniqueness/temporal consistency *within each simulation run*
    (keyed on simulation_id when present, else scenario_id), so that
    patient/event IDs that restart per run and per scenario are not falsely
    flagged.
    Checks:
      - unique (simulation_id, patient_id) and (simulation_id, event_id)
      - chronological events per patient within a run
      - first event is an ARRIVAL for every patient
      - no post-terminal events within a run
    """
    violations: List[str] = []

    # Uniqueness is enforced per simulation run (patient/event IDs restart for
    # every run and scenario), so the composite key must include simulation_id
    # when present; scenario_id only suffices for single-run-per-scenario data.
    if "simulation_id" in patients_df.columns:
        patient_key = ["simulation_id", "patient_id"]
    elif "scenario_id" in patients_df.columns:
        patient_key = ["scenario_id", "patient_id"]
    else:
        patient_key = ["patient_id"]
    if "simulation_id" in events_df.columns:
        event_key = ["simulation_id", "event_id"]
    elif "scenario_id" in events_df.columns:
        event_key = ["scenario_id", "event_id"]
    else:
        event_key = ["event_id"]

    if patients_df.duplicated(subset=patient_key).any():
        violations.append("duplicate patient_id within a simulation run in patients.parquet")
    if events_df.duplicated(subset=event_key).any():
        violations.append("duplicate event_id within a simulation run in patient_events.parquet")

    key_cols = patient_key
    per_patient = {}
    for _, ev in events_df.iterrows():
        key = tuple(ev[c] for c in key_cols)
        per_patient.setdefault(key, []).append(ev)

    for pid, evlist in per_patient.items():
        evlist = sorted(evlist, key=lambda e: e["event_hour"])
        hours = [e["event_hour"] for e in evlist]
        if hours != sorted(hours):
            violations.append(f"{pid} events not chronological")
        kinds = [e["event_type"] for e in evlist]
        if not kinds or kinds[0] != EVENT_ARRIVAL:
            violations.append(f"{pid} first event is not ARRIVAL")
        terminal_idx = None
        for idx, ev in enumerate(evlist):
            if ev["event_type"] in (EVENT_DISCHARGE, EVENT_DEATH):
                terminal_idx = idx
                break
        if terminal_idx is not None and terminal_idx != len(evlist) - 1:
            violations.append(f"{pid} has events after terminal event")

    # Every patient must appear in the events stream.
    if all(col in patients_df.columns for col in key_cols):
        patient_keys = set(
            tuple(row[c] for c in key_cols)
            for _, row in patients_df.iterrows()
        )
        event_keys = set(per_patient.keys())
        missing_arrivals = patient_keys - event_keys
        # Only flag patients that should have an ARRIVAL: those in the events.
        for key in sorted(missing_arrivals):
            violations.append(f"patient {key} has no events")

    return violations


def replay_operational_stocks(
    events_df: pd.DataFrame,
    initial: Dict[str, int],
    scenario_id: str,
    patients_df: pd.DataFrame = None,
) -> pd.DataFrame:
    """Reconstruct per-unit operational integer stocks from one scenario's events.

    The aggregate operational stocks count the initial population from the
    initial conditions and add only *admitted* arrivals. Because the events
    stream contains an ARRIVAL event for every initial patient too (at hour 0),
    those ARRIVAL events are NOT added here (the initial stock already includes
    the population). ``patients_df`` supplies the entry_type per patient.

    Returns a DataFrame with columns hour, ed_census, specialty_census,
    general_census, icu_census, discharged, deceased, cumulative_arrivals.
    """
    if "scenario_id" in events_df.columns:
        events_df = events_df[events_df["scenario_id"] == scenario_id]

    # Determine which patients are admitted arrivals (vs initial population).
    if patients_df is not None and not patients_df.empty:
        if "scenario_id" in patients_df.columns:
            pdf = patients_df[patients_df["scenario_id"] == scenario_id]
        else:
            pdf = patients_df
        if "entry_type" in pdf.columns:
            arrival_patients = set(
                int(pid)
                for pid, et in zip(pdf["patient_id"], pdf["entry_type"])
                if et == "ARRIVAL"
            )
        else:
            arrival_patients = None
    else:
        arrival_patients = None

    stock = {
        "ed": int(initial.get("ed", 0)),
        "specialty": int(initial.get("specialty", 0)),
        "general": int(initial.get("general", 0)),
        "icu": int(initial.get("icu", 0)),
    }
    discharged = 0
    deceased = 0
    arrivals = 0

    rows = []
    cols = ["hour", "ed_census", "specialty_census", "general_census", "icu_census", "discharged", "deceased", "cumulative_arrivals"]
    if events_df.empty:
        return pd.DataFrame(columns=cols)

    step_order = {
        EVENT_ARRIVAL: 0,
        EVENT_TRANSFER: 1,
        EVENT_DISCHARGE: 2,
        EVENT_DEATH: 3,
    }
    hours = sorted(events_df["event_hour"].unique().tolist())
    for h in hours:
        step = events_df[events_df["event_hour"] == h].sort_values(
            "event_type", key=lambda s: s.map(step_order)
        )
        for _, ev in step.iterrows():
            et = ev["event_type"]
            if et == EVENT_ARRIVAL:
                # Do not double-count the initial population.
                if arrival_patients is not None:
                    if int(ev["patient_id"]) not in arrival_patients:
                        continue
                stock[ev["to_unit"]] += 1
                arrivals += 1
            elif et == EVENT_TRANSFER:
                stock[ev["from_unit"]] -= 1
                stock[ev["to_unit"]] += 1
            elif et == EVENT_DISCHARGE:
                stock[ev["from_unit"]] -= 1
                discharged += 1
            elif et == EVENT_DEATH:
                stock[ev["from_unit"]] -= 1
                deceased += 1
        rows.append(
            {
                "hour": h,
                "ed_census": stock["ed"],
                "specialty_census": stock["specialty"],
                "general_census": stock["general"],
                "icu_census": stock["icu"],
                "discharged": discharged,
                "deceased": deceased,
                "cumulative_arrivals": arrivals,
            }
        )
    return pd.DataFrame(rows)


def match_aggregate_to_replay(aggregate_df, replay_df, scenario_id: str = None) -> List[str]:
    """Compare one scenario's written aggregate frame to its replayed stocks.

    Only rows for ``scenario_id`` are compared. Returns invariant violations.
    """
    violations: List[str] = []
    if replay_df.empty:
        return violations
    if "scenario_id" in aggregate_df.columns and scenario_id is not None:
        agg = aggregate_df[aggregate_df["scenario_id"] == scenario_id]
    else:
        agg = aggregate_df

    cols = [
        "ed_census",
        "specialty_census",
        "general_census",
        "icu_census",
        "discharged",
        "deceased",
        "cumulative_arrivals",
    ]
    if "hour" not in agg.columns or "hour" not in replay_df.columns:
        return ["aggregate frame missing hour column"]
    agg = agg[["hour"] + cols].drop_duplicates("hour")
    replay = replay_df[["hour"] + cols]
    merged = agg.merge(replay, on="hour", suffixes=("_agg", "_replay"))
    if len(merged) != len(replay):
        return ["aggregate hour range differs from replay hour range"]
    for col in cols:
        diff = (merged[f"{col}_agg"] - merged[f"{col}_replay"]).abs()
        if (diff > 0).any():
            violations.append(
                f"aggregate vs replay mismatch on {col}: max {int(diff.max())}"
            )
    return violations


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def dataset_manifest(
    *,
    product_id: str,
    dataset_id: str,
    dataset_version: str,
    engine_version: str,
    scenario_pack: str,
    patient_count: int,
    event_count: int,
    configuration_hash: str,
    validation_status: str,
    license_id: str,
) -> Dict[str, Any]:
    return {
        "product_id": product_id,
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "engine_version": engine_version,
        "scenario_pack": scenario_pack,
        "patient_record_count": patient_count,
        "patient_event_count": event_count,
        "generation_timestamp": datetime.now(timezone.utc).isoformat(),
        "data_type": "simulated_patient_event_data",
        "configuration_hash": configuration_hash,
        "validation_status": validation_status,
        "license_id": license_id,
        "status": "VALIDATION",
    }
