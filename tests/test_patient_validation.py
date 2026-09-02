"""Tests for patient/event invariant validation (MODEL.md sections 24, 25).

The full aggregate-to-patient reconciliation is Step 7; this module covers
Step 6's patient/event invariants only.
"""

from hfsg.events import (
    DISCHARGE_DESTINATION,
    EVENT_ARRIVAL,
    EVENT_DEATH,
    EVENT_DISCHARGE,
    EVENT_TRANSFER,
    PatientEvent,
)
from hfsg.patient_validation import PatientValidationResult, PatientValidator
from hfsg.patients import Patient


def _patient(pid=1, unit="ed", terminal=None):
    return Patient(
        simulation_id="sim",
        scenario_id="S1",
        patient_id=pid,
        arrival_datetime="t",
        age_group="18-44",
        sex="Female",
        severity_level="Medium",
        arrival_mode="Walk-in",
        initial_unit=unit,
        entry_type="ARRIVAL",
        current_unit=unit,
        arrival_hour=0,
        model_arrival_hour=0,
        terminal_event=terminal,
    )


def _event(eid, pid, etype, frm, to, hour):
    return PatientEvent(
        simulation_id="sim",
        scenario_id="S1",
        patient_id=pid,
        event_id=eid,
        event_datetime="t",
        event_hour=hour,
        event_type=etype,
        from_unit=frm,
        to_unit=to,
    )


class TestPatientValidator:
    def test_clean_sequence_passes(self):
        p1 = _patient(1, "ed")
        p2 = _patient(2, "specialty")
        events = [
            _event(1, 1, EVENT_ARRIVAL, "external", "ed", 0),
            _event(2, 2, EVENT_ARRIVAL, "external", "specialty", 0),
            _event(3, 1, EVENT_TRANSFER, "ed", "specialty", 1),
            _event(4, 1, EVENT_DISCHARGE, "specialty", DISCHARGE_DESTINATION, 2),
            _event(5, 2, EVENT_DEATH, "specialty", "deceased", 3),
        ]
        result = PatientValidator().validate([p1, p2], events, final_hour=5)
        assert result.passed

    def test_duplicate_patient_id(self):
        events = []
        result = PatientValidator().validate(
            [_patient(1), _patient(1)], events, final_hour=1
        )
        assert not result.passed
        assert any(i.check == "unique_patient_ids" for i in result.critical_issues)

    def test_duplicate_event_id(self):
        p = _patient(1)
        events = [_event(1, 1, EVENT_ARRIVAL, "external", "ed", 0),
                  _event(1, 1, EVENT_TRANSFER, "ed", "specialty", 1)]
        result = PatientValidator().validate([p], events, final_hour=2)
        assert any(i.check == "unique_event_ids" for i in result.critical_issues)

    def test_non_chronological_events(self):
        p = _patient(1)
        events = [_event(1, 1, EVENT_ARRIVAL, "external", "ed", 2),
                  _event(2, 1, EVENT_TRANSFER, "ed", "specialty", 1)]
        result = PatientValidator().validate([p], events, final_hour=3)
        assert any(i.check == "chronological_events" for i in result.critical_issues)

    def test_no_event_after_terminal(self):
        p = _patient(1, "specialty", terminal=EVENT_DISCHARGE)
        events = [_event(1, 1, EVENT_ARRIVAL, "external", "ed", 0),
                  _event(2, 1, EVENT_DISCHARGE, "specialty", DISCHARGE_DESTINATION, 1),
                  _event(3, 1, EVENT_TRANSFER, "specialty", "general", 2)]
        result = PatientValidator().validate([p], events, final_hour=3)
        assert any(i.check == "no_post_terminal_events" for i in result.critical_issues)

    def test_transfer_before_arrival_detected(self):
        p = _patient(1)
        # First event is a TRANSFER (no ARRIVAL) -> invalid.
        events = [_event(1, 1, EVENT_TRANSFER, "ed", "specialty", 0)]
        result = PatientValidator().validate([p], events, final_hour=1)
        assert any(i.check == "no_transfer_before_arrival" for i in result.critical_issues)

    def test_invalid_active_unit_detected(self):
        p = _patient(1, "morgue")
        result = PatientValidator().validate([p], [], final_hour=1)
        assert any(i.check == "valid_active_unit" for i in result.critical_issues)

    def test_unique_terminal_outcome(self):
        p = _patient(1, "ed", terminal="WEIRD")
        result = PatientValidator().validate([p], [], final_hour=1)
        assert any(i.check == "unique_terminal_outcome" for i in result.critical_issues)