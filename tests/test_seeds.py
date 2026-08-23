import pytest

from hfsg.context import SimulationContext, build_context
from hfsg.seeds import CHILD_SEED_ALGORITHM_VERSION, derive_child_seed


class TestChildSeedDerivation:
    def test_deterministic(self):
        a = derive_child_seed(20260805, "S1", 0)
        b = derive_child_seed(20260805, "S1", 0)
        assert a == b

    def test_differs_by_run_index(self):
        assert derive_child_seed(20260805, "S1", 0) != derive_child_seed(
            20260805, "S1", 1
        )

    def test_differs_by_scenario(self):
        assert derive_child_seed(20260805, "S1", 0) != derive_child_seed(
            20260805, "S2", 0
        )

    def test_differs_by_master_seed(self):
        assert derive_child_seed(1, "S1", 0) != derive_child_seed(2, "S1", 0)

    def test_seed_in_63_bit_range(self):
        for run_index in range(50):
            seed = derive_child_seed(20260805, "S1", run_index)
            assert 0 <= seed < (1 << 63)

    def test_accepts_string_master_seed(self):
        assert derive_child_seed("abc", "S1", 0) == derive_child_seed(
            "abc", "S1", 0
        )

    def test_negative_run_index_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            derive_child_seed(20260805, "S1", -1)

    def test_empty_scenario_rejected(self):
        with pytest.raises(ValueError, match="scenario_id"):
            derive_child_seed(20260805, "", 0)

    def test_algorithm_version_is_recorded(self):
        assert CHILD_SEED_ALGORITHM_VERSION == "hfsg-child-seed-v1"


class TestSimulationContext:
    def test_fields_recorded(self):
        context = SimulationContext(
            scenario_id="S1",
            run_index=3,
            master_seed=42,
            child_seed=99,
            model_version="1.0",
            configuration_version="1.0",
        )
        assert context.scenario_id == "S1"
        assert context.run_index == 3
        assert context.child_seed == 99

    def test_unique_simulation_ids(self):
        one = SimulationContext("S1", 0, 1, 2, "1.0", "1.0")
        two = SimulationContext("S1", 0, 1, 2, "1.0", "1.0")
        assert one.simulation_id != two.simulation_id

    def test_build_context_derives_child_seed(self, loader):
        config = loader.load("config/base.yaml")
        context = build_context(config, scenario_id="S7", run_index=5)
        assert context.master_seed == config.reproducibility["master_seed"]
        expected = derive_child_seed(context.master_seed, "S7", 5)
        assert context.child_seed == expected
        assert context.model_version == "1.0"
