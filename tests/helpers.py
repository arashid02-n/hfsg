"""Shared test helpers for HFSG engine tests."""

import copy

import yaml

from hfsg.config import ConfigurationLoader
from hfsg.context import build_context
from hfsg.engine import AggregateEngine

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
