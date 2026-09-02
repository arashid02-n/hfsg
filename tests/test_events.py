"""Tests for the Patient Event Generator (MODEL.md sections 16, 21, 22)."""

import numpy as np
import pytest

from hfsg.events import (
    CRITICAL_RECONCILIATION_FAILURE,
    DISCHARGE_DESTINATION,
    EVENT_ARRIVAL,
    EVENT_DEATH,
    EVENT_DISCHARGE,
    EVENT_TRANSFER,
    PatientEventGenerator,
    SimulationClock,
)
from hfsg.patients import PatientGenerator
from helpers import make_config


def _mk_generators(tmp_path, seed=7):
    config = make_config(tmp_path)
    rng = np.random.default_rng(seed)
    gene = PatientGenerator(
        config, simulation_id="sim", scenario_id="S1", rng=rng
    )
    evgen = PatientEventGenerator(
        config, simulation_id="sim", scenario_id="S1", rng=rng
    )
    return gene, evgen, config


def _initial(gene):
    return gene.create_initial_population(
        {"ed": 20, "specialty": 25, "general": 60, "icu": 10},
        "2026-01-01T00:00:00+00:00",
    )


def _ed_patients(gene, n=6, arrivals_at=0):
    """Return n patients currently in ED (mix of arrival hours)."""
    patients = gene.create_arrival_patients(n, hour=arrivals_at, arrival_datetime="t")
    assert all(p.current_unit == "ed" for p in patients)
    return patients


class TestArrivalEvent:
    def test_initial_population_gets_arrival_events(self, tmp_path):
        gene, evgen, config = _mk_generators(tmp_path)
        patients = _initial(gene)
        clock = SimulationClock()
        events = evgen.process_timestep(patients, 0, {}, clock)
        arrivals = [e for e in events if e.event_type == EVENT_ARRIVAL]
        assert len(arrivals) == 115
        assert all(e.to_unit == p.initial_unit for e, p in zip(arrivals, patients) if e.patient_id == p.patient_id)

    def test_event_fields(self, tmp_path):
        gene, evgen, config = _mk_generators(tmp_path)
        patients = _ed_patients(gene, n=1, arrivals_at=0)
        clock = SimulationClock()
        events = evgen.process_timestep(patients, 0, {}, clock)
        ev = events[0]
        assert ev.event_type == EVENT_ARRIVAL
        assert ev.from_unit == "external"
        assert ev.to_unit == "ed"
        assert ev.event_id == 1
        assert ev.patient_id == patients[0].patient_id
        assert ev.simulation_id == "sim"
        assert ev.scenario_id == "S1"


class TestTimestepEligibility:
    def test_patients_arriving_now_not_eligible_for_movement(self, tmp_path):
        gene, evgen, config = _mk_generators(tmp_path)
        # One patient arrives at hour 4, one at hour 5. At hour 5 the hour-5
        # arrival is ineligible; a quota for ED must move only the hour-4 one.
        earlier = gene.create_arrival_patients(1, hour=4, arrival_datetime="t")[0]
        now = gene.create_arrival_patients(1, hour=5, arrival_datetime="t")[0]
        patients = [earlier, now]
        clock = SimulationClock()
        quotas = {"T_EG": 1}
        events = evgen.process_timestep(patients, 5, quotas, clock)
        transfers = [e for e in events if e.event_type == EVENT_TRANSFER]
        assert len(transfers) == 1
        assert transfers[0].patient_id == earlier.patient_id
        assert now.current_unit == "ed"  # just-arrived must not have moved

    def test_patients_arriving_now_can_move_next_hour(self, tmp_path):
        gene, evgen, config = _mk_generators(tmp_path)
        patients = gene.create_arrival_patients(2, hour=5, arrival_datetime="t")
        clock = SimulationClock()
        quotas = {"T_EG": 1}
        events = evgen.process_timestep(patients, 6, quotas, clock)
        transfers = [e for e in events if e.event_type == EVENT_TRANSFER]
        assert len(transfers) == 1
        assert transfers[0].from_unit == "ed"
        assert transfers[0].to_unit == "general"


class TestSelectionRules:
    def test_ed_non_icu_is_fifo(self, tmp_path):
        gene, evgen, config = _mk_generators(tmp_path)
        # Arrival hours: patient A at hour 1, B at hour 2, C at hour 3.
        a = gene.create_arrival_patients(1, hour=1, arrival_datetime="t")[0]
        b = gene.create_arrival_patients(1, hour=2, arrival_datetime="t")[0]
        c = gene.create_arrival_patients(1, hour=3, arrival_datetime="t")[0]
        patients = [a, b, c]
        clock = SimulationClock()
        quotas = {"T_EG": 2}
        events = evgen.process_timestep(patients, 4, quotas, clock)
        transfers = [e for e in events if e.event_type == EVENT_TRANSFER]
        moved = [e.patient_id for e in transfers]
        # FIFO: oldest (A=hour1) then next (B=hour2).
        assert moved == [a.patient_id, b.patient_id]

    def test_icu_priority_by_severity(self, tmp_path):
        gene, evgen, config = _mk_generators(tmp_path)
        # Create 3 specialty patients with known severities by overriding.
        low = gene.create_arrival_patients(1, hour=1, arrival_datetime="t")[0]
        high = gene.create_arrival_patients(1, hour=1, arrival_datetime="t")[0]
        med = gene.create_arrival_patients(1, hour=1, arrival_datetime="t")[0]
        low.severity_level = "Low"
        high.severity_level = "Critical"
        med.severity_level = "Medium"
        for p in (low, high, med):
            p.current_unit = "specialty"
        patients = [low, high, med]
        clock = SimulationClock()
        quotas = {"T_CI": 1}
        events = evgen.process_timestep(patients, 4, quotas, clock)
        transfers = [e for e in events if e.event_type == EVENT_TRANSFER]
        assert len(transfers) == 1
        assert transfers[0].patient_id == high.patient_id  # highest severity

    def test_discharge_longest_stay_first(self, tmp_path):
        gene, evgen, config = _mk_generators(tmp_path)
        old = gene.create_arrival_patients(1, hour=1, arrival_datetime="t")[0]
        new = gene.create_arrival_patients(1, hour=3, arrival_datetime="t")[0]
        old.current_unit = "general"
        new.current_unit = "general"
        patients = [old, new]
        clock = SimulationClock()
        quotas = {"D_G": 1}
        events = evgen.process_timestep(patients, 5, quotas, clock)
        discharges = [e for e in events if e.event_type == EVENT_DISCHARGE]
        assert len(discharges) == 1
        assert discharges[0].patient_id == old.patient_id  # longest stay

    def test_death_weighted_selection(self, tmp_path):
        gene, evgen, config = _mk_generators(tmp_path)
        severe_icu = gene.create_arrival_patients(1, hour=1, arrival_datetime="t")[0]
        mild = gene.create_arrival_patients(1, hour=1, arrival_datetime="t")[0]
        severe_icu.severity_level = "Critical"
        severe_icu.current_unit = "icu"
        mild.severity_level = "Low"
        mild.current_unit = "general"
        patients = [severe_icu, mild]
        clock = SimulationClock()
        quotas = {"M_I": 1}
        events = evgen.process_timestep(patients, 5, quotas, clock)
        deaths = [e for e in events if e.event_type == EVENT_DEATH]
        assert len(deaths) == 1
        assert deaths[0].patient_id == severe_icu.patient_id
        assert deaths[0].to_unit == "deceased"


class TestQuotaAuthority:
    def test_event_generator_cannot_exceed_quota(self, tmp_path):
        gene, evgen, config = _mk_generators(tmp_path)
        patients = gene.create_arrival_patients(4, hour=1, arrival_datetime="t")
        clock = SimulationClock()
        quotas = {"T_EG": 2}
        events = evgen.process_timestep(patients, 3, quotas, clock)
        transfers = [e for e in events if e.event_type == EVENT_TRANSFER]
        assert len(transfers) == 2  # exactly the quota, no more

    def test_raises_when_quota_not_satisfiable(self, tmp_path):
        gene, evgen, config = _mk_generators(tmp_path)
        patients = gene.create_arrival_patients(1, hour=1, arrival_datetime="t")
        clock = SimulationClock()
        quotas = {"T_EG": 5}  # only 1 ED patient
        with pytest.raises(CRITICAL_RECONCILIATION_FAILURE):
            evgen.process_timestep(patients, 3, quotas, clock)


class TestPatientStateUpdates:
    def test_transfer_updates_current_unit(self, tmp_path):
        gene, evgen, config = _mk_generators(tmp_path)
        p = gene.create_arrival_patients(1, hour=1, arrival_datetime="t")[0]
        patients = [p]
        clock = SimulationClock()
        evgen.process_timestep(patients, 3, {"T_EG": 1}, clock)
        assert p.current_unit == "general"

    def test_terminal_patient_not_moved_again(self, tmp_path):
        gene, evgen, config = _mk_generators(tmp_path)
        p = gene.create_arrival_patients(1, hour=1, arrival_datetime="t")[0]
        p.current_unit = "general"
        patients = [p]
        clock = SimulationClock()
        evgen.process_timestep(patients, 3, {"D_G": 1}, clock)
        assert p.terminal_event == EVENT_DISCHARGE
        # A fresh arrival at hour 4 in general ward; the terminal patient is
        # excluded from selection. A discharge quota must pick the new one.
        p2 = gene.create_arrival_patients(1, hour=4, arrival_datetime="t")[0]
        p2.current_unit = "general"
        patients.append(p2)
        evgen.process_timestep(patients, 5, {"D_G": 1}, clock)
        assert p.terminal_event == EVENT_DISCHARGE          # unchanged
        assert p2.terminal_event == EVENT_DISCHARGE         # new one discharged
        assert p2.current_unit == "general"