"""Aggregate <-> Patient Reconciliation (MODEL.md section 23).

Reconciliation is a VALIDATION mechanism, never a correction. It proves
that the discrete patient layer and the operational aggregate stock layer
are consistent because both were generated from the SAME realized integer
flows (Model v1.0.1 clarification).

The authoritative operational pipeline is:

    requested_raw_flow
      -> constrained_raw_flow
      -> realized_integer_flow
           |-> patient events
           +-> operational aggregate stock update

The reconciler verifies, for every timestep:

    1. OperationalAggregateStock(unit,t) == active patient count in unit;
    2. cumulative discharges == number of discharged patients;
    3. cumulative deaths       == number of deceased patients;
    4. realized_integer_flow(flow,t)  == actual patient event count;
    5. operational mass balance (operational identity) holds.

If any check fails, the discrepancy is CRITICAL and must not be silently
repaired (MODEL.md section 23; section 22 CRITICAL_RECONCILIATION_FAILURE).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .units import ACTIVE_UNITS


SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING = "warning"

# Realized movement flows (from the Integer Flow Allocator) that correspond
# to patient events, keyed by event type and (from, to) semantics.
_TRANSFER_FLOWS = {
    "T_EC": ("ed", "specialty"),
    "T_EG": ("ed", "general"),
    "T_EI": ("ed", "icu"),
    "T_CG": ("specialty", "general"),
    "T_CI": ("specialty", "icu"),
    "T_GI": ("general", "icu"),
}
_DISCHARGE_FLOWS = {
    "D_C": "specialty",
    "D_G": "general",
    "D_I": "icu",
}
_DEATH_FLOWS = {
    "M_C": "specialty",
    "M_G": "general",
    "M_I": "icu",
}
# T_EH is the ED home-discharge flow (treated as a discharge event).
_HOME_DISCHARGE_FLOW = "T_EH"

_EVENT_TYPES = {"TRANSFER", "DISCHARGE", "DEATH"}
_DEATH_EVENT = "DEATH"
_DISCHARGE_EVENT = "DISCHARGE"
_TRANSFER_EVENT = "TRANSFER"


@dataclass(frozen=True)
class ReconciliationIssue:
    hour: int
    check: str
    severity: str
    message: str


@dataclass
class ReconciliationResult:
    issues: List[ReconciliationIssue] = field(default_factory=list)

    @property
    def critical_issues(self) -> List[ReconciliationIssue]:
        return [i for i in self.issues if i.severity == SEVERITY_CRITICAL]

    @property
    def passed(self) -> bool:
        return not self.critical_issues

    @property
    def issue_count(self) -> int:
        return len(self.issues)


class ReconciliationFailure(RuntimeError):
    """Raised when a critical reconciliation invariant is violated."""

    def __init__(self, result: ReconciliationResult) -> None:
        self.result = result
        first = result.critical_issues[0]
        super().__init__(
            f"Critical reconciliation failure at hour "
            f"{first.hour}: [{first.check}] {first.message}"
        )


@dataclass(frozen=True)
class OperationalStocks:
    """Integer operational aggregate stocks (authoritative patient counts)."""

    hour: int
    ed: int
    specialty: int
    general: int
    icu: int
    discharged: int
    deceased: int
    cumulative_arrivals: int

    def active(self, unit: str) -> int:
        return getattr(self, _UNIT_FIELD[unit])

    @property
    def active_total(self) -> int:
        return self.ed + self.specialty + self.general + self.icu

    @property
    def terminal_total(self) -> int:
        return self.discharged + self.deceased

    @property
    def total(self) -> int:
        return self.active_total + self.terminal_total


_UNIT_FIELD = {
    "ed": "ed",
    "specialty": "specialty",
    "general": "general",
    "icu": "icu",
}


class Reconciler:
    """Validates aggregate/patient consistency for one timestep and overall."""

    def __init__(self, config) -> None:
        self.capacities = {
            unit: float(config.capacities[unit]) for unit in ACTIVE_UNITS
        }
        self._result = ReconciliationResult()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reconcile_timestep(
        self,
        hour: int,
        stocks: OperationalStocks,
        patients: List,
        realized_flows: Dict[str, int],
        step_events: List,
        initial_patient_count: int,
    ) -> None:
        """Check one timestep's aggregate/patient and flow/event consistency.

        ``realized_flows`` is the authoritative integer quota dict from the
        Integer Flow Allocator. ``step_events`` are the events generated for
        this timestep. ``initial_patient_count`` is the size of the initial
        population (used for the mass-balance identity N0 + admitted arrivals).
        """
        active = {
            u: sum(
                1
                for p in patients
                if p.terminal_event is None and p.current_unit == u
            )
            for u in ACTIVE_UNITS
        }
        for unit in ACTIVE_UNITS:
            if stocks.active(unit) != active[unit]:
                self._add(
                    hour,
                    "aggregate_patient_reconciliation",
                    SEVERITY_CRITICAL,
                    f"{unit} operational stock {stocks.active(unit)} != "
                    f"active patient count {active[unit]}",
                )

        discharged = sum(1 for p in patients if p.terminal_event == "DISCHARGE")
        deceased = sum(1 for p in patients if p.terminal_event == "DEATH")
        if stocks.discharged != discharged:
            self._add(
                hour,
                "aggregate_patient_reconciliation",
                SEVERITY_CRITICAL,
                f"cumulative discharges stock {stocks.discharged} != "
                f"discharged patients {discharged}",
            )
        if stocks.deceased != deceased:
            self._add(
                hour,
                "aggregate_patient_reconciliation",
                SEVERITY_CRITICAL,
                f"cumulative deaths stock {stocks.deceased} != "
                f"deceased patients {deceased}",
            )

        self._reconcile_flows(hour, realized_flows, step_events)

        # Operational mass balance (integer identity).
        n0 = initial_patient_count
        expected_total = n0 + stocks.cumulative_arrivals
        if stocks.total != expected_total:
            self._add(
                hour,
                "mass_balance",
                SEVERITY_CRITICAL,
                f"operational total {stocks.total} != N0({n0}) + "
                f"admitted({stocks.cumulative_arrivals}) = {expected_total}",
            )

    def _reconcile_flows(
        self, hour: int, realized_flows: Dict[str, int], step_events: List
    ) -> None:
        """Verify realized_integer_flow == actual event count for every flow."""
        counts = self._event_counts(step_events)

        for flow, realized in realized_flows.items():
            expected = self._expected_events(flow)
            if expected is None:
                continue  # not a movement flow (e.g. none); skip
            actual = counts.get(expected, 0)
            if actual != realized:
                self._add(
                    hour,
                    "realized_flow_event_reconciliation",
                    SEVERITY_CRITICAL,
                    f"realized {flow}={realized} != event count {actual} "
                    f"(expected {expected})",
                )

    def _expected_events(self, flow: str):
        """Map a realized flow to the event-count key it should equal.

        Returns None for flows that do not produce a patient movement event
        (only the realized movement flows are compared against events).
        """
        if flow in _TRANSFER_FLOWS:
            return ("TRANSFER", _TRANSFER_FLOWS[flow][0], _TRANSFER_FLOWS[flow][1])
        if flow in _DISCHARGE_FLOWS:
            return ("DISCHARGE", _DISCHARGE_FLOWS[flow], "discharged")
        if flow == _HOME_DISCHARGE_FLOW:
            return ("DISCHARGE", "ed", "discharged")
        if flow in _DEATH_FLOWS:
            return ("DEATH", _DEATH_FLOWS[flow], "deceased")
        return None

    def _event_counts(self, events: List) -> Dict:
        """Count events by (event_type, from_unit, to_unit)."""
        counts: Dict = {}
        for ev in events:
            key = (ev.event_type, ev.from_unit, ev.to_unit)
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _add(self, hour, check, severity, message) -> None:
        self._result.issues.append(
            ReconciliationIssue(
                hour=hour, check=check, severity=severity, message=message
            )
        )

    def result(self) -> ReconciliationResult:
        return self._result

    def raise_if_critical(self) -> None:
        if self._result.critical_issues:
            raise ReconciliationFailure(self.result())