"""Aggregate validation layer (MODEL.md sections 7, 11, 12, 18, 30).

Implements the aggregate-applicable subset of the approved validation
checks from ``model.validation.checks``:

    no_negative_stocks, source_stock_limits, capacity_limits,
    destination_shares_sum_to_one (engine init), no_nan_inf,
    mass_balance, plus valid initial conditions and non-negative flows.

Mass-balance failure is Critical (MODEL.md section 18). Validation is
never bypassed: critical issues abort the run when the corresponding
enforcement flag is enabled. Patient/event checks (unique IDs,
chronology, reconciliation) belong to Steps 6-7 and are intentionally
absent here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from .units import (
    ACTIVE_UNITS,
    EXIT_FLOWS,
    TRANSFERS,
)


def _transfer_and_exit_sources():
    for name, src, _dst in TRANSFERS:
        yield name, src
    yield from EXIT_FLOWS.items()

SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING = "warning"

STOCK_TOLERANCE = 1e-9
FLOW_TOLERANCE = 1e-9
CAPACITY_TOLERANCE = 1e-6

CHECK_NO_NEGATIVE_STOCKS = "no_negative_stocks"
CHECK_SOURCE_STOCK_LIMITS = "source_stock_limits"
CHECK_CAPACITY_LIMITS = "capacity_limits"
CHECK_NO_NAN_INF = "no_nan_inf"
CHECK_MASS_BALANCE = "mass_balance"


@dataclass(frozen=True)
class ValidationIssue:
    step: Optional[int]
    check: str
    severity: str
    message: str


@dataclass
class ValidationResult:
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def critical_issues(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == SEVERITY_CRITICAL]

    @property
    def passed(self) -> bool:
        return not self.critical_issues


class AggregateValidationError(RuntimeError):
    """Raised when a critical aggregate invariant is violated."""

    def __init__(self, result: ValidationResult) -> None:
        self.result = result
        first = result.critical_issues[0]
        super().__init__(
            f"Critical aggregate validation failure at step "
            f"{first.step}: [{first.check}] {first.message}"
        )


class AggregateValidator:
    """Validates initial conditions and every aggregate timestep."""

    def __init__(self, config) -> None:
        validation = config.validation
        self.mass_balance_tolerance = float(
            validation.get("mass_balance_tolerance", 1e-6)
        )
        self.enforce_nonnegative = bool(
            validation.get("enforce_nonnegative_stocks", True)
        )
        self.enforce_capacity = bool(
            validation.get("enforce_capacity_limits", True)
        )
        self.enforce_mass_balance = bool(
            validation.get("enforce_mass_balance", True)
        )
        self.enabled_checks = set(validation.get("checks", []))
        self.capacities = {
            unit: float(config.capacities[unit]) for unit in ACTIVE_UNITS
        }
        self._result = ValidationResult()
        self._baseline_total: Optional[float] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_initial(self, snapshot) -> None:
        self._check_finite(None, {"stock": snapshot.total}, "initial total")
        for unit in ACTIVE_UNITS:
            stock = snapshot.stock(unit)
            capacity = self.capacities[unit]
            if math.isnan(stock) or math.isinf(stock):
                self._add(None, CHECK_NO_NAN_INF, True,
                          f"initial {unit} census is NaN/Inf")
                continue
            self._check_nonneg(None, unit, stock, True)
            if stock > capacity + CAPACITY_TOLERANCE:
                self._add(None, CHECK_CAPACITY_LIMITS, True,
                          f"initial {unit} census {stock} exceeds capacity "
                          f"{capacity}")
        if snapshot.cumulative_discharges < -STOCK_TOLERANCE:
            self._add(None, CHECK_NO_NEGATIVE_STOCKS, True,
                      "initial cumulative_discharges is negative")
        if snapshot.cumulative_deaths < -STOCK_TOLERANCE:
            self._add(None, CHECK_NO_NEGATIVE_STOCKS, True,
                      "initial cumulative_deaths is negative")
        self._baseline_total = snapshot.total
        self._raise_if_critical()

    def validate_step(self, record) -> None:
        hour = record.hour
        before, after, flows = record.before, record.after, record.flows

        values: dict = {
            "arrivals_drawn": float(flows.arrivals_drawn),
            "arrivals_accepted": float(flows.arrivals_accepted),
        }
        for name, value in flows.constrained.items():
            values[f"flow:{name}"] = value
            if name in flows.requested:
                values[f"requested:{name}"] = flows.requested[name]
        for unit in ACTIVE_UNITS:
            values[f"after:{unit}"] = after.stock(unit)
        self._check_finite(hour, values, "timestep")

        for unit in ACTIVE_UNITS:
            self._check_nonneg(hour, f"{unit}(end)", after.stock(unit),
                               self.enforce_nonnegative)
        if after.cumulative_discharges < -STOCK_TOLERANCE:
            self._add(hour, CHECK_NO_NEGATIVE_STOCKS,
                      self.enforce_nonnegative,
                      "cumulative_discharges went negative")
        if after.cumulative_deaths < -STOCK_TOLERANCE:
            self._add(hour, CHECK_NO_NEGATIVE_STOCKS,
                      self.enforce_nonnegative,
                      "cumulative_deaths went negative")

        self._check_flows_nonnegative(hour, flows)
        self._check_source_limits(hour, before, flows)
        self._check_capacity(hour, after)
        self._check_mass_balance(hour, before, after, flows)

        self._raise_if_critical()

    def result(self) -> ValidationResult:
        return self._result

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def _add(self, step: Optional[int], check: str, enforce: bool,
             message: str) -> None:
        severity = (
            SEVERITY_CRITICAL if enforce else SEVERITY_WARNING
        )
        self._result.issues.append(
            ValidationIssue(step=step, check=check, severity=severity,
                            message=message)
        )

    def _raise_if_critical(self) -> None:
        if self._result.critical_issues:
            raise AggregateValidationError(self.result())

    def _check_finite(self, step: Optional[int], values: dict,
                      label: str) -> None:
        for key, value in values.items():
            if not math.isfinite(value):
                self._add(step, CHECK_NO_NAN_INF, True,
                          f"non-finite {label} value {key}={value}")

    def _check_nonneg(self, step: Optional[int], label: str, value: float,
                      enforce: bool) -> None:
        if value < -STOCK_TOLERANCE:
            self._add(step, CHECK_NO_NEGATIVE_STOCKS, enforce,
                      f"{label} is negative ({value})")

    def _check_flows_nonnegative(self, hour, flows) -> None:
        for name, value in flows.constrained.items():
            if value < -FLOW_TOLERANCE:
                self._add(hour, CHECK_SOURCE_STOCK_LIMITS, True,
                          f"negative flow {name} ({value})")

    def _check_source_limits(self, hour, before, flows) -> None:
        outflows = {unit: 0.0 for unit in ACTIVE_UNITS}
        for name, src in _transfer_and_exit_sources():
            outflows[src] += flows.constrained[name]
        for unit in ACTIVE_UNITS:
            stock = before.stock(unit)
            if outflows[unit] > stock + FLOW_TOLERANCE:
                self._add(hour, CHECK_SOURCE_STOCK_LIMITS, True,
                          f"outflow from {unit} ({outflows[unit]}) exceeds "
                          f"beginning-of-step stock ({stock})")

    def _check_capacity(self, hour, after) -> None:
        for unit in ACTIVE_UNITS:
            stock = after.stock(unit)
            capacity = self.capacities[unit]
            if stock > capacity + CAPACITY_TOLERANCE:
                self._add(hour, CHECK_CAPACITY_LIMITS, self.enforce_capacity,
                          f"{unit} census {stock} exceeds capacity "
                          f"{capacity}")

    def _check_mass_balance(self, hour, before, after, flows) -> None:
        step_residual = (after.total - before.total) - flows.arrivals_accepted
        if abs(step_residual) > self.mass_balance_tolerance:
            self._add(hour, CHECK_MASS_BALANCE, self.enforce_mass_balance,
                      f"step mass balance residual {step_residual}")
        if self._baseline_total is not None:
            cumulative_residual = (
                after.total
                - self._baseline_total
                - after.cumulative_arrivals
            )
            if abs(cumulative_residual) > self.mass_balance_tolerance:
                self._add(hour, CHECK_MASS_BALANCE,
                          self.enforce_mass_balance,
                          f"cumulative mass balance residual "
                          f"{cumulative_residual}")
