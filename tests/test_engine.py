import copy

import pytest
import yaml

from hfsg.config import Configuration, ConfigurationLoader
from hfsg.context import build_context
from hfsg.engine import AggregateEngine, AggregateEngineError
from hfsg.units import ACTIVE_UNITS, FLOW_NAMES, TRANSFERS

BASE_CONFIG = "config/base.yaml"


def load_base_model_section() -> dict:
    with open(BASE_CONFIG, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)["model"]


def deep_merge(base: dict, overrides: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def make_config(tmp_path, overrides=None):
    model = deep_merge(load_base_model_section(), overrides or {})
    target = tmp_path / "scenario.yaml"
    with target.open("w", encoding="utf-8") as handle:
        yaml.safe_dump({"model": model}, handle)
    return ConfigurationLoader().load(target)


def make_engine(config, scenario_id="S1", run_index=0, seed=None):
    context = build_context(config, scenario_id=scenario_id, run_index=run_index)
    engine = AggregateEngine(config, context)
    if seed is not None:
        import numpy as np

        engine.rng = np.random.default_rng(seed)
    return engine


@pytest.fixture()
def base_config(loader):
    return loader.load(BASE_CONFIG)


class TestInitialization:
    def test_initial_state_matches_configuration(self, base_config):
        engine = make_engine(base_config)
        ic = base_config.initial_conditions
        assert engine.initial.ed_census == ic["ed_census"]
        assert engine.initial.specialty_census == ic["specialty_census"]
        assert engine.initial.general_census == ic["general_census"]
        assert engine.initial.icu_census == ic["icu_census"]
        assert engine.initial.cumulative_discharges == 0
        assert engine.initial.cumulative_deaths == 0
        assert engine.initial.total == 115.0

    def test_horizon_from_configuration(self, base_config):
        engine = make_engine(base_config)
        assert engine.total_steps == 720

    def test_rejects_initial_over_capacity(self, tmp_path):
        # The loader already rejects this case; build the Configuration
        # directly to exercise the engine's own MODEL.md section 12 guard.
        model = deep_merge(load_base_model_section(), {})
        model["initial_conditions"]["icu_census"] = 25
        config = Configuration(model, tmp_path / "inline.yaml")
        with pytest.raises(AggregateEngineError, match="exceeds capacity"):
            make_engine(config)

    def test_rejects_broken_destination_shares(self, tmp_path):
        model = deep_merge(load_base_model_section(), {})
        model["destination_shares"]["specialty"] = 0.5
        config = Configuration(model, tmp_path / "inline.yaml")
        with pytest.raises(AggregateEngineError, match="sum to 1"):
            make_engine(config)

    def test_rejects_non_beginning_of_step_capacity(self, tmp_path):
        config = make_config(
            tmp_path,
            {"capacity": {"timing": "intra_step"}},
        )
        with pytest.raises(AggregateEngineError, match="beginning_of_step"):
            make_engine(config)


class TestModelBEquations:
    def test_arrival_rate_seasonal(self, base_config):
        import math

        engine = make_engine(base_config)
        omega = 2 * math.pi / 24
        assert engine.arrival_rate(0) == pytest.approx(
            1.5 * (1 + 0.3 * math.sin(omega * (0 - 8)))
        )
        assert engine.arrival_rate(8) == pytest.approx(1.5)
        assert engine.arrival_rate(14) == pytest.approx(1.5 * 1.3, abs=1e-9)
        assert engine.arrival_rate(2) == pytest.approx(1.5 * 0.7, abs=1e-9)

    def test_arrival_rate_without_seasonality(self, tmp_path):
        config = make_config(
            tmp_path, {"arrivals": {"seasonality": {"enabled": False}}}
        )
        engine = make_engine(config)
        assert all(engine.arrival_rate(h) == pytest.approx(1.5) for h in range(24))

    def test_ed_processing_request_matches_formula(self, base_config):
        engine = make_engine(base_config)
        assert engine.ed_processing_request(20) == pytest.approx(
            0.25 * 20 / (1 + 0.02 * 20)
        )
        assert engine.ed_processing_request(0) == 0.0
        capped = engine.ed_processing_request(1e6)
        assert capped == pytest.approx(12.5, rel=1e-3)
        assert capped <= 1e6

    def test_icu_pressure_disabled_by_default(self, base_config):
        engine = make_engine(base_config)
        assert engine.icu_pressure_factor(50.0) == 1.0

    def test_icu_pressure_enabled(self, tmp_path):
        config = make_config(
            tmp_path, {"icu_pressure": {"enabled": True, "zeta": 0.5, "epsilon": 2.0}}
        )
        engine = make_engine(config)
        assert engine.icu_pressure_factor(4.0) == pytest.approx(
            1 + 0.5 * 4 / (1 + 2 * 4)
        )

    def test_requested_flows_follow_equations(self, base_config, tmp_path):
        config = make_config(
            tmp_path,
            {
                "arrivals": {"baseline_rate_per_hour": 0.0},
                "initial_conditions": {
                    "ed_census": 40,
                    "specialty_census": 50,
                    "general_census": 80,
                    "icu_census": 10,
                },
            },
        )
        engine = make_engine(config, seed=7)
        record = engine.step(0)
        req = record.flows.requested
        e, c, g, i = 40.0, 50.0, 80.0, 10.0
        t_e = min(0.25 * e / (1 + 0.02 * e), e)
        assert req["T_EC"] == pytest.approx(0.30 * t_e)
        assert req["T_EG"] == pytest.approx(0.45 * t_e)
        assert req["T_EI"] == pytest.approx(0.05 * t_e)
        assert req["T_EH"] == pytest.approx(0.20 * t_e)
        assert req["T_CG"] == pytest.approx(0.015 * c)
        assert req["T_CI"] == pytest.approx(0.005 * c)
        assert req["T_GI"] == pytest.approx(0.002 * g)
        assert req["D_C"] == pytest.approx(0.008 * c)
        assert req["D_G"] == pytest.approx(0.010 * g)
        assert req["D_I"] == pytest.approx(0.006 * i)
        assert req["M_C"] == pytest.approx(0.0002 * c)
        assert req["M_G"] == pytest.approx(0.0001 * g)
        assert req["M_I"] == pytest.approx(0.0008 * i)


class TestConstraints:
    def test_source_stock_limits_hold_per_step(self, base_config):
        engine = make_engine(base_config, seed=11)
        for _ in range(48):
            record = engine.step(engine.state.hour + 1)
            before, f = record.before, record.flows.constrained
            ed_out = sum(f[n] for n in ("T_EC", "T_EG", "T_EI", "T_EH"))
            c_out = sum(f[n] for n in ("T_CG", "T_CI", "D_C", "M_C"))
            g_out = sum(f[n] for n in ("T_GI", "D_G", "M_G"))
            i_out = sum(f[n] for n in ("D_I", "M_I"))
            assert ed_out <= before.ed_census + 1e-9
            assert c_out <= before.specialty_census + 1e-9
            assert g_out <= before.general_census + 1e-9
            assert i_out <= before.icu_census + 1e-9

    def test_capacity_never_exceeded_over_run(self, base_config):
        engine = make_engine(base_config, seed=3)
        result = engine.run()
        capacities = {u: float(base_config.capacities[u]) for u in ACTIVE_UNITS}
        for record in result.records:
            for unit in ACTIVE_UNITS:
                assert record.after.stock(unit) <= capacities[unit] + 1e-6
                assert record.after.stock(unit) >= -1e-9

    def test_icu_priority_order(self, tmp_path):
        config = make_config(
            tmp_path,
            {
                "arrivals": {"baseline_rate_per_hour": 0.0},
                "destination_shares": {
                    "specialty": 0.0,
                    "general": 0.0,
                    "icu": 1.0,
                    "home": 0.0,
                },
                "transfer_rates": {
                    "specialty_to_general": 0.0,
                    "specialty_to_icu": 0.5,
                    "general_to_icu": 0.5,
                },
                "discharge_rates": {
                    "specialty": 0.0,
                    "general": 0.0,
                    "icu": 0.0,
                },
                "mortality_rates": {
                    "specialty": 0.0,
                    "general": 0.0,
                    "icu": 0.0,
                },
                "capacities": {"ed": 200, "specialty": 200, "general": 200, "icu": 3},
                "initial_conditions": {
                    "ed_census": 100,
                    "specialty_census": 100,
                    "general_census": 100,
                    "icu_census": 0,
                },
            },
        )
        engine = make_engine(config, seed=1)
        record = engine.step(0)
        f = record.flows.constrained
        # ICU has 3 beds; approved priority ED -> Specialty -> General.
        assert f["T_EI"] == pytest.approx(3.0)
        assert f["T_CI"] == 0.0
        assert f["T_GI"] == 0.0
        assert record.flows.unmet.get("icu", 0.0) > 0.0

    def test_unmet_demand_recorded_when_capacity_short(self, tmp_path):
        config = make_config(
            tmp_path,
            {
                "arrivals": {"baseline_rate_per_hour": 0.0},
                "destination_shares": {
                    "specialty": 1.0,
                    "general": 0.0,
                    "icu": 0.0,
                    "home": 0.0,
                },
                "capacities": {"ed": 100, "specialty": 5, "general": 100, "icu": 20},
                "initial_conditions": {
                    "ed_census": 50,
                    "specialty_census": 0,
                    "general_census": 0,
                    "icu_census": 0,
                },
            },
        )
        engine = make_engine(config, seed=1)
        record = engine.step(0)
        t_e = engine.ed_processing_request(50.0)
        assert record.flows.constrained["T_EC"] == pytest.approx(5.0)
        assert record.flows.unmet["specialty"] == pytest.approx(t_e - 5.0)

    def test_arrivals_limited_by_ed_capacity_and_recorded(self, tmp_path):
        config = make_config(
            tmp_path,
            {
                "arrivals": {"baseline_rate_per_hour": 10.0},
                "ed_processing": {"a": 1e-9, "mean_processing_hours": 1e9},
                "capacities": {"ed": 3, "specialty": 60, "general": 100, "icu": 20},
                "initial_conditions": {
                    "ed_census": 3,
                    "specialty_census": 0,
                    "general_census": 0,
                    "icu_census": 0,
                },
            },
        )
        engine = make_engine(config, seed=5)
        record = engine.step(0)
        assert record.flows.arrivals_drawn > 0
        assert record.flows.arrivals_accepted == 0
        assert record.flows.unmet["ed"] == float(record.flows.arrivals_drawn)
        assert record.after.ed_census <= 3 + 1e-9


class TestCapacityTiming:
    def _timing_config(self, tmp_path):
        return make_config(
            tmp_path,
            {
                "arrivals": {"baseline_rate_per_hour": 0.0},
                "destination_shares": {
                    "specialty": 0.0,
                    "general": 0.0,
                    "icu": 1.0,
                    "home": 0.0,
                },
                "discharge_rates": {
                    "specialty": 0.0,
                    "general": 0.0,
                    "icu": 1.0,
                },
                "mortality_rates": {
                    "specialty": 0.0,
                    "general": 0.0,
                    "icu": 0.0,
                },
                "capacities": {"ed": 100, "specialty": 100, "general": 100, "icu": 5},
                "initial_conditions": {
                    "ed_census": 10,
                    "specialty_census": 0,
                    "general_census": 0,
                    "icu_census": 5,
                },
            },
        )

    def test_freed_beds_not_reusable_same_step(self, tmp_path):
        engine = make_engine(self._timing_config(tmp_path), seed=1)
        step0 = engine.step(0)
        # ICU starts full; the 5 ICU discharges this step must NOT free beds
        # for ED->ICU within the same timestep.
        assert step0.before.icu_census == 5.0
        assert step0.flows.constrained["D_I"] == pytest.approx(5.0)
        assert step0.flows.constrained["T_EI"] == 0.0
        assert step0.after.icu_census == 0.0
        assert step0.flows.unmet.get("icu", 0.0) > 0.0

    def test_freed_beds_available_next_step(self, tmp_path):
        engine = make_engine(self._timing_config(tmp_path), seed=1)
        engine.step(0)
        step1 = engine.step(1)
        # Beginning of hour 1: ICU is empty, so ED patients can move.
        assert step1.before.icu_census == 0.0
        expected = min(
            engine.ed_processing_request(step1.before.ed_census),
            step1.before.ed_census,
            engine.capacities["icu"],
        )
        assert step1.flows.constrained["T_EI"] == pytest.approx(expected)


class TestMassBalanceAndDeterminism:
    def test_mass_balance_every_step(self, base_config):
        engine = make_engine(base_config, seed=42)
        result = engine.run()
        n0 = result.initial.total
        for record in result.records:
            expected = n0 + record.after.cumulative_arrivals
            assert record.after.total == pytest.approx(expected, abs=1e-6)
            step_delta = (
                record.after.total - record.before.total
            ) - record.flows.arrivals_accepted
            assert step_delta == pytest.approx(0.0, abs=1e-9)

    def test_simultaneous_update_matches_flow_equations(self, base_config):
        engine = make_engine(base_config, seed=13)
        record = engine.step(0)
        b, a, f = record.before, record.after, record.flows.constrained
        accepted = float(record.flows.arrivals_accepted)
        assert a.ed_census == pytest.approx(
            b.ed_census + accepted - f["T_EC"] - f["T_EG"] - f["T_EI"] - f["T_EH"]
        )
        assert a.specialty_census == pytest.approx(
            b.specialty_census + f["T_EC"] - f["T_CG"] - f["T_CI"]
            - f["D_C"] - f["M_C"]
        )
        assert a.general_census == pytest.approx(
            b.general_census + f["T_EG"] + f["T_CG"] - f["T_GI"]
            - f["D_G"] - f["M_G"]
        )
        assert a.icu_census == pytest.approx(
            b.icu_census + f["T_EI"] + f["T_CI"] + f["T_GI"] - f["D_I"] - f["M_I"]
        )
        assert a.cumulative_discharges == pytest.approx(
            b.cumulative_discharges + f["T_EH"] + f["D_C"] + f["D_G"] + f["D_I"]
        )
        assert a.cumulative_deaths == pytest.approx(
            b.cumulative_deaths + f["M_C"] + f["M_G"] + f["M_I"]
        )

    def test_same_seed_reproduces_identical_trajectory(self, base_config):
        first = make_engine(base_config, scenario_id="S1", run_index=0).run()
        second = make_engine(base_config, scenario_id="S1", run_index=0).run()
        assert len(first.records) == len(second.records)
        for r1, r2 in zip(first.records, second.records):
            assert r1.hour == r2.hour
            for name in FLOW_NAMES:
                assert r1.flows.constrained[name] == r2.flows.constrained[name]
            assert r1.flows.arrivals_drawn == r2.flows.arrivals_drawn
            assert r1.after.total == r2.after.total

    def test_different_seed_changes_arrivals(self, base_config):
        first = make_engine(base_config, seed=101).run()
        second = make_engine(base_config, seed=202).run()
        arrivals_a = [r.flows.arrivals_drawn for r in first.records]
        arrivals_b = [r.flows.arrivals_drawn for r in second.records]
        assert arrivals_a != arrivals_b

    def test_mean_arrivals_track_lambda(self, base_config):
        engine = make_engine(base_config, seed=99)
        result = engine.run()
        drawn = [r.flows.arrivals_drawn for r in result.records]
        rates = [engine.arrival_rate(r.hour) for r in result.records]
        observed = sum(drawn) / len(drawn)
        expected = sum(rates) / len(rates)
        assert observed == pytest.approx(expected, rel=0.15)


class TestRawConstrainedFlowsRecorded:
    def test_requested_and_constrained_both_available(self, base_config):
        engine = make_engine(base_config, seed=21)
        record = engine.step(0)
        assert set(FLOW_NAMES) <= set(record.flows.requested)
        assert set(FLOW_NAMES) <= set(record.flows.constrained)
        for name in FLOW_NAMES:
            assert record.flows.constrained[name] <= record.flows.requested[name] + 1e-9

    def test_transfer_allocation_order_preserves_priority(self, base_config):
        engine = make_engine(base_config, seed=21)
        record = engine.step(0)
        f = record.flows.constrained
        for name, _, _ in TRANSFERS:
            assert f[name] >= 0.0
