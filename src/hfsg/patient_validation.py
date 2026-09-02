"""Patient-level invariant validation (MODEL.md sections 19, 24, 25).

Enforces the patient-level rules that Step 6 (Patient Generator + Patient
Event Generator) must satisfy. The full aggregate-to-patient reconciliation
subsystem is Step 7 and is intentionally separate; this module covers the
patient/event invariants only.

Checks (MODEL.md section 24 / AGENTS.md section 14):

- unique patient_id;
- unique event_id;
- event time never moves backward (chronological per patient);
- no transfer before arrival;
- no event after discharge/death;
- one active location per patient;
- active patients belong to a valid active unit;
- terminal outcome is unique.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .events import (
    DISCHARGE_DESTINATION,
    EVENT_ARRIVAL,
    EVENT_DEATH,
    EVENT_DISCHARGE,
    EVENT_TRANSFER,
    TERMINAL_EVENTS,
)
from .units import ACTIVE_UNITS

SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING = "warning"


@dataclass(frozen=True)
class PatientValidationIssue:
    check: str
    severity: str
    message: str


@dataclass
class PatientValidationResult:
    issues: List[PatientValidationIssue] = field(default_factory=list)

    @property
    def critical_issues(self) -> List[PatientValidationIssue]:
        return [i for i in self.issues if i.severity == SEVERITY_CRITICAL]

    @property
    def passed(self) -> bool:
        return not self.critical_issues


class PatientValidationError(RuntimeError):
    def __init__(self, result: PatientValidationResult) -> None:
        self.result = result
        first = result.critical_issues[0]
        super().__init__(f"Critical patient validation failure: {first.message}")


class PatientValidator:
    """Validates patient/event invariants after Step 6 processing."""

    def __init__(self) -> None:
        self._result = PatientValidationResult()

    def validate(
        self,
        patients: List,
        events: List,
        final_hour: int,
    ) -> PatientValidationResult:
        result = PatientValidationResult()

        patient_ids = [p.patient_id for p in patients]
        self._check_unique(result, "unique_patient_ids", patient_ids, "patient")

        event_ids = [e.event_id for e in events]
        self._check_unique(result, "unique_event_ids", event_ids, "event")

        self._check_chronology(result, events)
        self._check_one_active_location(result, events, patients, final_hour)
        self._check_no_post_terminal(result, events)
        self._check_valid_active_units(result, patients, final_hour)
        self._check_unique_terminal(result, patients)

        self._result = result
        return result

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_unique(self, result, check, values, kind) -> None:
        seen = set()
        for value in values:
            if value in seen:
                result.issues.append(
                    PatientValidationIssue(
                        check=check,
                        severity=SEVERITY_CRITICAL,
                        message=f"duplicate {kind} id {value}",
                    )
                )
            seen.add(value)

    def _check_chronology(self, result, events) -> None:
        by_patient: Dict[int, List] = {}
        for event in events:
            by_patient.setdefault(event.patient_id, []).append(event)
        for patient_id, evs in by_patient.items():
            # Events are recorded in generation order (per-hour chronological).
            # Verify no event time moves backward and the first event is an
            # ARRIVAL (no transfer/discharge before arrival).
            if not evs:
                continue
            if evs[0].event_type != EVENT_ARRIVAL:
                result.issues.append(
                    PatientValidationIssue(
                        check="no_transfer_before_arrival",
                        severity=SEVERITY_CRITICAL,
                        message=f"patient {patient_id} first event is "
                        f"{evs[0].event_type}, not ARRIVAL",
                    )
                )
            prev_hour = None
            for event in evs:
                if prev_hour is not None and event.event_hour < prev_hour:
                    result.issues.append(
                        PatientValidationIssue(
                            check="chronological_events",
                            severity=SEVERITY_CRITICAL,
                            message=f"patient {patient_id} event time moved "
                            f"backward ({prev_hour} -> {event.event_hour})",
                        )
                    )
                prev_hour = event.event_hour

    def _check_one_active_location(self, result, events, patients, final_hour) -> None:
        # Reconstruct current_unit from events; verify a patient never
        # occupies two units simultaneously (movement is atomic).
        current = {}
        for event in events:
            pid = event.patient_id
            if event.event_type == EVENT_ARRIVAL:
                current[pid] = event.to_unit
            elif event.event_type == EVENT_TRANSFER:
                if current.get(pid) != event.from_unit:
                    result.issues.append(
                        PatientValidationIssue(
                            check="one_active_location_per_patient",
                            severity=SEVERITY_CRITICAL,
                            message=f"patient {pid} transfer from "
                            f"{event.from_unit} but currently in "
                            f"{current.get(pid)}",
                        )
                    )
                current[pid] = event.to_unit
            elif event.event_type in TERMINAL_EVENTS:
                if current.get(pid) != event.from_unit:
                    result.issues.append(
                        PatientValidationIssue(
                            check="one_active_location_per_patient",
                            severity=SEVERITY_CRITICAL,
                            message=f"patient {pid} terminal from "
                            f"{event.from_unit} but currently in "
                            f"{current.get(pid)}",
                        )
                    )
                current.pop(pid, None)

    def _check_no_post_terminal(self, result, events) -> None:
        seen_terminal = set()
        for event in events:
            pid = event.patient_id
            if pid in seen_terminal:
                result.issues.append(
                    PatientValidationIssue(
                        check="no_post_terminal_events",
                        severity=SEVERITY_CRITICAL,
                        message=f"patient {pid} has an event after a "
                        f"terminal event",
                    )
                )
            if event.event_type in TERMINAL_EVENTS:
                seen_terminal.add(pid)

    def _check_valid_active_units(self, result, patients, final_hour) -> None:
        for patient in patients:
            if patient.terminal_event is None and patient.current_unit not in ACTIVE_UNITS:
                result.issues.append(
                    PatientValidationIssue(
                        check="valid_active_unit",
                        severity=SEVERITY_CRITICAL,
                        message=f"patient {patient.patient_id} active in "
                        f"invalid unit {patient.current_unit}",
                    )
                )

    def _check_unique_terminal(self, result, patients) -> None:
        for patient in patients:
            if (
                patient.terminal_event is not None
                and patient.terminal_event not in TERMINAL_EVENTS
            ):
                result.issues.append(
                    PatientValidationIssue(
                        check="unique_terminal_outcome",
                        severity=SEVERITY_CRITICAL,
                        message=f"patient {patient.patient_id} has invalid "
                        f"terminal outcome {patient.terminal_event}",
                    )
                )
