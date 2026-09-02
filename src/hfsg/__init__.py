"""HFSG - Hospital Flow Scenario Generator.

Phase 1 MVP package.
"""

from .config import Configuration, ConfigurationLoader, ConfigError
from .context import SimulationContext, build_context
from .engine import (
    AggregateEngine,
    AggregateEngineError,
    RunResult,
    StateSnapshot,
    StepFlows,
    TimestepRecord,
)
from .seeds import CHILD_SEED_ALGORITHM_VERSION, derive_child_seed
from .validation import (
    AggregateValidationError,
    AggregateValidator,
    ValidationIssue,
    ValidationResult,
)
from .patients import Patient, PatientGenerator
from .quota import IntegerFlowAllocator, QuotaResult
from .events import (
    CRITICAL_RECONCILIATION_FAILURE,
    PatientEvent,
    PatientEventGenerator,
    SimulationClock,
)
from .patient_validation import (
    PatientValidationError,
    PatientValidationResult,
    PatientValidator,
)

__all__ = [
    "Configuration",
    "ConfigurationLoader",
    "ConfigError",
    "SimulationContext",
    "build_context",
    "AggregateEngine",
    "AggregateEngineError",
    "RunResult",
    "StateSnapshot",
    "StepFlows",
    "TimestepRecord",
    "CHILD_SEED_ALGORITHM_VERSION",
    "derive_child_seed",
    "AggregateValidator",
    "AggregateValidationError",
    "ValidationIssue",
    "ValidationResult",
    "Patient",
    "PatientGenerator",
    "IntegerFlowAllocator",
    "QuotaResult",
    "CRITICAL_RECONCILIATION_FAILURE",
    "PatientEvent",
    "PatientEventGenerator",
    "SimulationClock",
    "PatientValidator",
    "PatientValidationResult",
    "PatientValidationError",
]
__version__ = "0.3.0"
