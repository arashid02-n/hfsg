OPERATIONS.md

HFSG — Operations Specification

Project: Hospital Flow Scenario Generator
Operations Version: 1.0
Implementation Target: Phase 1 — MVP


---

1. Purpose

This document defines how HFSG is configured, executed, validated, tested, and used during Phase 1.

It describes the operational workflow around the HFSG Core Engine.

It does NOT define the mathematical model.

Model behaviour is defined in MODEL.md.

Product scope is defined in PRODUCT.md.

Software structure is defined in ARCHITECTURE.md.

Agent behaviour is defined in AGENTS.md.


---

2. Operating Principle

HFSG must be operated through a controlled workflow:

Configuration
    ↓
Configuration Validation
    ↓
Scenario Selection
    ↓
Simulation
    ↓
Patient/Event Generation
    ↓
Reconciliation
    ↓
Validation
    ↓
Output Generation
    ↓
Result Inspection

A simulation that completes without errors is not automatically considered valid.

Validation MUST pass before a production Dataset is released.


---

3. Required Environment

Phase 1 requires an environment capable of running the HFSG software and its dependencies.

The project MUST maintain:

source code;

configuration files;

test suite;

simulation engine;

validation tools;

output writers.


The exact operating-system, Python-version, package versions, and installation commands MUST be defined by the actual implementation environment rather than invented by the agent.


---

4. Repository Structure

The repository SHOULD maintain a clear separation between source code, configuration, tests, documentation, and generated outputs.

A recommended structure is:

HFSG/
├── PRODUCT.md
├── MODEL.md
├── ARCHITECTURE.md
├── OPERATIONS.md
├── AGENTS.md
│
├── config/
│   ├── base.yaml
│   └── scenarios/
│
├── src/
│   └── hfsg/
│
├── tests/
│
├── scripts/
│
├── data/
│   ├── input/
│   └── output/
│
└── reports/

The implementation may use a different directory structure only when it remains consistent with ARCHITECTURE.md.

Generated large datasets SHOULD NOT be committed to Git unless explicitly required.


---

5. Configuration Workflow

Before running a simulation:

1. load the approved YAML configuration;


2. validate the configuration;


3. select the scenario;


4. apply approved scenario overrides;


5. validate the resulting configuration;


6. initialize the simulation.



The engine MUST refuse invalid configuration.

Examples of configuration errors include:

invalid destination shares;

negative capacity;

invalid initial stock;

invalid rate;

missing required parameter;

invalid scenario definition;

invalid random seed configuration.



---

6. Scenario Execution

The approved Standard-8 scenarios are:

S1 — Normal Operation
S2 — Busy Week
S3 — Crisis Mode
S4 — ICU Capacity Loss
S5 — Bed Block
S6 — Compound Stress
S7 — Emergency Wave
S8 — Recovery Strategy

The system must also support:

CUSTOM — Customer Scenario

Each scenario MUST be executed using the same Core Engine.

Scenario parameters MUST be loaded from configuration.

The engine MUST NOT modify its mathematical structure based on the scenario.


---

7. Single Simulation Run

A standard simulation run should follow:

1. Select configuration
2. Select scenario
3. Set simulation ID
4. Set random seed
5. Initialize stocks
6. Initialize patient state
7. Run simulation for the configured horizon
8. Generate patient entities
9. Generate patient events
10. Reconcile aggregate and patient data
11. Run validation
12. Write outputs
13. Generate summary
14. Record run metadata

The default MVP horizon is:

720 hours

The default time step is:

1 hour


---

8. Random Seed

Every simulation MUST have an identifiable random seed.

The run metadata must preserve:

simulation ID;

scenario ID;

random seed;

model version;

configuration version;

generation timestamp.


For reproducibility testing, the same configuration and seed MUST be reused.

The resulting test fixture must reproduce the expected deterministic/stochastic behaviour.


---

9. Baseline Execution
Before running Standard-8 or a large Batch, the baseline scenario MUST be tested.

Baseline:

S1 — Normal Operation

The initial baseline test should be small enough to allow rapid inspection.

The baseline MUST demonstrate that:

the simulation starts;

stocks remain valid;

flows remain valid;

mass balance passes;

patient generation works;

event generation works;

aggregate/patient reconciliation passes;

outputs can be read successfully.


Large Batch generation SHOULD NOT begin until the baseline is validated.


---

10. Validation Workflow

Validation must occur during and after simulation.

Required checks include:

no negative stocks;

no flow greater than source stock;

no unauthorized capacity violation;

destination shares sum to one;

no NaN/Inf;

mass balance;

unique patient IDs;

unique event IDs;

chronological events;

no post-terminal events;

one active location per patient;

aggregate/patient reconciliation;

seed reproducibility;

scenario coverage.


A critical failure MUST be clearly reported.

Do not silently repair invalid data after generation.


---

11. Standard-8 Validation

All eight standard scenarios MUST be executed and validated:

S1 → PASS
S2 → PASS
S3 → PASS
S4 → PASS
S5 → PASS
S6 → PASS
S7 → PASS
S8 → PASS

CUSTOM must also be executable using an approved customer configuration.

A Standard-8 result is incomplete if any standard scenario is missing or failed.


---

12. Output Generation

A successful simulation should produce the approved outputs where applicable:

patients.parquet
patient_events.parquet
aggregate_timeseries.parquet
simulation_summary.parquet
scenario_comparison.csv
dataset_manifest.json
validation_report.json
used_configuration.yaml

The exact files produced by a small development run may be limited according to the execution mode, but production Dataset generation MUST produce the required Dataset package.


---

13. Output Inspection

After a simulation:

1. confirm expected files exist;


2. confirm files can be opened;


3. inspect row counts;


4. inspect schema;


5. inspect scenario ID;


6. inspect simulation ID;


7. inspect validation status;


8. inspect patient/event uniqueness;


9. inspect aggregate/patient reconciliation;


10. inspect metadata.



A file existing on disk does not mean the output is valid.


---

14. Batch Operation

The commercial Dataset target is:

>= 1,000,000 patient records

Batch generation must be incremental.

Approved planning configuration:

patient chunk = 50,000 rows
event chunk = 100,000 rows
compression = ZSTD
partition = scenario_id

The complete Dataset MUST NOT be held in memory.

The Batch process should:

Generate
    ↓
Validate
    ↓
Write
    ↓
Release Memory
    ↓
Continue


---

15. Batch Scenario Coverage

The Standard Dataset must contain representation from all eight scenarios.

Required:

S1
S2
S3
S4
S5
S6
S7
S8

The Batch process MUST record scenario coverage.

If one of the required Standard-8 scenarios is absent, the Standard Dataset is incomplete.


---

16. Batch Failure Policy

A production Batch MUST NOT be released when:

mass balance fails;

aggregate/patient reconciliation fails;

required validation fails;

required scenario coverage is missing;

required output files are missing;

output files cannot be read;

Dataset metadata is incomplete.


The resulting Dataset status must be:

NOT RELEASABLE

until the failure is resolved.


---

17. Dataset Metadata

A commercial Dataset must contain metadata including:

Product ID;

Dataset ID;

Dataset Version;

Engine Version;

Scenario Pack;

Patient Record Count;

Patient Event Count;

Generation Timestamp;

Data Type;

Configuration Hash;

Validation Status;

License ID.


Patient and event counts MUST be calculated from the generated data.

They MUST NOT be hard-coded.


---

18. Dataset Release

A Dataset can be released only when:

validation_status = PASS

and:

required files exist;

metadata is complete;

configuration is preserved;

random seed policy is recorded;

mass balance passes;

reconciliation passes;

uniqueness checks pass;
temporal consistency passes;

scenario coverage passes;

Parquet files are readable.


Otherwise:

NOT RELEASABLE


---

19. Development vs Production Runs

HFSG operations should distinguish between:

Development Run

Purpose:

debugging;

testing;

rapid iteration;

small datasets.


Development runs may use small horizons and small patient counts.

Validation Run

Purpose:

verify the complete approved behaviour;

execute Standard-8;

verify validation and reconciliation.


Production Batch

Purpose:

generate the approved commercial Dataset volume;

produce complete metadata;

produce the final validation report.


Do not use a large production Batch as the primary debugging method.


---

20. Reproducibility Test

A reproducibility test should:

1. select a fixed configuration;


2. select a fixed scenario;


3. select a fixed random seed;


4. run the simulation;


5. save the relevant outputs;


6. repeat using the same inputs;


7. compare the defined test outputs.



A reproducibility failure must be investigated rather than ignored.


---

21. Logging

The system SHOULD record enough information to identify a simulation run.

At minimum, logs should make it possible to identify:

simulation ID;

scenario ID;

configuration version;

model version;

random seed;

execution status;

validation status;

errors or critical failures.


Logs MUST NOT silently hide critical validation failures.


---

22. Operational Troubleshooting

When a run fails:

1. identify the failure type;


2. identify the component responsible;


3. inspect the relevant configuration;


4. inspect the validation output;


5. reproduce with the smallest useful test case;


6. fix the underlying implementation or configuration;


7. rerun the affected validation;


8. only then continue to larger execution.



Do not bypass a failed validation simply to continue the Batch.


---

23. Operational Decision Rules

If a required value is missing:

DECISION_REQUIRED

If project specifications conflict:

SPEC_CONFLICT

If the generated data violates a critical invariant:

CRITICAL

These states must remain visible in logs/reports.


---

24. Phase 1 Operational Completion

Phase 1 operations are considered complete when the system can:

1. load approved configuration;


2. execute S1 baseline;


3. generate valid patient data;


4. generate valid patient events;


5. reconcile aggregate and patient data;


6. validate the simulation;


7. execute S1–S8;


8. execute CUSTOM;


9. generate the required outputs;


10. perform a 100,000-patient dry run;


11. perform the approved >=1,000,000-patient Batch;


12. produce Dataset metadata;


13. produce a validation report;


14. confirm the final Dataset is releasable.



The final release condition is:

validation_status = PASS

with no unresolved critical validation failure.