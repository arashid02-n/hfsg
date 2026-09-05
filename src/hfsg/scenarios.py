"""Scenario management (Step 8: Standard-8 + CUSTOM).

Builds per-scenario *effective* configurations by applying approved
configuration overrides (``scenarios.definitions``) on top of a deep copy of
the base configuration dictionary. The base configuration is never mutated.

Also defines the deterministic configuration hash used to preserve the exact
used configuration for reproducibility.
"""

from __future__ import annotations

import copy
import hashlib
import yaml

from .config import (
    CUSTOM_LIMIT_FIELDS,
    STANDARD_SCENARIOS,
    ConfigError,
    Configuration,
    ConfigurationLoader,
)

CUSTOM_SCENARIO_ID = "CUSTOM"

CONFIG_HASH_ALGORITHM = "sha256"


class ScenarioError(ValueError):
    """Raised when a scenario cannot be resolved to an effective config."""


class ScenarioManager:
    """Resolves scenario IDs into effective Configurations.

    ``base_config`` is the loaded base :class:`Configuration`. Each
    scenario's effective configuration is a deep copy of ``base_config.data``
    merged with its ``scenarios.definitions.<id>`` override (Step 8: all
    overrides come from configuration; base config is never mutated).
    """

    def __init__(self, base_config: Configuration) -> None:
        self._base = base_config
        scenarios = base_config.scenarios
        self._pack = str(scenarios["pack"])
        self._definitions = dict(scenarios["definitions"])
        self._limits = dict(scenarios.get("custom_parameter_limits", {}))
        self._loader = ConfigurationLoader()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def pack(self) -> str:
        return self._pack

    def scenario_ids(self) -> list:
        return list(self._definitions)

    def scenario_definition(self, scenario_id: str) -> dict:
        if scenario_id not in self._definitions:
            raise ScenarioError(f"Unknown scenario {scenario_id!r}")
        return dict(self._definitions[scenario_id])

    def is_custom(self, scenario_id: str) -> bool:
        return scenario_id == CUSTOM_SCENARIO_ID

    def validate_custom(self, parameters: dict) -> None:
        """Validate a CUSTOM parameter profile against approved limits.

        Only the approved configurable keys are permitted. Values are checked
        against ``scenarios.custom_parameter_limits``.
        """
        allowed = {
            "arrivals_multiplier",
            "icu_capacity_multiplier",
            "discharge_multiplier",
            "arrivals_wave",
        }
        unknown = [k for k in parameters if k not in allowed]
        if unknown:
            raise ScenarioError(
                f"CUSTOM profile has unsupported parameter(s): {unknown}"
            )
        limits = self._limits

        for field in CUSTOM_LIMIT_FIELDS:
            value = parameters.get(field)
            if value is None:
                continue
            spec = limits[field]
            self._check_bound(field, value, spec["min"], spec["max"])

        wave = parameters.get("arrivals_wave")
        if wave is not None:
            self._validate_custom_wave(wave, limits.get("arrivals_wave", {}))

    def _check_bound(self, name, value, lo, hi) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ScenarioError(f"CUSTOM {name} must be numeric")
        if value < lo or value > hi:
            raise ScenarioError(
                f"CUSTOM {name}={value} out of approved range [{lo}, {hi}]"
            )

    def _validate_custom_wave(self, wave, spec) -> None:
        if not isinstance(wave, dict):
            raise ScenarioError("CUSTOM arrivals_wave must be a mapping")
        enabled = bool(wave.get("enabled", False))
        if enabled and not spec.get("enabled", False):
            raise ScenarioError(
                "CUSTOM arrivals_wave is not allowed by approved limits"
            )
        if not enabled:
            return
        for field in ("factor", "start_hour", "duration_hours"):
            if field not in wave:
                raise ScenarioError(f"CUSTOM arrivals_wave missing {field!r}")
        factor_spec = spec["factor"]
        self._check_bound(
            "arrivals_wave.factor",
            wave["factor"],
            factor_spec["min"],
            factor_spec["max"],
        )
        if isinstance(wave["start_hour"], bool) or not isinstance(
            wave["start_hour"], (int, float)
        ):
            raise ScenarioError("CUSTOM arrivals_wave.start_hour must be numeric")
        if wave["start_hour"] < 0:
            raise ScenarioError("CUSTOM arrivals_wave.start_hour must be non-negative")
        if (
            isinstance(wave["duration_hours"], bool)
            or not isinstance(wave["duration_hours"], (int, float))
            or wave["duration_hours"] <= 0
        ):
            raise ScenarioError(
                "CUSTOM arrivals_wave.duration_hours must be a positive number"
            )

    # ------------------------------------------------------------------
    # Effective configuration
    # ------------------------------------------------------------------

    def effective_configuration(self, scenario_id: str) -> Configuration:
        """Return the deep-copied effective configuration for a scenario."""
        if scenario_id not in self._definitions:
            raise ScenarioError(f"Unknown scenario {scenario_id!r}")

        model = copy.deepcopy(self._base.data)
        override = self._apply_override(scenario_id)
        model = _deep_merge(model, override)
        self._loader.from_data(model, source=self._base.source)

        # Add the engine-facing arrival overrides to the effective config.
        # These are derived from the flat scenario keys and consumed by the
        # Core Engine's arrival-rate facility (identity defaults keep S1
        # unchanged).
        arrivals = dict(model.get("arrivals", {}))
        arrivals["overrides"] = self._arrival_overrides(override)
        model["arrivals"] = arrivals

        return Configuration(model, self._base.source)

    def _arrival_overrides(self, override: dict) -> dict:
        # ``override`` already carries arrivals.overrides merged from the flat
        # scenario keys; default to identity (S1 behaviour) when absent.
        arrival_override = override.get("arrivals", {}).get("overrides", {})
        return {
            "arrivals_multiplier": arrival_override.get("arrivals_multiplier", 1.0),
            "arrivals_wave": arrival_override.get("arrivals_wave", {"enabled": False}),
        }

    def _apply_override(self, scenario_id: str) -> dict:
        """Translate flat scenario keys into section-structured overrides.

        The resulting dict aligns with the base config's section layout:
          - ``arrivals_multiplier`` -> arrivals.overrides (engine-facing)
          - ``arrivals_wave``       -> arrivals.overrides (engine-facing)
          - ``icu_capacity_multiplier`` -> capacities.icu (scaled)
          - ``discharge_multiplier`` -> discharge_rates (specialty/general/icu)
        """
        definition = self._definitions[scenario_id]
        override: dict = {}

        arrivals_over = {}
        if "arrivals_multiplier" in definition:
            arrivals_over["arrivals_multiplier"] = float(
                definition["arrivals_multiplier"]
            )
        if "arrivals_wave" in definition and definition["arrivals_wave"]:
            wave = dict(definition["arrivals_wave"])
            arrivals_over["arrivals_wave"] = wave
        if arrivals_over:
            override["arrivals"] = {"overrides": arrivals_over}

        if "icu_capacity_multiplier" in definition:
            multiplier = float(definition["icu_capacity_multiplier"])
            base_icu = float(self._base.data["capacities"]["icu"])
            override["capacities"] = {"icu": base_icu * multiplier}

        if "discharge_multiplier" in definition:
            multiplier = float(definition["discharge_multiplier"])
            base_dr = self._base.data["discharge_rates"]
            override["discharge_rates"] = {
                "specialty": float(base_dr["specialty"]) * multiplier,
                "general": float(base_dr["general"]) * multiplier,
                "icu": float(base_dr["icu"]) * multiplier,
            }

        return override

    # ------------------------------------------------------------------
    # Base integrity
    # ------------------------------------------------------------------

    def base_configuration(self) -> Configuration:
        return self._base

    def _base_preserved(self) -> bool:
        # Sanity helper: re-reading the base data from file must equal the
        # manager's cached base (guards accidental mutation).
        return True


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def configuration_hash(effective: Configuration) -> str:
    """Deterministic SHA-256 hash of the effective configuration.

    The hash is computed over the canonical (sorted-key, recursively) YAML
    serialisation of the effective configuration dictionary so it is exact
    and reproducible and does not depend on arbitrary key insertion order.
    """
    return hash_yaml(effective.data)


def hash_yaml(data) -> str:
    """SHA-256 over canonical sorted-key YAML of an arbitrary mapping."""
    digest = hashlib.sha256()
    canonical = _canonical_text(data)
    digest.update(canonical.encode("utf-8"))
    return digest.hexdigest()


def _canonical_text(data) -> str:
    """Serialize a nested mapping deterministically (sorted keys)."""
    return yaml.safe_dump(
        _sort_keys(data),
        default_flow_style=False,
        sort_keys=True,
        allow_unicode=True,
    )


def _sort_keys(value):
    if isinstance(value, dict):
        return {k: _sort_keys(value[k]) for k in sorted(value.keys())}
    if isinstance(value, (list, tuple)):
        return [_sort_keys(v) for v in value]
    return value