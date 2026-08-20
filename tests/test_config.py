import pytest
import yaml

from hfsg.config import ConfigurationLoader, ConfigError

BASE_CONFIG = "config/base.yaml"


def load_raw() -> dict:
    with open(BASE_CONFIG, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


@pytest.fixture()
def loader():
    return ConfigurationLoader()


@pytest.fixture()
def base_data():
    return load_raw()


def write_tmp(tmp_path, data: dict, name="config.yaml"):
    target = tmp_path / name
    with target.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle)
    return target


class TestValidConfiguration:
    def test_loads_base_yaml(self, loader):
        config = loader.load(BASE_CONFIG)
        assert config.name == "hfsg_balanced_synthetic_hospital_flow_model"
        assert config.time_step_hours == 1
        assert config.simulation_hours == 720

    def test_attribute_access(self, loader):
        config = loader.load(BASE_CONFIG)
        assert config.initial_conditions["ed_census"] == 20
        assert config.capacities["icu"] == 20
        assert config.batch["target_patient_records"] == 1000000

    def test_destination_shares_sum_to_one(self, loader):
        loader.load(BASE_CONFIG)


class TestValidations:
    def test_missing_section_rejected(self, loader, base_data, tmp_path):
        del base_data["model"]["validation"]
        with pytest.raises(ConfigError, match="Missing required configuration section"):
            loader.load(write_tmp(tmp_path, base_data))

    def test_missing_required_field_rejected(self, loader, base_data, tmp_path):
        del base_data["model"]["capacities"]["icu"]
        with pytest.raises(ConfigError, match="Missing required field"):
            loader.load(write_tmp(tmp_path, base_data))

    def test_unknown_section_rejected(self, loader, base_data, tmp_path):
        base_data["model"]["surprise_section"] = {}
        with pytest.raises(ConfigError, match="Unknown configuration section"):
            loader.load(write_tmp(tmp_path, base_data))

    def test_non_numeric_field_rejected(self, loader, base_data, tmp_path):
        base_data["model"]["capacities"]["ed"] = "many"
        with pytest.raises(ConfigError, match="must be numeric"):
            loader.load(write_tmp(tmp_path, base_data))

    def test_negative_value_rejected(self, loader, base_data, tmp_path):
        base_data["model"]["capacities"]["ed"] = -5
        with pytest.raises(ConfigError, match="non-negative"):
            loader.load(write_tmp(tmp_path, base_data))

    def test_non_positive_time_step_rejected(self, loader, base_data, tmp_path):
        base_data["model"]["time_step_hours"] = 0
        with pytest.raises(ConfigError, match="time_step_hours must be positive"):
            loader.load(write_tmp(tmp_path, base_data))

    def test_non_positive_simulation_hours_rejected(self, loader, base_data, tmp_path):
        base_data["model"]["simulation_hours"] = -1
        with pytest.raises(ConfigError, match="simulation_hours must be positive"):
            loader.load(write_tmp(tmp_path, base_data))

    def test_shares_not_summing_to_one_rejected(self, loader, base_data, tmp_path):
        base_data["model"]["destination_shares"]["specialty"] = 0.31
        with pytest.raises(ConfigError, match="must sum to 1"):
            loader.load(write_tmp(tmp_path, base_data))

    def test_initial_population_exceeds_capacity_rejected(self, loader, base_data, tmp_path):
        base_data["model"]["initial_conditions"]["icu_census"] = 999
        with pytest.raises(ConfigError, match="exceeds configured"):
            loader.load(write_tmp(tmp_path, base_data))

    def test_invalid_yaml_rejected(self, tmp_path):
        target = tmp_path / "bad.yaml"
        target.write_text("model: [unclosed", encoding="utf-8")
        with pytest.raises(ConfigError, match="Invalid YAML"):
            ConfigurationLoader().load(target)

    def test_missing_file_rejected(self, tmp_path):
        with pytest.raises(ConfigError, match="not found"):
            ConfigurationLoader().load(tmp_path / "does_not_exist.yaml")

    def test_negative_target_records_rejected(self, loader, base_data, tmp_path):
        base_data["model"]["batch"]["target_patient_records"] = -100
        with pytest.raises(ConfigError, match="positive integer"):
            loader.load(write_tmp(tmp_path, base_data))