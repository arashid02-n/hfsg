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

        self._validate_sections(data)
        self._validate_required_fields(data)
        self._validate_types(data)
        self._validate_non_negative(data)
        self._validate_time_step(data)
        self._validate_destination_shares(data)
        self._validate_initial_population_vs_capacity(data)
        self._validate_batch(data)

        return Configuration(data, config_path)

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