"""Tests for the Integer Flow Allocator (MODEL.md section 14)."""

import numpy as np

from hfsg.engine import StateSnapshot
from hfsg.quota import IntegerFlowAllocator, QuotaResult
from helpers import make_config


def _before(**stocks):
    return StateSnapshot(
        hour=-1,
        ed_census=stocks.get("ed", 10.0),
        specialty_census=stocks.get("specialty", 10.0),
        general_census=stocks.get("general", 10.0),
        icu_census=stocks.get("icu", 5.0),
        cumulative_discharges=0.0,
        cumulative_deaths=0.0,
        cumulative_arrivals=0,
    )


def _flow(constrained):
    return {name: float(value) for name, value in constrained.items()}


def _make_allocator(tmp_path, seed=12345):
    config = make_config(tmp_path)
    return IntegerFlowAllocator(config, seed=seed)


class TestIntegerAllocation:
    def test_quotas_are_integers_non_negative(self, tmp_path):
        allocator = _make_allocator(tmp_path)
        constrained = _flow(
            {
                "T_EC": 1.2, "T_EG": 1.7, "T_EI": 0.3, "T_EH": 0.8,
                "T_CG": 0.4, "T_CI": 0.1, "T_GI": 0.2,
                "D_C": 0.9, "D_G": 1.1, "D_I": 0.2,
                "M_C": 0.0, "M_G": 0.0, "M_I": 0.0,
            }
        )
        result = allocator.allocate(0, _before(), constrained)
        assert isinstance(result, QuotaResult)
        for name, quota in result.quotas.items():
            assert isinstance(quota, int)
            assert quota >= 0

    def test_largest_remainder_distribution(self, tmp_path):
        allocator = _make_allocator(tmp_path, seed=7)
        # Total raw ED outflow = 1.2+1.7+0.3+0.8 = 4.0 -> total quota 4.
        constrained = _flow(
            {
                "T_EC": 1.2, "T_EG": 1.7, "T_EI": 0.3, "T_EH": 0.8,
                "T_CG": 0, "T_CI": 0, "T_GI": 0,
                "D_C": 0, "D_G": 0, "D_I": 0,
                "M_C": 0, "M_G": 0, "M_I": 0,
            }
        )
        result = allocator.allocate(0, _before(), constrained)
        # Remainders: T_EC=0.2, T_EG=0.7, T_EI=0.3, T_EH=0.8
        # floors: 1,1,0,0 = 2; remaining=2 -> add to T_EH(0.8) and T_EG(0.7).
        assert result.quotas["T_EC"] == 1
        assert result.quotas["T_EG"] == 2
        assert result.quotas["T_EI"] == 0
        assert result.quotas["T_EH"] == 1

    def test_source_stock_limit_respected(self, tmp_path):
        allocator = _make_allocator(tmp_path, seed=11)
        # ED stock is 2, but raw ED outflows total 4 -> integer outflow capped.
        constrained = _flow(
            {
                "T_EC": 1.2, "T_EG": 1.7, "T_EI": 0.3, "T_EH": 0.8,
                "T_CG": 0, "T_CI": 0, "T_GI": 0,
                "D_C": 0, "D_G": 0, "D_I": 0,
                "M_C": 0, "M_G": 0, "M_I": 0,
            }
        )
        result = allocator.allocate(0, _before(ed=2.0), constrained)
        assert sum(result.quotas[n] for n in ("T_EC", "T_EG", "T_EI", "T_EH")) <= 2

    def test_icu_capacity_guard_priority(self, tmp_path):
        allocator = _make_allocator(tmp_path, seed=5)
        constrained = _flow(
            {
                "T_EI": 3.0, "T_CI": 3.0, "T_GI": 3.0,
                "T_EC": 0, "T_EG": 0, "T_EH": 0,
                "T_CG": 0,
                "D_C": 0, "D_G": 0, "D_I": 0,
                "M_C": 0, "M_G": 0, "M_I": 0,
            }
        )
        # ICU free beds = capacity(20) - before(18) = 2.
        result = allocator.allocate(0, _before(icu=18.0), constrained)
        icu_in = result.quotas["T_EI"] + result.quotas["T_CI"] + result.quotas["T_GI"]
        assert icu_in <= 2

    def test_records_raw_and_difference(self, tmp_path):
        allocator = _make_allocator(tmp_path, seed=3)
        constrained = _flow(
            {
                "T_EC": 1.2, "T_EG": 1.7, "T_EI": 0.3, "T_EH": 0.8,
                "T_CG": 0.2, "T_CI": 0.1, "T_GI": 0.1,
                "D_C": 0.2, "D_G": 0.3, "D_I": 0.1,
                "M_C": 0.0, "M_G": 0.0, "M_I": 0.0,
            }
        )
        result = allocator.allocate(0, _before(), constrained)
        for name, quota in result.quotas.items():
            assert result.raw[name] == constrained[name]
            assert result.differences[name] == pytest.approx(
                quota - constrained[name]
            )

    def test_deterministic_same_seed(self, tmp_path):
        constrained = _flow(
            {
                "T_EC": 1.2, "T_EG": 1.7, "T_EI": 0.3, "T_EH": 0.8,
                "T_CG": 0.4, "T_CI": 0.1, "T_GI": 0.2,
                "D_C": 0.9, "D_G": 1.1, "D_I": 0.2,
                "M_C": 0.0, "M_G": 0.0, "M_I": 0.0,
            }
        )
        a = _make_allocator(tmp_path, seed=42).allocate(0, _before(), constrained)
        b = _make_allocator(tmp_path, seed=42).allocate(0, _before(), constrained)
        assert a.quotas == b.quotas


import pytest  # noqa: E402

# imported for fixture-less per-test assertion helper usage consistency