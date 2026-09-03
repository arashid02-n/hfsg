"""Integrated simulation driver (Model v1.0.1 flow pipeline).

Runs the full per-timestep loop that keeps the discrete patient layer and
the operational integer aggregate layer consistent by construction, because
both are driven by the SAME realized integer flows.

Per timestep:

    1.  build beginning-of-step operational integer stocks;
    2.  compute requested/constrained raw flows from the Model B equations;
    3.  Integer Flow Allocator produces realized integer flows;
    4.  create patient entities for admitted arrivals;
    5.  generate ARRIVAL + movement events from realized flows;
    6.  update operational integer stocks using realized flows;
    7.  reconcile patient layer <-> operational aggregate layer.

Reconciliation is validation only (never correction). A critical
reconciliation failure stops the run loudly instead of being hidden.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from .engine import AggregateEngine, StateSnapshot
from .events import PatientEventGenerator, SimulationClock
from .patients import PatientGenerator
from .quota import IntegerFlowAllocator
from .reconciliation import OperationalStocks, Reconciler
from .units import ACTIVE_UNITS


@dataclass(frozen=True)
class StepOutcome:
    """One timestep's flow + reconciliation record."""

    hour: int
    arrivals_drawn: int
    arrivals_accepted: int
    unmet_arrivals: int
    requested_raw: Dict[str, float]
    constrained_raw: Dict[str, float]
    realized_flow: Dict[str, int]
    integerization_difference: Dict[str, float]
    before: OperationalStocks
    after: OperationalStocks
    step_events: List
    event_count: int


@dataclass(frozen=True)
class SimulationResult:
    outcomes: List[StepOutcome]
    patients: List = field(default_factory=list)
    events: List = field(default_factory=list)
    reconciliation: Optional = None
    initial_stocks: Optional = None

    @property
    def final(self) -> OperationalStocks:
        return self.outcomes[-1].after

    @property
    def completed_full_horizon(self) -> bool:
        return bool(self.outcomes) and len(self.outcomes) == self.horizon_steps

    @property
    def horizon_steps(self) -> int:
        return self.outcomes[-1].hour + 1 if self.outcomes else 0


class SimulationDriver:
    """Coordinates model flow computation, integerization, patient events and
    operational stock updates into one reconciling simulation."""

    INITIAL_STOCKS = {"ed": 20, "specialty": 25, "general": 60, "icu": 10}

    def __init__(self, config, context, rng=None, patient_rng=None) -> None:
        self.config = config
        self.context = context
        self.engine = AggregateEngine(config, context)
        self.clock = SimulationClock()

        self._rng = rng if rng is not None else np.random.default_rng(context.child_seed)
        self.engine.rng = self._rng

        self.allocator = IntegerFlowAllocator(
            config, seed=context.child_seed, rng=self._rng
        )
        self.patient_gen = PatientGenerator(
            config,
            simulation_id=context.simulation_id,
            scenario_id=context.scenario_id,
            rng=(patient_rng or np.random.default_rng(context.child_seed)),
        )
        self.event_gen = PatientEventGenerator(
            config,
            simulation_id=context.simulation_id,
            scenario_id=context.scenario_id,
            rng=self._rng,
        )
        self.reconciler = Reconciler(config)

        self.initial_population = []
        self.patients: List = []
        self.events: List = []
        self.outcomes: List[StepOutcome] = []
        self._next_clock_hour = 0
        self.horizon = int(config.simulation_hours / config.time_step_hours)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def run(self) -> SimulationResult:
        # Initialize operational stocks from configuration initial conditions.
        ic = self.config.initial_conditions
        stocks = OperationalStocks(
            hour=-1,
            ed=int(ic["ed_census"]),
            specialty=int(ic["specialty_census"]),
            general=int(ic["general_census"]),
            icu=int(ic["icu_census"]),
            discharged=int(ic["cumulative_discharges"]),
            deceased=int(ic["cumulative_deaths"]),
            cumulative_arrivals=0,
        )

        # Create the initial patient population matching the stocks.
        self.initial_population = self.patient_gen.create_initial_population(
            {
                "ed": stocks.ed,
                "specialty": stocks.specialty,
                "general": stocks.general,
                "icu": stocks.icu,
            },
            self.clock.iso(0),
        )
        self.patients = list(self.initial_population)

        for hour in range(self.horizon):
            before = self._to_snapshot(stocks, hour)
            step = self._step(hour, before, stocks)
            stocks = step.after
            self.outcomes.append(step)

        result = SimulationResult(
            outcomes=self.outcomes,
            patients=self.patients,
            events=self.events,
            reconciliation=self.reconciler.result(),
            initial_stocks=self.initial_population,
        )
        return result

    # ------------------------------------------------------------------
    # Per-timestep
    # ------------------------------------------------------------------

    def _to_snapshot(self, stocks: OperationalStocks, hour: int) -> StateSnapshot:
        return StateSnapshot(
            hour=hour - 1,
            ed_census=float(stocks.ed),
            specialty_census=float(stocks.specialty),
            general_census=float(stocks.general),
            icu_census=float(stocks.icu),
            cumulative_discharges=float(stocks.discharged),
            cumulative_deaths=float(stocks.deceased),
            cumulative_arrivals=stocks.cumulative_arrivals,
        )

    def _step(
        self, hour: int, before_snapshot: StateSnapshot, stocks: OperationalStocks
    ) -> StepOutcome:
        # 1-2. Compute requested + constrained raw flows from Model B.
        flows = self.engine.compute_flows(hour, before_snapshot)
        admitted = int(flows.arrivals_accepted)
        unmet = int(flows.arrivals_drawn - flows.arrivals_accepted)

        # 3. Integerize constrained flows -> realized integer flows.
        quota = self.allocator.allocate(hour, before_snapshot, flows.constrained)
        realized = dict(quota.quotas)
        differences = dict(quota.differences)

        # 4. Create patient entities for admitted arrivals.
        new_patients = self.patient_gen.create_arrival_patients(
            admitted, hour, self.clock.iso(hour)
        )
        self.patients.extend(new_patients)

        # 5. Generate all events from realized integer flows.
        step_events = self.event_gen.process_timestep(
            self.patients, hour, realized, self.clock
        )
        self.events.extend(step_events)

        # 6. Update operational integer stocks using realized flows.
        after = self._apply_realized(stocks, hour, admitted, realized)

        # 7. Reconcile patient layer <-> operational aggregate layer.
        self.reconciler.reconcile_timestep(
            hour=hour,
            stocks=after,
            patients=self.patients,
            realized_flows=realized,
            step_events=step_events,
            initial_patient_count=len(self.initial_population),
        )
        self.reconciler.raise_if_critical()

        return StepOutcome(
            hour=hour,
            arrivals_drawn=int(flows.arrivals_drawn),
            arrivals_accepted=admitted,
            unmet_arrivals=unmet,
            requested_raw=dict(flows.requested),
            constrained_raw=dict(flows.constrained),
            realized_flow=realized,
            integerization_difference=differences,
            before=stocks,
            after=after,
            step_events=step_events,
            event_count=len(step_events),
        )

    def _apply_realized(
        self,
        stocks: OperationalStocks,
        hour: int,
        admitted: int,
        realized: Dict[str, int],
    ) -> OperationalStocks:
        """Update operational integer stocks with realized integer flows."""
        ed = (
            stocks.ed
            + admitted
            - realized.get("T_EC", 0)
            - realized.get("T_EG", 0)
            - realized.get("T_EI", 0)
            - realized.get("T_EH", 0)
        )
        specialty = (
            stocks.specialty
            + realized.get("T_EC", 0)
            - realized.get("T_CG", 0)
            - realized.get("T_CI", 0)
            - realized.get("D_C", 0)
            - realized.get("M_C", 0)
        )
        general = (
            stocks.general
            + realized.get("T_EG", 0)
            + realized.get("T_CG", 0)
            - realized.get("T_GI", 0)
            - realized.get("D_G", 0)
            - realized.get("M_G", 0)
        )
        icu = (
            stocks.icu
            + realized.get("T_EI", 0)
            + realized.get("T_CI", 0)
            + realized.get("T_GI", 0)
            - realized.get("D_I", 0)
            - realized.get("M_I", 0)
        )
        discharged = (
            stocks.discharged
            + realized.get("T_EH", 0)
            + realized.get("D_C", 0)
            + realized.get("D_G", 0)
            + realized.get("D_I", 0)
        )
        deceased = (
            stocks.deceased
            + realized.get("M_C", 0)
            + realized.get("M_G", 0)
            + realized.get("M_I", 0)
        )
        return OperationalStocks(
            hour=hour,
            ed=int(ed),
            specialty=int(specialty),
            general=int(general),
            icu=int(icu),
            discharged=int(discharged),
            deceased=int(deceased),
            cumulative_arrivals=stocks.cumulative_arrivals + admitted,
        )