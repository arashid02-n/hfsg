"""Configuration loader for HFSG.

Loads and validates the approved YAML configuration. This module contains no
simulation logic (ARCHITECTURE.md section 3.1).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import yaml

DEFAULT_MASS_BALANCE_TOLERANCE = 1.0e-9

CONFIG_ROOT_KEY = "model"

SECTIONS = (
    "name",
    "version",
    "document_status",
    "time_unit",
    "time_step_hours",
    "simulation_hours",
    "primary_data_label",
    "initial_conditions",
    "initial_patient_population",
    "capacities",
    "arrivals",
    "ed_processing",
    "destination_shares",
    "transfer_rates",
    "discharge_rates",
    "mortality_rates",
    "icu_pressure",
    "capacity",
    "integerization",
    "patient_selection",
    "patient_attributes",
    "batch",
    "reproducibility",
    "validation",
    "output",
    "scenarios",
)

REQUIRED_SECTIONS = (
    "name",
    "version",
    "time_unit",
    "time_step_hours",
    "simulation_hours",
    "initial_conditions",
    "capacities",
    "destination_shares",
    "validation",
    "output",
)

REQUIRED_FIELDS: Dict[str, tuple[str, ...]] = {
    "initial_conditions": (
        "ed_census",
        "specialty_census",
        "general_census",
        "icu_census",
        "cumulative_discharges",
        "cumulative_deaths",
    ),
    "capacities": ("ed", "specialty", "general", "icu"),
    "destination_shares": ("specialty", "general", "icu", "home"),
}

NON_NEGATIVE_FIELDS: Dict[str, tuple[str, ...]] = {
    "initial_conditions": (
        "ed_census",
        "specialty_census",
        "general_census",
        "icu_census",
        "cumulative_discharges",
        "cumulative_deaths",
    ),
    "capacities": ("ed", "specialty", "general", "icu"),
    "destination_shares": ("specialty", "general", "icu", "home"),
}

CAPACITY_UNITS = ("ed", "specialty", "general", "icu")

STANDARD_SCENARIOS = ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8")

# Configurable scenario override keys (Step 8). Flat keys on each scenario.
# ``arrivals_wave`` is a temporal override: arrivals are multiplied by
# ``factor`` for exactly the [start_hour, start_hour + duration_hours) window.
SCENARIO_PARAMETER_KEYS = (
    "arrivals_multiplier",
    "arrivals_wave",
    "icu_capacity_multiplier",
    "discharge_multiplier",
)

# Numeric bounds for the CUSTOM scenario (approved ranges).
CUSTOM_LIMIT_FIELDS = (
    "arrivals_multiplier",
    "icu_capacity_multiplier",
    "discharge_multiplier",
)


class ConfigError(ValueError):
    """Raised when a configuration file is invalid."""


class Configuration:
    """Validated HFSG configuration.

    Wraps the approved configuration root and exposes its sections as
    attributes (e.g. ``config.capacities``, ``config.batch``).
    """

    def __init__(self, data: Dict[str, Any], source: Path) -> None:
        self._data = data
        self.source = source

    def __getattr__(self, name: str) -> Any:
        try:
            return self._data[name]
        except KeyError as exc:
            raise AttributeError(
                f"Configuration has no section {name!r}"
            ) from exc

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    @property
    def data(self) -> Dict[str, Any]:
        return self._data

    @property
    def time_step_hours(self) -> float:
        return float(self._data["time_step_hours"])

    @property
    def simulation_hours(self) -> float:
        return float(self._data["simulation_hours"])

    @property
    def mass_balance_tolerance(self) -> float:
        tolerance = self._data.get("validation", {}).get(
            "mass_balance_tolerance", DEFAULT_MASS_BALANCE_TOLERANCE
        )
        return float(tolerance)

    def __repr__(self) -> str:
        return f"Configuration(source={self.source})"


class ConfigurationLoader:
    """Loads and validates HFSG YAML configuration files."""

    def __init__(self) -> None:
        self._share_tolerance = DEFAULT_MASS_BALANCE_TOLERANCE

    def load(self, path: str | Path) -> Configuration:
        config_path = Path(path)
        if not config_path.is_file():
            raise ConfigError(f"Configuration file not found: {config_path}")

        try:
            with config_path.open("r", encoding="utf-8") as handle:
                raw = yaml.safe_load(handle)
        except yaml.YAMLError as exc:
            raise ConfigError(f"Invalid YAML in {config_path}: {exc}") from exc

        if not isinstance(raw, dict):
            raise ConfigError(
                f"Configuration root must be a mapping, got {type(raw).__name__}"
            )

        if CONFIG_ROOT_KEY not in raw:
            raise ConfigError(
                f"Missing configuration root section {CONFIG_ROOT_KEY!r}"
            )
        data = raw[CONFIG_ROOT_KEY]
        if not isinstance(data, dict):
            raise ConfigError(
                f"Configuration section {CONFIG_ROOT_KEY!r} must be a mapping, "
                f"got {type(data).__name__}"
            )

        return self.from_data(data, source=config_path)

    def from_data(
        self, data: Dict[str, Any], source: str | Path = "inline"
    ) -> Configuration:
        """Validate an already-parsed model dictionary into a Configuration.

        Used to build effective (base + override) configurations per scenario
        without re-reading YAML. ``data`` must be the ``model`` root mapping.
        """
        if not isinstance(data, dict):
            raise ConfigError(
                f"Configuration must be a mapping, got {type(data).__name__}"
            )

        self._validate_sections(data)
        self._validate_required_fields(data)
        self._validate_types(data)
        self._validate_non_negative(data)
        self._validate_time_step(data)
        self._validate_destination_shares(data)
        self._validate_initial_population_vs_capacity(data)
        self._validate_patient_attributes(data)
        self._validate_batch(data)
        self._validate_scenarios(data)

        return Configuration(data, Path(source))

    def _validate_sections(self, data: Dict[str, Any]) -> None:
        unknown = [s for s in data if s not in SECTIONS]
        if unknown:
            raise ConfigError(f"Unknown configuration section(s): {unknown}")
        missing = [s for s in REQUIRED_SECTIONS if s not in data]
        if missing:
            raise ConfigError(f"Missing required configuration section(s): {missing}")

    def _validate_required_fields(self, data: Dict[str, Any]) -> None:
        for section, fields in REQUIRED_FIELDS.items():
            present = data.get(section, {})
            missing = [f for f in fields if f not in present]
            if missing:
                raise ConfigError(
                    f"Missing required field(s) in section {section!r}: {missing}"
                )

    def _validate_types(self, data: Dict[str, Any]) -> None:
        for section, fields in NON_NEGATIVE_FIELDS.items():
            for field in fields:
                value = data[section][field]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ConfigError(
                        f"Field {section}.{field} must be numeric, got "
                        f"{type(value).__name__}"
                    )

    def _validate_non_negative(self, data: Dict[str, Any]) -> None:
        for section, fields in NON_NEGATIVE_FIELDS.items():
            for field in fields:
                value = data[section][field]
                if value < 0:
                    raise ConfigError(
                        f"Field {section}.{field} must be non-negative, got {value}"
                    )

    def _validate_time_step(self, data: Dict[str, Any]) -> None:
        time_step = data["time_step_hours"]
        simulation = data["simulation_hours"]
        if time_step <= 0:
            raise ConfigError(f"time_step_hours must be positive, got {time_step}")
        if simulation <= 0:
            raise ConfigError(f"simulation_hours must be positive, got {simulation}")

    def _validate_destination_shares(self, data: Dict[str, Any]) -> None:
        shares = data["destination_shares"]
        total = sum(float(shares[k]) for k in ("specialty", "general", "icu", "home"))
        if abs(total - 1.0) > self._share_tolerance:
            raise ConfigError(
                f"destination_shares must sum to 1 within tolerance "
                f"{self._share_tolerance}, got {total}"
            )

    def _validate_initial_population_vs_capacity(
        self, data: Dict[str, Any]
    ) -> None:
        initial = data["initial_conditions"]
        capacities = data["capacities"]
        for unit in CAPACITY_UNITS:
            census = initial[f"{unit}_census"]
            capacity = capacities[unit]
            if census > capacity:
                raise ConfigError(
                    f"initial {unit}_census ({census}) exceeds configured "
                    f"{unit} capacity ({capacity})"
                )

    def _validate_patient_attributes(self, data: Dict[str, Any]) -> None:
        patient_attributes = data.get("patient_attributes", {})
        for attr in ("age_group", "sex", "severity_level", "arrival_mode"):
            spec = patient_attributes.get(attr)
            if spec is None:
                raise ConfigError(
                    f"patient_attributes.{attr} must be configured"
                )
            categories = spec.get("categories")
            probabilities = spec.get("probabilities")
            if (
                not isinstance(categories, list)
                or not categories
                or not all(isinstance(c, str) for c in categories)
            ):
                raise ConfigError(
                    f"patient_attributes.{attr}.categories must be a "
                    "non-empty list of strings"
                )
            if (
                not isinstance(probabilities, list)
                or len(probabilities) != len(categories)
            ):
                raise ConfigError(
                    f"patient_attributes.{attr}.probabilities must match "
                    "categories length"
                )
            if not all(
                isinstance(p, (int, float)) and not isinstance(p, bool) and p >= 0
                for p in probabilities
            ):
                raise ConfigError(
                    f"patient_attributes.{attr}.probabilities must be "
                    "non-negative numbers"
                )
            if abs(sum(float(p) for p in probabilities) - 1.0) > 1e-6:
                raise ConfigError(
                    f"patient_attributes.{attr}.probabilities must sum "
                    f"to 1, got {sum(probabilities)}"
                )

    def _validate_batch(self, data: Dict[str, Any]) -> None:
        batch = data.get("batch", {})
        target = batch.get("target_patient_records")
        if target is not None and (
            isinstance(target, bool) or not isinstance(target, int) or target <= 0
        ):
            raise ConfigError(
                f"batch.target_patient_records must be a positive integer, got {target}"
            )

        required_scenarios = batch.get("required_standard_scenarios")
        if required_scenarios is not None:
            if not isinstance(required_scenarios, list) or not all(
                isinstance(s, str) for s in required_scenarios
            ):
                raise ConfigError(
                    "batch.required_standard_scenarios must be a list of strings"
                )
            expected = {"S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"}
            configured = set(required_scenarios)
            missing = expected - configured
            if missing:
                raise ConfigError(
                    f"batch.required_standard_scenarios missing Standard-8 "
                    f"scenario(s): {sorted(missing)}"
                )

    def _validate_scenarios(self, data: Dict[str, Any]) -> None:
        scenarios = data.get("scenarios")
        if scenarios is None:
            raise ConfigError("Missing required section 'scenarios'")
        if not isinstance(scenarios, dict):
            raise ConfigError(f"scenarios must be a mapping, got {type(scenarios).__name__}")

        pack = scenarios.get("pack")
        if pack is None:
            raise ConfigError("scenarios.pack must be configured")
        if pack != "Standard-8+CUSTOM":
            raise ConfigError(
                f"scenarios.pack must be 'Standard-8+CUSTOM', got {pack!r}"
            )

        definitions = scenarios.get("definitions")
        if not isinstance(definitions, dict):
            raise ConfigError("scenarios.definitions must be a mapping")
        missing_scenarios = [s for s in STANDARD_SCENARIOS if s not in definitions]
        if missing_scenarios:
            raise ConfigError(
                f"scenarios.definitions missing Standard-8 scenario(s): "
                f"{missing_scenarios}"
            )
        if "CUSTOM" not in definitions:
            raise ConfigError("scenarios.definitions must include 'CUSTOM'")

        # Validate every scenario definition against the known override keys.
        for sid, definition in definitions.items():
            self._validate_scenario_definition(sid, definition)

        # Validate the CUSTOM parameter limits allowlist.
        limits = scenarios.get("custom_parameter_limits")
        if limits is None:
            raise ConfigError("scenarios.custom_parameter_limits must be configured")
        self._validate_custom_limits(limits)

    def _validate_scenario_definition(self, sid: str, definition: Any) -> None:
        if not isinstance(definition, dict):
            raise ConfigError(f"scenarios.definitions.{sid} must be a mapping")
        unknown = [k for k in definition if k not in SCENARIO_PARAMETER_KEYS]
        if unknown:
            raise ConfigError(
                f"scenarios.definitions.{sid} has unknown key(s): {unknown}"
            )
        for key in SCENARIO_PARAMETER_KEYS:
            value = definition.get(key)
            if value is None:
                continue
            if key == "arrivals_wave":
                self._validate_wave(sid, value)
            else:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ConfigError(
                        f"scenarios.definitions.{sid}.{key} must be numeric, "
                        f"got {type(value).__name__}"
                    )
                if value < 0:
                    raise ConfigError(
                        f"scenarios.definitions.{sid}.{key} must be "
                        f"non-negative, got {value}"
                    )

    def _validate_wave(self, sid: str, wave: Any) -> None:
        if not isinstance(wave, dict):
            raise ConfigError(f"scenarios.definitions.{sid}.arrivals_wave must be a mapping")
        enabled = bool(wave.get("enabled", False))
        if not enabled:
            return
        for field in ("factor", "start_hour", "duration_hours"):
            if field not in wave:
                raise ConfigError(
                    f"scenarios.definitions.{sid}.arrivals_wave missing field "
                    f"{field!r}"
                )
            if isinstance(wave[field], bool) or not isinstance(wave[field], (int, float)):
                raise ConfigError(
                    f"scenarios.definitions.{sid}.arrivals_wave.{field} must "
                    f"be numeric"
                )
        if wave["factor"] < 0:
            raise ConfigError(
                f"scenarios.definitions.{sid}.arrivals_wave.factor must be "
                f"non-negative"
            )
        if wave["start_hour"] < 0 or wave["duration_hours"] <= 0:
            raise ConfigError(
                f"scenarios.definitions.{sid}.arrivals_wave requires "
                f"start_hour >= 0 and duration_hours > 0"
            )

    def _validate_custom_limits(self, limits: Any) -> None:
        if not isinstance(limits, dict):
            raise ConfigError("scenarios.custom_parameter_limits must be a mapping")
        for field in CUSTOM_LIMIT_FIELDS:
            spec = limits.get(field)
            if not isinstance(spec, dict) or "min" not in spec or "max" not in spec:
                raise ConfigError(
                    f"scenarios.custom_parameter_limits.{field} must define "
                    f"min/max bounds"
                )
            lo, hi = spec["min"], spec["max"]
            if (
                isinstance(lo, bool)
                or isinstance(hi, bool)
                or not isinstance(lo, (int, float))
                or not isinstance(hi, (int, float))
            ):
                raise ConfigError(
                    f"scenarios.custom_parameter_limits.{field} bounds must "
                    f"be numeric"
                )
            if hi < lo:
                raise ConfigError(
                    f"scenarios.custom_parameter_limits.{field} max must be "
                    f">= min"
                )
        wave = limits.get("arrivals_wave")
        if not isinstance(wave, dict) or "enabled" not in wave:
            raise ConfigError("scenarios.custom_parameter_limits.arrivals_wave must be configured")
        if wave.get("enabled") is True:
            factor = wave.get("factor")
            if (
                not isinstance(factor, dict)
                or "min" not in factor
                or "max" not in factor
            ):
                raise ConfigError(
                    "scenarios.custom_parameter_limits.arrivals_wave.factor "
                    "must define min/max when the wave is enabled"
                )
            lo, hi = factor["min"], factor["max"]
            if (
                isinstance(lo, bool)
                or isinstance(hi, bool)
                or not isinstance(lo, (int, float))
                or not isinstance(hi, (int, float))
                or hi < lo
            ):
                raise ConfigError(
                    "scenarios.custom_parameter_limits.arrivals_wave.factor "
                    "bounds invalid"
                )
