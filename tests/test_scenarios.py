"""Step 8 tests: scenario definitions, effective configurations, overrides.

Covers: Standard-8 + CUSTOM definitions from configuration, the approved
override mappings (arrivals multiplier/wave, ICU capacity, discharge rates),
base configuration immutability, CUSTOM parameter limits and rejection of
invalid CUSTOM profiles, and configuration hashing.
"""

import numpy as np
import pytest
from hfsg.config import ConfigurationLoader
from hfsg.scenarios import (
    CUSTOM_SCENARIO_ID,
    ScenarioError,
    ScenarioManager,
    configuration_hash,
)

BASE = "config/base.yaml"


@pytest.fixture
def manager():
    return ScenarioManager(ConfigurationLoader().load(BASE))


@pytest.fixture
def base_data():
    return ConfigurationLoader().load(BASE).data


def _arrival_overrides(effective):
    return effective.data["arrivals"].get("overrides", {})


def _discharge_rates(effective):
    return effective.data["discharge_rates"]


def _icu_capacity(effective):
    return effective.data["capacities"]["icu"]


class TestScenarioPack:
    def test_standard_8_plus_custom_present(self, manager):
        ids = manager.scenario_ids()
        for sid in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", CUSTOM_SCENARIO_ID):
            assert sid in ids, sid

    def test_s1_has_identity_overrides(self, manager):
        eff = manager.effective_configuration("S1")
        overrides = _arrival_overrides(eff)
        assert overrides["arrivals_multiplier"] == pytest.approx(1.0)
        assert overrides["arrivals_wave"]["enabled"] is False

    def test_s2_arrivals_plus_20(self, manager):
        eff = manager.effective_configuration("S2")
        assert _arrival_overrides(eff)["arrivals_multiplier"] == pytest.approx(1.20)

    def test_s3_arrivals_plus_50(self, manager):
        eff = manager.effective_configuration("S3")
        assert _arrival_overrides(eff)["arrivals_multiplier"] == pytest.approx(1.50)

    def test_s4_icu_capacity_loss(self, manager, base_data):
        eff = manager.effective_configuration("S4")
        base_icu = base_data["capacities"]["icu"]
        assert _icu_capacity(eff) == pytest.approx(0.80 * base_icu)
        overrides = _arrival_overrides(eff)
        assert overrides["arrivals_multiplier"] == pytest.approx(1.0)

    def test_s5_discharge_reduction(self, manager, base_data):
        eff = manager.effective_configuration("S5")
        rates = _discharge_rates(eff)
        for unit, value in base_data["discharge_rates"].items():
            assert rates[unit] == pytest.approx(0.80 * value)

    def test_s6_arrivals_and_icu_loss(self, manager, base_data):
        eff = manager.effective_configuration("S6")
        assert _arrival_overrides(eff)["arrivals_multiplier"] == pytest.approx(1.20)
        assert _icu_capacity(eff) == pytest.approx(0.80 * base_data["capacities"]["icu"])

    def test_s7_wave_eighteen_hours(self, manager):
        eff = manager.effective_configuration("S7")
        wave = _arrival_overrides(eff)["arrivals_wave"]
        assert wave["enabled"] is True
        assert wave["factor"] == pytest.approx(2.0)
        assert wave["start_hour"] == 0
        assert wave["duration_hours"] == 48

    def test_s8_icu_and_discharge_increase(self, manager, base_data):
        eff = manager.effective_configuration("S8")
        base_icu = base_data["capacities"]["icu"]
        assert _icu_capacity(eff) == pytest.approx(1.20 * base_icu)
        rates = _discharge_rates(eff)
        for unit, value in base_data["discharge_rates"].items():
            assert rates[unit] == pytest.approx(1.20 * value)


class TestBaseConfigurationImmutability:
    def test_effective_does_not_mutate_base(self, manager, base_data):
        before = dict(base_data)
        for sid in manager.scenario_ids():
            manager.effective_configuration(sid)
        assert base_data == before

    def test_effective_is_copied(self, manager):
        eff = manager.effective_configuration("S2")
        eff.data["arrivals"]["overrides"]["arrivals_multiplier"] = 99.0
        again = manager.effective_configuration("S2")
        assert _arrival_overrides(again)["arrivals_multiplier"] == pytest.approx(1.20)


class TestCustomValidation:
    VALID = {
        "arrivals_multiplier": 1.25,
        "icu_capacity_multiplier": 1.0,
        "discharge_multiplier": 1.1,
    }

    def test_default_custom_profile_valid(self, manager):
        eff = manager.effective_configuration(CUSTOM_SCENARIO_ID)
        assert eff.data["arrivals"]["overrides"]["arrivals_multiplier"] == pytest.approx(1.25)

    def test_valid_custom_profile_ok(self, manager):
        manager.validate_custom(self.VALID)

    def test_rejects_out_of_range_arrivals(self, manager):
        bad = dict(self.VALID, arrivals_multiplier=5.0)
        with pytest.raises(ScenarioError):
            manager.validate_custom(bad)

    def test_rejects_out_of_range_icu(self, manager):
        bad = dict(self.VALID, icu_capacity_multiplier=2.0)
        with pytest.raises(ScenarioError):
            manager.validate_custom(bad)

    def test_rejects_out_of_range_discharge(self, manager):
        bad = dict(self.VALID, discharge_multiplier=7.5)
        with pytest.raises(ScenarioError):
            manager.validate_custom(bad)

    def test_rejects_unknown_key(self, manager):
        bad = dict(self.VALID, diagnosis="pneumonia")
        with pytest.raises(ScenarioError):
            manager.validate_custom(bad)

    def test_effective_config_revalidates(self, manager):
        eff = manager.effective_configuration(CUSTOM_SCENARIO_ID)
        assert configuration_hash(eff)


class TestS7WaveShape:
    def test_wave_applies_exactly_48_hours(self, base_data, manager):
        """arrival_rate must be doubled for hours 0..47 and baseline at 48+."""
        from hfsg.context import build_context
        from hfsg.engine import AggregateEngine

        ctx1 = build_context(manager.effective_configuration("S1"), scenario_id="S1")
        eff7 = manager.effective_configuration("S7")
        ctx7 = build_context(eff7, scenario_id="S7")
        rate1 = AggregateEngine(manager.effective_configuration("S1"), ctx1).arrival_rate
        rate7 = AggregateEngine(eff7, ctx7).arrival_rate
        for hour in range(48):
            assert rate7(hour) == pytest.approx(2.0 * rate1(hour)), hour
        for hour in (48, 49, 100, 719):
            assert rate7(hour) == pytest.approx(rate1(hour)), hour


class TestConfigurationHash:
    def test_hash_is_stable(self, manager):
        h1 = configuration_hash(manager.effective_configuration("S1"))
        h2 = configuration_hash(manager.effective_configuration("S1"))
        assert h1 == h2
        assert len(h1) == 64

    def test_hash_differs_across_scenarios(self, manager):
        h_s1 = configuration_hash(manager.effective_configuration("S1"))
        h_s2 = configuration_hash(manager.effective_configuration("S2"))
        assert h_s1 != h_s2

    def test_roundtrip_yaml_hash(self, manager, tmp_path):
        """base.yaml -> ConfigurationLoader -> yaml dump -> hash must equal."""
        from hfsg.scenarios import hash_yaml
        import yaml

        cfg = ConfigurationLoader().load(BASE)
        dumped = yaml.safe_dump(cfg.data, sort_keys=True)
        loaded_back = yaml.safe_load(dumped)
        assert hash_yaml(loaded_back) == hash_yaml(cfg.data)


class TestScenarioWording:
    def test_destination_shares_always_sum_one(self, manager):
        """Applying overrides must not break destination shares (invariant)."""
        for sid in manager.scenario_ids():
            eff = manager.effective_configuration(sid)
            shares = eff.data["destination_shares"]
            assert abs(sum(shares.values()) - 1.0) < 1e-9, sid