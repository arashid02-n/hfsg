"""Patient Event Generator (MODEL.md sections 16, 21, 22, 17, and 8).

Converts integer aggregate quotas into individual ARRIVAL / TRANSFER /
DISCHARGE / DEATH events. The Aggregate engine determines HOW MANY patients
move; this generator determines WHICH patients move (MODEL.md section 15)
and MUST NOT change the approved quotas.

Patient selection rules (MODEL.md section 22):

- ED non-ICU movement: FIFO.
- ICU transfer: highest severity, then longest waiting time, then a
  seeded-random tie break.
- Discharge: longest stay first (minimum-stay eligibility inactive unless
  configured).
- Death: weighted selection (severity 0.50 / ICU status 0.30 / elapsed stay
  0.20).

Timestep eligibility (MODEL.md section 17): patients arriving during
timestep t are ineligible for transfer, discharge or death during t.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from .patients import Patient

EXTERNAL_ORIGIN = "external"
DISCHARGE_DESTINATION = "discharged"
DEATH_DESTINATION = "deceased"

EVENT_ARRIVAL = "ARRIVAL"
EVENT_TRANSFER = "TRANSFER"
EVENT_DISCHARGE = "DISCHARGE"
EVENT_DEATH = "DEATH"

TERMINAL_EVENTS = (EVENT_DISCHARGE, EVENT_DEATH)

# Death weighting components (MODEL.md section 22, project assumptions).
DEATH_WEIGHT_SEVERITY = 0.50
DEATH_WEIGHT_ICU = 0.30
DEATH_WEIGHT_STAY = 0.20


class CRITICAL_RECONCILIATION_FAILURE(RuntimeError):
    """Raised when a valid integer quota cannot be satisfied by patient
    state (MODEL.md section 22). The quota is never silently changed."""


# (source, destination) endpoints for transfer flows.
_TRANSFER_ENDPOINTS = {
    "T_EC": ("ed", "specialty"),
    "T_EG": ("ed", "general"),
    "T_EI": ("ed", "icu"),
    "T_CG": ("specialty", "general"),
    "T_CI": ("specialty", "icu"),
    "T_GI": ("general", "icu"),
}


@dataclass(frozen=True)
class PatientEvent:
    simulation_id: str
    scenario_id: str
    patient_id: int
    event_id: int
    event_datetime: str
    event_hour: int
    event_type: str
    from_unit: str
    to_unit: str
    quota_flow: str = ""


class SimulationClock:
    """Maps simulation hour to a deterministic wall-clock datetime."""

    def __init__(self, start: Optional[datetime] = None) -> None:
        self._start = start or datetime(
            2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc
        )

    def at(self, hour: int) -> datetime:
        return self._start + timedelta(hours=hour)

    def iso(self, hour: int) -> str:
        return self.at(hour).isoformat()


class PatientEventGenerator:
    """Generates patient events from integer quotas and patient state."""

    def __init__(self, config, simulation_id, scenario_id, rng=None) -> None:
        self._config = config
        self._simulation_id = simulation_id
        self._scenario_id = scenario_id
        self._rng = rng
        self._next_event_id = 1

    def set_rng(self, rng) -> None:
        self._rng = rng

    def new_event_id(self) -> int:
        event_id = self._next_event_id
        self._next_event_id += 1
        return event_id

    # ------------------------------------------------------------------
    # ARRIVAL
    # ------------------------------------------------------------------

    def arrival_event(
        self, patient: Patient, hour: int, clock: SimulationClock
    ) -> PatientEvent:
        return PatientEvent(
            simulation_id=self._simulation_id,
            scenario_id=self._scenario_id,
            patient_id=patient.patient_id,
            event_id=self.new_event_id(),
            event_datetime=clock.iso(hour),
            event_hour=hour,
            event_type=EVENT_ARRIVAL,
            from_unit=EXTERNAL_ORIGIN,
            to_unit=patient.initial_unit,
            quota_flow="arrivals",
        )

    # ------------------------------------------------------------------
    # Candidate selection
    # ------------------------------------------------------------------

    def _eligible(self, patients: List[Patient], hour: int) -> List[Patient]:
        """Patients present that are eligible for movement at ``hour``.

        MODEL.md section 17: patients arriving during timestep ``hour`` are
        not eligible for transfer, discharge or death during that timestep;
        they become eligible at ``hour + 1``.

        Initial patients (entry_type=INITIAL) are present at N(0) and are
        eligible from hour 0 onward (they did not "arrive" during a
        timestep; no prior-stay is invented).
        """
        return [
            p
            for p in patients
            if p.terminal_event is None
            and p.arrival_hour is not None
            and (
                p.entry_type == "INITIAL"
                or p.arrival_hour < hour
            )
        ]

    def _by_unit(self, patients, unit):
        return [p for p in patients if p.current_unit == unit]

    def _fifo(self, candidates: List[Patient]) -> List[Patient]:
        return sorted(
            candidates,
            key=lambda p: (p.arrival_hour, p.patient_id),
        )

    def _icu_priority(self, candidates: List[Patient], hour: int) -> List[Patient]:
        # Highest severity desc, then longest waiting time desc, then a
        # seeded-random tie-break (MODEL.md section 22).
        waiting = self._waits_from(candidates, hour)
        tie = self._tie_break_values(candidates)
        return sorted(
            candidates,
            key=lambda p: (
                -p.severity_rank,
                -waiting[p.patient_id],
                -tie[p.patient_id],
                p.patient_id,
            ),
        )

    def _longest_stay_first(self, candidates: List[Patient], hour: int) -> List[Patient]:
        # Longest elapsed stay first; patient_id as a stable secondary key.
        stays = self._waits_from(candidates, hour)
        return sorted(
            candidates,
            key=lambda p: (-stays[p.patient_id], p.patient_id),
        )

    def _weighted_death(self, candidates: List[Patient], hour: int) -> List[Patient]:
        stays = self._waits_from(candidates, hour)
        max_sev = max((p.severity_rank for p in candidates), default=1)
        max_stay = max((stays[p.patient_id] for p in candidates), default=1)
        max_sev = max(max_sev, 1)
        max_stay = max(max_stay, 1)

        scores = {}
        for p in candidates:
            severity_component = (
                (p.severity_rank - 1) / (max_sev - 1) if max_sev > 1 else 1.0
            )
            icu_component = 1.0 if p.current_unit == "icu" else 0.0
            stay_component = stays[p.patient_id] / max_stay
            scores[p.patient_id] = (
                DEATH_WEIGHT_SEVERITY * severity_component
                + DEATH_WEIGHT_ICU * icu_component
                + DEATH_WEIGHT_STAY * stay_component
            )
        tie = self._tie_break_values(candidates)
        return sorted(
            candidates,
            key=lambda p: (-scores[p.patient_id], -tie[p.patient_id], p.patient_id),
        )

    def _waits_from(self, candidates: List[Patient], hour: int) -> Dict[int, int]:
        return {
            p.patient_id: max(0, hour - (p.arrival_hour or 0)) for p in candidates
        }

    def _tie_break_values(self, patients: List[Patient]) -> Dict[int, float]:
        if not patients or self._rng is None:
            return {p.patient_id: 0.0 for p in patients}
        stream = self._rng.uniform(size=len(patients))
        return {p.patient_id: float(stream[i]) for i, p in enumerate(patients)}

    # ------------------------------------------------------------------
    # Flow-level emission
    # ------------------------------------------------------------------

    def process_timestep(
        self,
        patients: List[Patient],
        hour: int,
        quotas: Dict[str, int],
        clock: SimulationClock,
    ) -> List[PatientEvent]:
        """Emit all events for one timestep using the integer quotas.

        ``quotas`` is the approved integer quota dict (flow name -> count)
        produced by the Integer Flow Allocator. This generator selects WHICH
        patients move but MUST NOT change the quota counts (MODEL.md 15).
        """
        candidates = self._eligible(patients, hour)
        events: List[PatientEvent] = []

        self._process_arrivals(patients, hour, clock, events, quota_from=quotas)

        # Transfers resolve ICU inflows; ED non-ICU flows first.
        for flow in ("T_EI", "T_CI", "T_GI"):
            self._process_transfer(
                patients, candidates, hour, clock, events, flow, quota_from=quotas
            )
        for flow in ("T_EC", "T_EG"):
            self._process_ed_non_icu(
                patients, candidates, hour, clock, events, flow, quota_from=quotas
            )
        # Direct ED exit (home).
        self._process_discharge_home(
            patients, candidates, hour, clock, events, quota_from=quotas
        )
        # Ward discharges.
        for flow, unit in (("D_C", "specialty"), ("D_G", "general"), ("D_I", "icu")):
            self._process_discharge(
                patients, candidates, hour, clock, events, flow, unit, quota_from=quotas
            )
        # Deaths.
        for flow, unit in (("M_C", "specialty"), ("M_G", "general"), ("M_I", "icu")):
            self._process_death(
                patients, candidates, hour, clock, events, flow, unit, quota_from=quotas
            )

        return events

    def _process_arrivals(
        self, patients, hour, clock, events, quota_from
    ) -> None:
        # Emit an ARRIVAL event for every patient entering at ``hour``,
        # including the INITIAL population at hour 0 (their ARRIVAL places
        # them in their initial unit). Admitted arrivals and initial
        # patients both require an ARRIVAL event (MODEL.md section 21).
        for patient in patients:
            if patient.arrival_hour != hour:
                continue
            if patient.terminal_event is not None:
                continue
            events.append(self.arrival_event(patient, hour, clock))

    def _take(
        self,
        patients: List[Patient],
        candidates: List[Patient],
        unit: str,
        ordered: List[Patient],
        count: int,
        hour: int,
    ) -> List[Patient]:
        """Select exactly ``count`` eligible patients from ``unit``.

        Raises if the quota cannot be satisfied (MODEL.md section 22:
        CRITICAL_RECONCILIATION_FAILURE rather than silently changing the
        quota). Full reconciliation is deferred to Step 7, but Step 6 must
        not violate a quota silently.
        """
        in_unit = [p for p in candidates if p.current_unit == unit]
        ordered_unit = [p for p in ordered if p.current_unit == unit]
        pool = ordered_unit if ordered_unit else in_unit
        if count > len(pool):
            raise CRITICAL_RECONCILIATION_FAILURE(
                f"cannot satisfy quota {count} for {unit} with only "
                f"{len(pool)} eligible patients at hour {hour}"
            )
        return pool[:count]

    def _apply_movement(self, patient: Patient, from_unit, to_unit, event) -> None:
        if patient.current_unit != from_unit:
            raise CRITICAL_RECONCILIATION_FAILURE(
                f"patient {patient.patient_id} in {patient.current_unit} "
                f"but expected {from_unit}"
            )
        patient.current_unit = to_unit
        patient.activity_start_hour = event.event_hour

    def _process_transfer(self, patients, candidates, hour, clock, events, flow, quota_from) -> None:
        quota = int(quota_from.get(flow, 0))
        if quota <= 0:
            return
        src, dst = _TRANSFER_ENDPOINTS[flow]
        ordered = self._icu_priority(candidates, hour)
        chosen = self._take(patients, candidates, src, ordered, quota, hour)
        for patient in chosen:
            event = PatientEvent(
                simulation_id=self._simulation_id,
                scenario_id=self._scenario_id,
                patient_id=patient.patient_id,
                event_id=self.new_event_id(),
                event_datetime=clock.iso(hour),
                event_hour=hour,
                event_type=EVENT_TRANSFER,
                from_unit=src,
                to_unit=dst,
                quota_flow=flow,
            )
            self._apply_movement(patient, src, dst, event)
            events.append(event)

    def _process_ed_non_icu(self, patients, candidates, hour, clock, events, flow, quota_from) -> None:
        quota = int(quota_from.get(flow, 0))
        if quota <= 0:
            return
        _, dst = _TRANSFER_ENDPOINTS[flow]
        ordered = self._fifo(candidates)
        chosen = self._take(patients, candidates, "ed", ordered, quota, hour)
        for patient in chosen:
            event = PatientEvent(
                simulation_id=self._simulation_id,
                scenario_id=self._scenario_id,
                patient_id=patient.patient_id,
                event_id=self.new_event_id(),
                event_datetime=clock.iso(hour),
                event_hour=hour,
                event_type=EVENT_TRANSFER,
                from_unit="ed",
                to_unit=dst,
                quota_flow=flow,
            )
            self._apply_movement(patient, "ed", dst, event)
            events.append(event)

    def _process_discharge_home(self, patients, candidates, hour, clock, events, quota_from) -> None:
        quota = int(quota_from.get("T_EH", 0))
        if quota <= 0:
            return
        ordered = self._fifo(candidates)
        chosen = self._take(patients, candidates, "ed", ordered, quota, hour)
        for patient in chosen:
            event = PatientEvent(
                simulation_id=self._simulation_id,
                scenario_id=self._scenario_id,
                patient_id=patient.patient_id,
                event_id=self.new_event_id(),
                event_datetime=clock.iso(hour),
                event_hour=hour,
                event_type=EVENT_DISCHARGE,
                from_unit="ed",
                to_unit=DISCHARGE_DESTINATION,
                quota_flow="T_EH",
            )
            self._finish(patient, "ed", event, EVENT_DISCHARGE)
            events.append(event)

    def _process_discharge(self, patients, candidates, hour, clock, events, flow, unit, quota_from) -> None:
        quota = int(quota_from.get(flow, 0))
        if quota <= 0:
            return
        ordered = self._longest_stay_first(candidates, hour)
        chosen = self._take(patients, candidates, unit, ordered, quota, hour)
        for patient in chosen:
            event = PatientEvent(
                simulation_id=self._simulation_id,
                scenario_id=self._scenario_id,
                patient_id=patient.patient_id,
                event_id=self.new_event_id(),
                event_datetime=clock.iso(hour),
                event_hour=hour,
                event_type=EVENT_DISCHARGE,
                from_unit=unit,
                to_unit=DISCHARGE_DESTINATION,
                quota_flow=flow,
            )
            self._finish(patient, unit, event, EVENT_DISCHARGE)
            events.append(event)

    def _process_death(self, patients, candidates, hour, clock, events, flow, unit, quota_from) -> None:
        quota = int(quota_from.get(flow, 0))
        if quota <= 0:
            return
        ordered = self._weighted_death(candidates, hour)
        chosen = self._take(patients, candidates, unit, ordered, quota, hour)
        for patient in chosen:
            event = PatientEvent(
                simulation_id=self._simulation_id,
                scenario_id=self._scenario_id,
                patient_id=patient.patient_id,
                event_id=self.new_event_id(),
                event_datetime=clock.iso(hour),
                event_hour=hour,
                event_type=EVENT_DEATH,
                from_unit=unit,
                to_unit=DEATH_DESTINATION,
                quota_flow=flow,
            )
            self._finish(patient, unit, event, EVENT_DEATH)
            events.append(event)

    def _finish(self, patient, from_unit, event, terminal) -> None:
        if patient.current_unit != from_unit:
            raise CRITICAL_RECONCILIATION_FAILURE(
                f"patient {patient.patient_id} in {patient.current_unit} "
                f"but expected {from_unit}"
            )
        patient.current_unit = from_unit
        patient.terminal_event = terminal
        patient.terminal_hour = event.event_hour
