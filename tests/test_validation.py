from dataclasses import replace

import pytest

from hfsg.engine import AggregateEngine
from hfsg.validation import (
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    AggregateValidationError,
    AggregateValidator,
    ValidationIssue,
    ValidationResult,
)
from helpers import make_config, make_engine


class TestValidationResult:
    def test_empty_result_passes(self):
        assert ValidationResult().passed

    def test_critical_fails(self):
        result = ValidationResult()
        result.issues.append(
            ValidationIssue(step=3, check="mass_balance",
                            severity=SEVERITY_CRITICAL, message="x")
        )
        assert not result.passed
        assert len(result.critical_issues) == 1

    def test_warning_alone_passes(self):
        result = ValidationResult()
        result.issues.append(
            ValidationIssue(step=3, check="capacity_limits",
                            severity=SEVERITY_WARNING, message="x")
        )
        assert result.passed


class TestInitialValidation:
    def test_valid_initial_passes(self, base_config):
        engine = make_engine(base_config)
        assert engine.validator.result().passed
        assert engine.initial.total == 115.0

    def test_nan_initial_rejected(self, base_config):
        validator = AggregateValidator(base_config)
        snapshot = replace(make_engine(base_config).initial,
                           icu_census=float("nan"))
        with pytest.raises(AggregateValidationError, match="nan"):
            validator.validate_initial(snapshot)

    def test_negative_initial_rejected(self, base_config):
        validator = AggregateValidator(base_config)
        snapshot = replace(make_engine(base_config).initial, ed_census=-1.0)
        with pytest.raises(AggregateValidationError, match="negative"):
            validator.validate_initial(snapshot)

    def test_over_capacity_initial_rejected(self, base_config):
        validator = AggregateValidator(base_config)
        snapshot = replace(make_engine(base_config).initial,
                           general_census=150.0)
        with pytest.raises(AggregateValidationError, match="exceeds capacity"):
            validator.validate_initial(snapshot)


class TestStepValidation:
    def test_clean_run_reports_no_issues(self, base_config):
        engine = make_engine(base_config, seed=17)
        result = engine.run()
        assert result.validation is not None
        assert result.validation.issues == []
        assert result.validation.passed
        assert result.passed

    def test_negative_stock_detected(self, base_config):
        validator = AggregateValidator(base_config)
        engine = make_engine(base_config, seed=17)
        record = engine.step(0)
        tampered = replace(
            record,
            after=replace(record.after, specialty_census=-0.5),
        )
        with pytest.raises(AggregateValidationError, match="negative"):
            validator.validate_step(tampered)

    def test_nan_flow_detected(self, base_config):
        validator = AggregateValidator(base_config)
        engine = make_engine(base_config, seed=17)
        record = engine.step(0)
        flows = replace(
            record.flows,
            constrained={**record.flows.constrained, "T_EC": float("nan")},
        )
        tampered = replace(record, flows=flows)
        with pytest.raises(AggregateValidationError, match="non-finite"):
            validator.validate_step(tampered)

    def test_infinite_stock_detected(self, base_config):
        validator = AggregateValidator(base_config)
        engine = make_engine(base_config, seed=17)
        record = engine.step(0)
        tampered = replace(
            record,
            after=replace(record.after, ed_census=float("inf")),
        )
        with pytest.raises(AggregateValidationError, match="non-finite"):
            validator.validate_step(tampered)

    def test_source_limit_violation_detected(self, base_config):
        validator = AggregateValidator(base_config)
        engine = make_engine(base_config, seed=17)
        record = engine.step(0)
        flows = replace(
            record.flows,
            constrained={
                **record.flows.constrained,
                "T_EH": record.before.ed_census + 10.0,
                "T_EC": 0.0,
                "T_EG": 0.0,
                "T_EI": 0.0,
            },
        )
        tampered = replace(record, flows=flows)
        with pytest.raises(AggregateValidationError, match="exceeds"):
            validator.validate_step(tampered)

    def test_mass_balance_violation_detected(self, base_config):
        validator = AggregateValidator(base_config)
        engine = make_engine(base_config, seed=17)
        record = engine.step(0)
        tampered = replace(
            record,
            after=replace(record.after, cumulative_deaths=99.0),
        )
        with pytest.raises(AggregateValidationError, match="mass balance"):
            validator.validate_step(tampered)

    def test_capacity_violation_detected(self, base_config):
        validator = AggregateValidator(base_config)
        engine = make_engine(base_config, seed=17)
        record = engine.step(0)
        tampered = replace(
            record,
            after=replace(record.after, icu_census=999.0),
        )
        with pytest.raises(AggregateValidationError, match="exceeds capacity"):
            validator.validate_step(tampered)


class TestEnforcementFlags:
    def test_disabled_enforcement_downgrades_to_warning(self, tmp_path):
        config = make_config(
            tmp_path,
            {
                "validation": {
                    "enforce_nonnegative_stocks": False,
                    "enforce_capacity_limits": False,
                    "enforce_mass_balance": False,
                }
            },
        )
        validator = AggregateValidator(config)
        engine = make_engine(config, seed=17)
        record = engine.step(0)
        tampered = replace(
            record,
            after=replace(record.after, icu_census=-1.0),
        )
        validator.validate_step(tampered)
        issues = validator.result().issues
        assert issues, "expected at least one recorded issue"
        assert any(i.severity == SEVERITY_WARNING for i in issues)
        assert not any(i.severity == SEVERITY_CRITICAL for i in issues)


class TestEngineIntegration:
    def test_validator_attached_by_default(self, base_config):
        engine = make_engine(base_config)
        assert isinstance(engine.validator, AggregateValidator)

    def test_custom_validator_is_used_and_accumulates(self, base_config):
        from hfsg.context import build_context

        validator = AggregateValidator(base_config)
        context = build_context(base_config, "S1", 0)
        engine = AggregateEngine(base_config, context, validator=validator)
        result = engine.run()
        assert engine.validator is validator
        assert result.validation is validator.result()
        assert result.validation.passed
