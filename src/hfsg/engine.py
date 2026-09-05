"""HFSG Aggregate Flow Engine — Model B (MODEL.md sections 4-18).

Implements the aggregate compartment simulation only. Patient-level
generation, patient selection and integer quota allocation are NOT part of
this component (Phase 1 implementation order: Steps 6-7).

Timestep semantics (MODEL.md section 16):
    1. read beginning-of-step stocks;
    2. draw Poisson arrivals for the step;
    3. calculate requested flows from beginning-of-step stocks;
    4. apply source-stock constraints;
    5. apply destination-capacity constraints using beginning-of-step
       occupancy (capacity released during step t is available at t+1);
    6. compute discharge/death flows;
    7. update ALL stocks simultaneously.

Raw constrained flows are recorded for later integerization diagnostics
(MODEL.md section 14). All parameters come from the approved configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from .units import (
    ACTIVE_UNITS,
    DEATH_FLOWS,
    DISCHARGE_FLOWS,
    EXIT_FLOWS,
    FLOW_NAMES,
    TRANSFERS,
    UNIT_TO_STOCK_FIELD,
)
from .validation import AggregateValidator

_FLOAT_EPS = 1e-9


class AggregateEngineError(ValueError):
    """Raised when a run cannot proceed without violating MODEL.md."""


@dataclass(frozen=True)
class StateSnapshot:
    """Beginning-of-step or end-of-step aggregate state."""

    hour: int
    ed_census: float
    specialty_census: float
    general_census: float
    icu_census: float
    cumulative_discharges: float
    cumulative_deaths: float
    cumulative_arrivals: int

    def stock(self, unit: str) -> float:
        return getattr(self, UNIT_TO_STOCK_FIELD[unit])

    @property
    def active_total(self) -> float:
        return sum(self.stock(u) for u in ACTIVE_UNITS)

    @property
    def total(self) -> float:
        return (
            self.active_total
            + self.cumulative_discharges
            + self.cumulative_deaths
        )


@dataclass(frozen=True)
class StepFlows:
    """Requested and constrained flows for one timestep.

    ``requested`` holds the unconstrained Model B flow requests,
    ``constrained`` holds the raw constrained flows that define the actual
    simultaneous stock update, and ``unmet`` records demand that could not
    be served because of destination capacity (MODEL.md section 11).
    """

    hour: int
    arrivals_drawn: int
    arrivals_accepted: int
    requested: Dict[str, float]
    constrained: Dict[str, float]
    unmet: Dict[str, float] = field(default_factory=dict)

    @property
    def total_transfers(self) -> float:
        return sum(
            self.constrained[name]
            for name, _, _ in TRANSFERS
        )

    @property
    def total_discharges(self) -> float:
        return sum(self.constrained[name] for name in DISCHARGE_FLOWS)

    @property
    def total_deaths(self) -> float:
        return sum(self.constrained[name] for name in DEATH_FLOWS)


@dataclass(frozen=True)
class TimestepRecord:
    hour: int
    before: StateSnapshot
    after: StateSnapshot
    flows: StepFlows


@dataclass(frozen=True)
class RunResult:
    context: Any
    initial: StateSnapshot
    records: List[TimestepRecord]
    validation: Optional[Any] = None

    @property
    def final(self) -> StateSnapshot:
        return self.records[-1].after

    @property
    def passed(self) -> bool:
        if self.validation is None:
            return True
        return bool(self.validation.passed)


class AggregateEngine:
    """Aggregate Model B hospital-flow simulation engine."""

    def __init__(self, config, context, validator: Optional[Any] = None) -> None:
        self._config = config
        self.context = context

        self.dt = config.time_step_hours
        steps = config.simulation_hours / self.dt
        if steps != int(steps):
            raise AggregateEngineError(
                "simulation_hours must be an integer multiple of "
                f"time_step_hours ({self.dt}), got {config.simulation_hours}"
            )
        self.total_steps = int(steps)

        self._read_arrival_parameters(config)
        self._read_ed_parameters(config)
        self._read_destination_shares(config)
        self._read_transfer_rates(config)
        self._read_rate_tables(config)
        self._read_icu_pressure(config)
        self.capacities = {
            unit: float(config.capacities[unit]) for unit in ACTIVE_UNITS
        }
        self.capacity_timing = str(
            config.get("capacity", {}).get("timing", "beginning_of_step")
        )
        if self.capacity_timing != "beginning_of_step":
            raise AggregateEngineError(
                f"Unsupported capacity timing {self.capacity_timing!r}: "
                "Phase 1 requires 'beginning_of_step' (MODEL.md section 11)"
            )

        self.rng = np.random.default_rng(context.child_seed)
        if validator is None:
            validator = AggregateValidator(config)
        self.validator = validator

        self.initial = self._build_initial_state(config)
        self._validate_initial_state(self.initial)
        self.validator.validate_initial(self.initial)
        self.state = self.initial
        self.records: List[TimestepRecord] = []

    # ------------------------------------------------------------------
    # Configuration readers (no defaults invented; missing keys are errors)
    # ------------------------------------------------------------------

    def _read_arrival_parameters(self, config) -> None:
        arrivals = config.arrivals
        distribution = str(arrivals.get("distribution", "poisson"))
        if distribution != "poisson":
            raise AggregateEngineError(
                f"Unsupported arrivals distribution {distribution!r} "
                "(MODEL.md section 5 requires Poisson)"
            )
        self.lambda_0 = float(arrivals["baseline_rate_per_hour"])
        seasonality = arrivals.get("seasonality", {})
        self.seasonality_enabled = bool(seasonality.get("enabled", False))
        self.seasonality_amplitude = float(seasonality.get("amplitude", 0.0))
        self.seasonality_period = float(seasonality.get("period_hours", 24))
        self.seasonality_phase = float(seasonality.get("phase_shift_hours", 0))
        if self.seasonality_enabled and self.seasonality_amplitude >= 1.0:
            raise AggregateEngineError(
                "arrivals.seasonality.amplitude >= 1 produces negative "
                "arrival rates"
            )

        # Scenario-level arrival scaling (Step 8). Identity defaults keep the
        # S1 baseline unchanged. ``arrivals_multiplier`` scales the baseline
        # rate; ``arrivals_wave`` multiplies by ``factor`` for exactly
        # [start_hour, start_hour + duration_hours) and then resumes baseline.
        arrivals_overrides = arrivals.get("overrides", {})
        self.arrivals_multiplier = float(
            arrivals_overrides.get("arrivals_multiplier", 1.0)
        )
        wave = arrivals_overrides.get("arrivals_wave", {})
        self.wave_enabled = bool(wave.get("enabled", False))
        self.wave_factor = float(wave.get("factor", 1.0))
        self.wave_start = int(wave.get("start_hour", 0))
        self.wave_duration = int(wave.get("duration_hours", 0))
        if self.arrivals_multiplier < 0 or self.wave_factor < 0:
            raise AggregateEngineError(
                "arrivals overrides must be non-negative"
            )
        if self.wave_enabled and self.wave_duration <= 0:
            raise AggregateEngineError(
                "arrivals_wave duration_hours must be positive when enabled"
            )

    def _read_ed_parameters(self, config) -> None:
        ed_processing = config.ed_processing
        mean_hours = float(ed_processing["mean_processing_hours"])
        self.ed_a = float(ed_processing["a"])
        self.ed_b1 = float(ed_processing["b1"])
        if abs(mean_hours * self.ed_a - 1.0) > _FLOAT_EPS:
            raise AggregateEngineError(
                "ed_processing.a is inconsistent with "
                f"mean_processing_hours ({mean_hours})"
            )

    def _read_destination_shares(self, config) -> None:
        shares = config.destination_shares
        self.destination_shares = {
            key: float(shares[key]) for key in ("specialty", "general", "icu", "home")
        }
        total = sum(self.destination_shares.values())
        if abs(total - 1.0) > _FLOAT_EPS:
            raise AggregateEngineError(
                f"destination_shares must sum to 1, got {total} "
                "(MODEL.md section 7)"
            )

    def _read_transfer_rates(self, config) -> None:
        rates = config.transfer_rates
        self.transfer_rates = {
            "T_CG": float(rates["specialty_to_general"]),
            "T_CI": float(rates["specialty_to_icu"]),
            "T_GI": float(rates["general_to_icu"]),
        }

    def _read_rate_tables(self, config) -> None:
        discharge = config.discharge_rates
        mortality = config.mortality_rates
        self.discharge_rates = {
            "D_C": float(discharge["specialty"]),
            "D_G": float(discharge["general"]),
            "D_I": float(discharge["icu"]),
        }
        self.death_rates = {
            "M_C": float(mortality["specialty"]),
            "M_G": float(mortality["general"]),
            "M_I": float(mortality["icu"]),
        }

    def _read_icu_pressure(self, config) -> None:
        icu_pressure = config.icu_pressure
        self.icu_pressure_enabled = bool(icu_pressure.get("enabled", False))
        self.icu_zeta = float(icu_pressure.get("zeta", 0.0))
        self.icu_epsilon = float(icu_pressure.get("epsilon", 0.0))

    def _build_initial_state(self, config) -> StateSnapshot:
        initial = config.initial_conditions
        return StateSnapshot(
            hour=-1,
            ed_census=float(initial["ed_census"]),
            specialty_census=float(initial["specialty_census"]),
            general_census=float(initial["general_census"]),
            icu_census=float(initial["icu_census"]),
            cumulative_discharges=float(initial["cumulative_discharges"]),
            cumulative_deaths=float(initial["cumulative_deaths"]),
            cumulative_arrivals=0,
        )

    def _validate_initial_state(self, snapshot: StateSnapshot) -> None:
        for unit in ACTIVE_UNITS:
            stock = snapshot.stock(unit)
            capacity = self.capacities[unit]
            if stock < 0:
                raise AggregateEngineError(
                    f"Initial {unit} census is negative: {stock}"
                )
            if stock > capacity + _FLOAT_EPS:
                raise AggregateEngineError(
                    f"Initial {unit} census ({stock}) exceeds capacity "
                    f"({capacity}) (MODEL.md section 12)"
                )
        if snapshot.cumulative_discharges < 0 or snapshot.cumulative_deaths < 0:
            raise AggregateEngineError("Initial cumulative exits are negative")

    # ------------------------------------------------------------------
    # Model B equations (MODEL.md sections 5-10)
    # ------------------------------------------------------------------

    def arrival_rate(self, hour: int) -> float:
        base = self.lambda_0
        if self.seasonality_enabled:
            omega = 2.0 * np.pi / self.seasonality_period
            base = base * (
                1.0
                + self.seasonality_amplitude
                * np.sin(omega * (hour - self.seasonality_phase))
            )
        rate = base * self.arrivals_multiplier
        if self.wave_enabled and self.wave_start <= hour < (
            self.wave_start + self.wave_duration
        ):
            rate *= self.wave_factor
        return float(rate)

    def icu_pressure_factor(self, icu_census: float) -> float:
        if not self.icu_pressure_enabled:
            return 1.0
        return 1.0 + self.icu_zeta * icu_census / (
            1.0 + self.icu_epsilon * icu_census
        )

    def ed_processing_request(self, ed_census: float) -> float:
        requested = self.ed_a * ed_census / (1.0 + self.ed_b1 * ed_census)
        return min(requested, ed_census)

    # ------------------------------------------------------------------
    # One timestep
    # ------------------------------------------------------------------

    def step(self, hour: int) -> TimestepRecord:
        before = self.state
        flows = self._compute_flows(hour, before)
        after = self._apply_flows(hour, before, flows)
        record = TimestepRecord(
            hour=hour, before=before, after=after, flows=flows
        )
        if self.validator is not None:
            self.validator.validate_step(record)
        self.state = after
        self.records.append(record)
        return record

    def compute_flows(self, hour: int, before: StateSnapshot) -> StepFlows:
        """Compute requested + constrained flows from beginning-of-step state.

        Public wrapper around the Model B flow computation. Given a
        beginning-of-step ``before`` StateSnapshot, it draws Poisson
        arrivals, computes requested flows, and constrains them respecting
        source stock and beginning-of-step destination capacity (MODEL.md
        sections 5-11). It does NOT mutate engine state, so callers may feed
        integer operational stocks to drive a discrete patient layer (Model
        v1.0.1 flow pipeline).
        """
        return self._compute_flows(hour, before)

    def _compute_flows(self, hour: int, before: StateSnapshot) -> StepFlows:
        e = before.ed_census
        c = before.specialty_census
        g = before.general_census
        i = before.icu_census

        lam = self.arrival_rate(hour)
        if lam < 0:
            raise AggregateEngineError(f"Negative arrival rate at hour {hour}")
        arrivals_drawn = int(self.rng.poisson(lam * self.dt))

        q_i = self.icu_pressure_factor(i)
        t_e_requested = self.ed_processing_request(e)
        p = self.destination_shares
        k = self.transfer_rates

        requested: Dict[str, float] = {"arrivals": float(arrivals_drawn)}
        requested.update(
            {
                "T_EC": p["specialty"] * t_e_requested,
                "T_EG": p["general"] * t_e_requested,
                "T_EI": p["icu"] * t_e_requested,
                "T_EH": p["home"] * t_e_requested,
                "T_CG": k["T_CG"] * c * q_i,
                "T_CI": k["T_CI"] * c * q_i,
                "T_GI": k["T_GI"] * g,
                "D_C": self.discharge_rates["D_C"] * c,
                "D_G": self.discharge_rates["D_G"] * g,
                "D_I": self.discharge_rates["D_I"] * i,
                "M_C": self.death_rates["M_C"] * c,
                "M_G": self.death_rates["M_G"] * g,
                "M_I": self.death_rates["M_I"] * i,
            }
        )

        constrained, unmet, arrivals_accepted = self._constrain_flows(
            before, requested, arrivals_drawn
        )
        return StepFlows(
            hour=hour,
            arrivals_drawn=arrivals_drawn,
            arrivals_accepted=arrivals_accepted,
            requested=requested,
            constrained=constrained,
            unmet=unmet,
        )

    def _constrain_flows(
        self,
        before: StateSnapshot,
        requested: Dict[str, float],
        arrivals_drawn: int,
    ) -> tuple[Dict[str, float], Dict[str, float], int]:
        """Apply source-stock and beginning-of-step capacity constraints.

        Transfers are allocated sequentially in the approved order so that
        competing ICU inflows resolve according to the approved ICU priority
        (MODEL.md section 8). Destination availability uses ONLY
        beginning-of-step occupancy (MODEL.md section 11): beds released by
        this step's discharges, deaths or transfers stay unusable until the
        next timestep.
        """
        source_remaining = {unit: before.stock(unit) for unit in ACTIVE_UNITS}
        available_capacity = {
            unit: max(0.0, self.capacities[unit] - before.stock(unit))
            for unit in ACTIVE_UNITS
        }
        constrained: Dict[str, float] = dict.fromkeys(FLOW_NAMES, 0.0)
        unmet: Dict[str, float] = {}

        # Arrivals enter the ED subject to beginning-of-step ED capacity.
        arrivals_accepted = min(arrivals_drawn, int(available_capacity["ed"]))
        if arrivals_accepted < arrivals_drawn:
            unmet["ed"] = float(arrivals_drawn - arrivals_accepted)

        for name, src, dst in TRANSFERS:
            demand = requested[name]
            src_before = source_remaining[src]
            cap_before = available_capacity[dst]
            flow = min(demand, src_before, cap_before)
            constrained[name] = flow
            source_remaining[src] = src_before - flow
            available_capacity[dst] = cap_before - flow
            if flow < demand - _FLOAT_EPS and cap_before <= src_before:
                unmet[dst] = unmet.get(dst, 0.0) + (demand - flow)

        # Direct ED exit (home) competes only with remaining ED stock.
        t_eh = min(requested["T_EH"], source_remaining["ed"])
        constrained["T_EH"] = t_eh
        source_remaining["ed"] -= t_eh

        for name in list(DISCHARGE_FLOWS) + list(DEATH_FLOWS):
            constrained[name] = requested[name]

        self._guard_source_limits(before, constrained)
        return constrained, unmet, arrivals_accepted

    def _guard_source_limits(
        self, before: StateSnapshot, constrained: Dict[str, float]
    ) -> None:
        """Critical guard: total outflow may never exceed the source stock."""
        for unit in ACTIVE_UNITS:
            outflow = 0.0
            for name, src in EXIT_FLOWS.items():
                if src == unit:
                    outflow += constrained[name]
            for name, src, _ in TRANSFERS:
                if src == unit:
                    outflow += constrained[name]
            stock = before.stock(unit)
            if outflow > stock + 1e-6:
                raise AggregateEngineError(
                    f"Timestep {before.hour + 1}: total outflow from {unit} "
                    f"({outflow}) exceeds beginning-of-step stock ({stock})"
                )

    def _apply_flows(
        self, hour: int, before: StateSnapshot, flows: StepFlows
    ) -> StateSnapshot:
        """Simultaneous stock update (MODEL.md sections 4 and 16)."""
        f = flows.constrained
        accepted = float(flows.arrivals_accepted)
        after = StateSnapshot(
            hour=hour,
            ed_census=before.ed_census
            + accepted
            - f["T_EC"]
            - f["T_EG"]
            - f["T_EI"]
            - f["T_EH"],
            specialty_census=before.specialty_census
            + f["T_EC"]
            - f["T_CG"]
            - f["T_CI"]
            - f["D_C"]
            - f["M_C"],
            general_census=before.general_census
            + f["T_EG"]
            + f["T_CG"]
            - f["T_GI"]
            - f["D_G"]
            - f["M_G"],
            icu_census=before.icu_census
            + f["T_EI"]
            + f["T_CI"]
            + f["T_GI"]
            - f["D_I"]
            - f["M_I"],
            cumulative_discharges=before.cumulative_discharges
            + f["T_EH"]
            + f["D_C"]
            + f["D_G"]
            + f["D_I"],
            cumulative_deaths=before.cumulative_deaths
            + f["M_C"]
            + f["M_G"]
            + f["M_I"],
            cumulative_arrivals=before.cumulative_arrivals
            + flows.arrivals_accepted,
        )
        return after

    # ------------------------------------------------------------------
    # Run control
    # ------------------------------------------------------------------

    def run(self) -> RunResult:
        for hour in range(self.total_steps):
            self.step(hour)
        validation = None
        if self.validator is not None:
            validation = self.validator.result()
        return RunResult(
            context=self.context,
            initial=self.initial,
            records=self.records,
            validation=validation,
        )
