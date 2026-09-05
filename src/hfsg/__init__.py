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
from .reconciliation import (
    OperationalStocks,
    ReconciliationFailure,
    ReconciliationIssue,
    ReconciliationResult,
    Reconciler,
)
from .simulation import (
    SimulationDriver,
    SimulationResult,
    StepOutcome,
)
from .scenarios import (
    CUSTOM_SCENARIO_ID,
    ScenarioManager,
    ScenarioError,
    configuration_hash,
    hash_yaml,
)
from .output import (
    write_partitioned,
    read_partitioned,
    dataset_manifest,
    check_post_serialization,
    replay_operational_stocks,
    match_aggregate_to_replay,
)
from .pipeline import (
    Pipeline,
    ScenarioRunOutcome,
    Step8Error,
)
from .validation_report import (
    ValidationReportError,
    validate_outputs,
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
    "OperationalStocks",
    "Reconciler",
    "ReconciliationResult",
    "ReconciliationIssue",
    "ReconciliationFailure",
    "SimulationDriver",
    "SimulationResult",
    "StepOutcome",
    "CUSTOM_SCENARIO_ID",
    "ScenarioManager",
    "ScenarioError",
    "configuration_hash",
    "hash_yaml",
    "write_partitioned",
    "read_partitioned",
    "dataset_manifest",
    "check_post_serialization",
    "replay_operational_stocks",
    "match_aggregate_to_replay",
    "Pipeline",
    "ScenarioRunOutcome",
    "Step8Error",
    "ValidationReportError",
    "validate_outputs",
]
__version__ = "0.5.0"
