"""Simulation execution identity.

Implements the Simulation Context component from ARCHITECTURE.md section 3.3.
Volatile fields (simulation_id, created_at) are operational metadata and MUST
be excluded or normalized in reproducibility comparisons (MODEL.md section 28).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _new_simulation_id() -> str:
    return uuid.uuid4().hex


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class SimulationContext:
    """Stable execution identity for one simulation run."""

    scenario_id: str
    run_index: int
    master_seed: int
    child_seed: int
    model_version: str
    configuration_version: str
    simulation_id: str = field(default_factory=_new_simulation_id)
    created_at: str = field(default_factory=_utc_now_iso)


def build_context(
    config,
    scenario_id: str = "S1",
    run_index: int = 0,
) -> SimulationContext:
    """Build a context with the child seed derived per MODEL.md section 27."""
    from .seeds import derive_child_seed

    master_seed = int(config.reproducibility["master_seed"])
    return SimulationContext(
        scenario_id=scenario_id,
        run_index=run_index,
        master_seed=master_seed,
        child_seed=derive_child_seed(master_seed, scenario_id, run_index),
        model_version=str(config.version),
        configuration_version=str(config.version),
    )
