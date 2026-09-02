"""Tests for the Patient Generator (MODEL.md sections 13, 19, 20)."""

import numpy as np

from hfsg.patients import PatientGenerator
from helpers import make_config


def _make_generator(tmp_path, seed=123):
    config = make_config(tmp_path)
    return PatientGenerator(
        config,
        simulation_id="sim-test",
        scenario_id="S1",
        rng=np.random.default_rng(seed),
    )


INITIAL_STOCKS = {"ed": 20, "specialty": 25, "general": 60, "icu": 10}


class TestInitialPopulation:
    def test_exact_count(self, tmp_path):
        gen = _make_generator(tmp_path)
        patients = gen.create_initial_population(INITIAL_STOCKS, "2026-01-01T00:00:00+00:00")
        assert len(patients) == 115

    def test_entry_type_initial_and_unique_ids(self, tmp_path):
        gen = _make_generator(tmp_path)
        patients = gen.create_initial_population(INITIAL_STOCKS, "2026-01-01T00:00:00+00:00")
        assert all(p.entry_type == "INITIAL" for p in patients)
        ids = [p.patient_id for p in patients]
        assert len(set(ids)) == len(ids)

    def test_unit_count_distribution(self, tmp_path):
        gen = _make_generator(tmp_path)
        patients = gen.create_initial_population(INITIAL_STOCKS, "2026-01-01T00:00:00+00:00")
        counts = {}
        for p in patients:
            counts[p.current_unit] = counts.get(p.current_unit, 0) + 1
        assert counts == {"ed": 20, "specialty": 25, "general": 60, "icu": 10}

    def test_required_fields_present(self, tmp_path):
        gen = _make_generator(tmp_path)
        patients = gen.create_initial_population(INITIAL_STOCKS, "2026-01-01T00:00:00+00:00")
        p = patients[0]
        for attr in ("patient_id", "age_group", "sex", "severity_level",
                     "arrival_mode", "initial_unit", "entry_type", "arrival_datetime"):
            assert getattr(p, attr) is not None
        assert p.simulation_id == "sim-test"
        assert p.scenario_id == "S1"


class TestArrivals:
    def test_one_patient_per_admitted_arrival(self, tmp_path):
        gen = _make_generator(tmp_path)
        patients = gen.create_arrival_patients(5, hour=10, arrival_datetime="x")
        assert len(patients) == 5
        assert all(p.entry_type == "ARRIVAL" for p in patients)
        assert all(p.initial_unit == "ed" for p in patients)

    def test_arrival_ids_unique_across_initial_and_arrivals(self, tmp_path):
        gen = _make_generator(tmp_path)
        init = gen.create_initial_population(INITIAL_STOCKS, "t")
        arrivals = gen.create_arrival_patients(7, hour=1, arrival_datetime="t")
        ids = [p.patient_id for p in init] + [p.patient_id for p in arrivals]
        assert len(set(ids)) == len(ids)

    def test_zero_count_empty(self, tmp_path):
        gen = _make_generator(tmp_path)
        assert gen.create_arrival_patients(0, hour=1, arrival_datetime="t") == []


class TestAttributeSampling:
    def test_attributes_come_from_configured_categories(self, tmp_path):
        config = make_config(tmp_path)
        gen = PatientGenerator(config, simulation_id="s", scenario_id="S1",
                               rng=np.random.default_rng(1))
        patients = gen.create_initial_population(INITIAL_STOCKS, "t")
        ages = {p.age_group for p in patients}
        sexes = {p.sex for p in patients}
        sevs = {p.severity_level for p in patients}
        modes = {p.arrival_mode for p in patients}
        assert ages <= set(config.patient_attributes["age_group"]["categories"])
        assert sexes <= set(config.patient_attributes["sex"]["categories"])
        assert sevs <= set(config.patient_attributes["severity_level"]["categories"])
        assert modes <= set(config.patient_attributes["arrival_mode"]["categories"])

    def test_deterministic_same_seed(self, tmp_path):
        a = _make_generator(tmp_path, seed=9).create_initial_population(INITIAL_STOCKS, "t")
        b = _make_generator(tmp_path, seed=9).create_initial_population(INITIAL_STOCKS, "t")
        attrs_a = [(p.age_group, p.sex, p.severity_level, p.arrival_mode) for p in a]
        attrs_b = [(p.age_group, p.sex, p.severity_level, p.arrival_mode) for p in b]
        assert attrs_a == attrs_b

    def test_different_seed_differs(self, tmp_path):
        a = _make_generator(tmp_path, seed=9).create_initial_population(INITIAL_STOCKS, "t")
        b = _make_generator(tmp_path, seed=10).create_initial_population(INITIAL_STOCKS, "t")
        attrs_a = [(p.age_group, p.sex, p.severity_level, p.arrival_mode) for p in a]
        attrs_b = [(p.age_group, p.sex, p.severity_level, p.arrival_mode) for p in b]
        assert attrs_a != attrs_b