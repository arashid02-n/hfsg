"""Integer Flow Allocation (MODEL.md section 14).

Converts raw constrained aggregate flows into integer patient quotas using
the approved Largest Remainder Method with seeded deterministic
tie-breaking.

Scope: patient-level events require integer movement counts, but raw
aggregate flows are fractional. The allocator operates per source unit over
the competing outflows of that unit, preserving the source-stock limit, and
applies a destination-capacity guard for ICU inflows in the approved
priority order (MODEL.md section 8).

The allocator MUST NOT modify model parameters, scenario parameters,
patient-selection rules or model structure. It only determines HOW MANY
patients move; the Patient Event Generator determines WHICH patients move
(MODEL.md section 15).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np

from .units import (
    UNIT_TO_STOCK_FIELD,
)


@dataclass(frozen=True)
class AllocationGroup:
    """One source unit and its competing outflows."""

    source: str
    flows: tuple  # flow names ordered for deterministic allocation


# Competing outflows per source unit. ``flows`` order is stable and is used
# to seed the deterministic tie-break consistently.
SOURCE_GROUPS: tuple = (
    AllocationGroup(
        "ed",
        ("T_EC", "T_EG", "T_EI", "T_EH"),
    ),
    AllocationGroup(
        "specialty",
        ("T_CG", "T_CI", "D_C", "M_C"),
    ),
    AllocationGroup(
        "general",
        ("T_GI", "D_G", "M_G"),
    ),
    AllocationGroup(
        "icu",
        ("D_I", "M_I"),
    ),
)

# ICU inflows in the approved priority order (ED -> ICU, Specialty -> ICU,
# General Ward -> ICU) for the destination-capacity guard.
ICU_INFLOWS = ("T_EI", "T_CI", "T_GI")


@dataclass(frozen=True)
class QuotaResult:
    """Result of integerizing one timestep's constrained flows."""

    hour: int
    # flow name -> integer patient quota
    quotas: Dict[str, int]
    # flow name -> raw constrained flow (for diagnostics, MODEL.md 14.9)
    raw: Dict[str, float]
    # flow name -> quota - raw (MODEL.md section 23)
    differences: Dict[str, float]
    # sum of integer outflows per source unit
    integer_outflow: Dict[str, int] = field(default_factory=dict)

    def quota(self, name: str) -> int:
        return self.quotas[name]


class IntegerFlowAllocator:
    """Largest Remainder Method with seeded deterministic tie-breaking."""

    def __init__(
        self,
        config,
        seed: int | None = None,
        rng: np.random.Generator | None = None,
    ) -> None:
        self._config = config
        self._seed = seed
        self._rng = rng
        self._tie_rng = rng
        if self.tie_rng is None:
            self._tie_rng = np.random.default_rng(seed)

    @property
    def rng(self) -> np.random.Generator | None:
        return self._rng

    @property
    def tie_rng(self) -> np.random.Generator:
        return self._tie_rng

    def allocate(
        self, hour: int, before_state, constrained: Dict[str, float]
    ) -> QuotaResult:
        """Integerize one timestep's constrained flows.

        ``before_state`` provides the beginning-of-step stocks used to cap
        integer outflow at the integer source stock (MODEL.md section 14.7
        and the source-stock guard).
        """
        quotas: Dict[str, float | int] = {}
        differences: Dict[str, float] = {}
        integer_outflow: Dict[str, int] = {}

        for group in SOURCE_GROUPS:
            source = group.source
            raw_flows = {
                name: float(constrained[name]) for name in group.flows
            }
            source_stock = float(getattr(before_state, UNIT_TO_STOCK_FIELD[source]))
            pool = self._allocate_group(raw_flows, source_stock)
            for name, quota in pool.items():
                quotas[name] = quota
                differences[name] = quota - raw_flows[name]
            integer_outflow[source] = sum(pool.values())

        integer = {k: int(v) for k, v in quotas.items()}

        # ICU destination-capacity guard in approved priority order.
        self._guard_icu_capacity(before_state, integer, constrained)

        # Recompute differences and integer outflow after the ICU guard.
        for name, value in integer.items():
            differences[name] = value - constrained[name]

        return QuotaResult(
            hour=hour,
            quotas=integer,
            raw={k: float(v) for k, v in constrained.items()},
            differences=differences,
            integer_outflow=integer_outflow,
        )

    # ------------------------------------------------------------------
    # Largest Remainder Method over one source-unit group
    # ------------------------------------------------------------------

    def _allocate_group(
        self, raw_flows: Dict[str, float], source_stock: float
    ) -> Dict[str, int]:
        names = list(raw_flows.keys())
        values = [max(0.0, raw_flows[n]) for n in names]

        total_raw = sum(values)
        quotas = [0 for _ in names]

        if total_raw <= 0.0:
            return {n: 0 for n in names}

        # Total integer outflow: nearest integer to total_raw, capped at the
        # integer source stock (never exceed available patients).
        source_floor = int(
            np.floor(max(0.0, source_stock))
        )
        total_quota = int(round(total_raw))
        if total_quota > source_floor:
            total_quota = max(0, source_floor)

        # Initial allocation: integer floors.
        floors = [int(np.floor(v)) for v in values]
        allocated = sum(floors)
        quotas = list(floors)
        remaining = total_quota - allocated

        if remaining <= 0:
            return {n: quotas[i] for i, n in enumerate(names)}

        # Rank fractional remainders from largest to smallest.
        remainders = [(v - np.floor(v), i) for i, v in enumerate(values)]
        # Precompute one seeded tie value per flow so the tie-break draws a
        # fixed number of RNG values regardless of sort internals (MODEL.md
        # section 28 reproducibility).
        tie = self._tie_values(len(names))
        # Largest remainder first; seeded tie-break for exact ties.
        remainders.sort(key=lambda rir: (-rir[0], tie[rir[1]], rir[1]))

        for _ in range(remaining):
            if not remainders:
                break
            _, idx = remainders.pop(0)
            quotas[idx] += 1

        return {n: quotas[i] for i, n in enumerate(names)}

    def _tie_values(self, n: int) -> List[float]:
        """Seeded deterministic tie-rank values (MODEL.md sections 14.6, 28).

        Draws exactly ``n`` values from the seeded RNG so the outcome is
        reproducible regardless of sort key-evaluation order.
        """
        if self.tie_rng is None:
            return [float(i) for i in range(n)]
        stream = self.tie_rng.uniform(size=n)
        return [float(v) for v in stream]

    def _guard_icu_capacity(
        self,
        before_state,
        integer: Dict[str, int],
        constrained: Dict[str, float],
    ) -> None:
        """Enforce destination-capacity limits for ICU inflows.

        ICU inflows are capped in the approved priority order so that the
        integer quota does not exceed the ICU capacity available at
        beginning-of-step occupancy (MODEL.md section 11 and section 8).
        """
        icu_capacity = float(self._config.capacities["icu"])
        icu_before = float(getattr(before_state, "icu_census"))
        available = max(0.0, icu_capacity - icu_before)
        remaining = available

        for name in ICU_INFLOWS:
            quota = integer.get(name, 0)
            if quota > remaining + 1e-9:
                reduced = int(np.floor(remaining))
                if reduced < 0:
                    reduced = 0
                integer[name] = reduced
                remaining = max(0.0, remaining - reduced)
            else:
                remaining -= quota
