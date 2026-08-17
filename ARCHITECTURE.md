ARCHITECTURE.md

HFSG — Software Architecture Specification

Project: Hospital Flow Scenario Generator
Architecture Version: 1.0
Implementation Target: Phase 1 — MVP


---

1. Architecture Purpose

This document defines the software architecture required to implement the approved HFSG Phase 1 MVP.

The architecture MUST:

implement the approved Model B from MODEL.md;

respect the product scope defined in PRODUCT.md;

separate model logic from configuration;

separate aggregate simulation from patient-level generation;

preserve aggregate-to-patient reconciliation;

support Standard-8 and CUSTOM scenarios;

support reproducible simulation;

support validation;

support chunked dataset generation.


The architecture MUST remain simple and focused on the Phase 1 requirements.


---

2. Core Architecture

The HFSG Core Engine follows this logical pipeline:

Approved Configuration
        ↓
Configuration Loader
        ↓
Scenario Configuration
        ↓
Aggregate Flow Engine
        ↓
Patient Generator
        ↓
Patient Event Generator
        ↓
Reconciliation / Validation
        ↓
Output Writer
        ↓
Dataset / Simulation Outputs

The same Core Engine MUST be used for:

Demo;

Dataset;

Generator;

Standard-8;

CUSTOM.


The simulation model MUST NOT be duplicated for different products or scenarios.


---

3. Major Components

3.1 Configuration Layer

Responsibility:

Load and validate approved YAML configuration.

It provides:

model parameters;

initial conditions;

capacities;

arrival parameters;

transfer parameters;

discharge parameters;

death parameters;

patient attribute distributions;

scenario definitions;

random seed configuration;

output configuration.


The Configuration Layer MUST NOT contain simulation logic.

It MUST reject invalid configurations before simulation begins.


---

3.2 Scenario Layer

Responsibility:

Select a scenario and apply approved parameter overrides.

Supported scenarios:

S1
S2
S3
S4
S5
S6
S7
S8
CUSTOM

Scenario logic MUST operate through configuration.

It MUST NOT:

change the mathematical equations;

create a separate simulation engine;

silently introduce new parameters;

modify core model structure.



---

3.3 Aggregate Flow Engine

Responsibility:

Implement Model B aggregate hospital-flow simulation defined in MODEL.md.

It manages:

ED;

Specialty Ward;

General Medical Ward;

ICU;

cumulative discharges;

cumulative deaths.


It calculates:

arrivals;

ED processing;

transfers;

discharges;

deaths;

capacity constraints;

unmet demand;

stock updates.


The engine MUST use the simultaneous update rule defined in MODEL.md.

The Aggregate Flow Engine MUST NOT directly implement product-specific interfaces.


---

3.4 Patient Generator

Responsibility:

Create one synthetic patient entity for each synthetic arrival.

Each patient must contain the approved minimum fields defined in MODEL.md.

The Patient Generator is an HFSG engineering extension.

It MUST NOT be represented as part of the original scientific paper.

Patient attributes MUST be generated from approved configurable distributions.


---

3.5 Patient Event Generator

Responsibility:

Convert aggregate flow quotas into individual patient events.

Supported event types:

ARRIVAL
TRANSFER
DISCHARGE
DEATH

The Event Generator MUST follow the patient selection rules in MODEL.md.

It MUST preserve:

patient identity;

chronological ordering;

valid patient location;

terminal-state rules;

aggregate reconciliation.



---

3.6 Reconciliation Layer

Responsibility:

Verify consistency between aggregate simulation and patient-level data.

It MUST verify:

Patient stock = Aggregate stock

and:

Patient events = Aggregate flows

for every required simulation hour and flow.

A critical reconciliation failure MUST stop production Batch generation.


---

3.7 Validation Layer

Responsibility:

Validate simulation and generated data.

It MUST implement the validation requirements from MODEL.md, including:

non-negative stocks;

flow/source constraints;

capacity constraints;

destination-share invariant;
NaN/Inf checks;

mass balance;

unique patient IDs;

unique event IDs;

chronological events;

no post-terminal events;

one active location per patient;

aggregate/patient reconciliation;

reproducibility;

scenario coverage.


Validation MUST NOT be treated as an optional reporting feature.


---

3.8 Output Layer

Responsibility:

Write approved simulation and dataset outputs.

Required outputs include:

patients.parquet
patient_events.parquet
aggregate_timeseries.parquet
simulation_summary.parquet
scenario_comparison.csv
dataset_manifest.json
validation_report.json
used_configuration.yaml

The Output Layer MUST support chunked writing for large datasets.

The full Dataset MUST NOT be held in memory.


---

4. Data Flow

The approved data flow is:

YAML Configuration
        ↓
Configuration Loader
        ↓
Scenario Selection
        ↓
Validated Parameters
        ↓
Aggregate Flow Engine
        ↓
Aggregate Stocks / Flows
        ↓
Patient Generator
        ↓
Patient Entities
        ↓
Patient Event Generator
        ↓
Patient Events
        ↓
Reconciliation
        ↓
Validation
        ↓
Output Writer
        ↓
Parquet / JSON / CSV

Configuration flows downward into the system.

Validation and reconciliation operate across the generated outputs.


---

5. Separation of Responsibilities

The implementation MUST preserve the following boundaries:

Component Primary Responsibility

Configuration Parameters and configuration validation
Scenario Scenario selection and approved parameter overrides
Aggregate Engine Model B hospital-flow simulation
Patient Generator Synthetic patient creation
Event Generator Individual patient events
Reconciliation Aggregate ↔ patient consistency
Validation Correctness and invariant checks
Output Dataset and metadata writing


A component SHOULD NOT silently take over the responsibility of another component.


---

6. Configuration-Driven Design

Configurable values MUST remain outside the mathematical engine whenever practical.

Examples include:

capacities;

arrival rates;

seasonal parameters;

destination shares;

transfer rates;

discharge rates;

death rates;

initial conditions;

patient distributions;

scenario modifications;

random seeds;

output settings.


The engine reads these values from approved configuration.

Scenario changes MUST be expressed as configuration changes rather than duplicated code paths.


---

7. Simulation Execution

A simulation run follows this logical sequence:

1. Load configuration
2. Validate configuration
3. Select scenario
4. Apply approved scenario overrides
5. Initialize random seed
6. Initialize aggregate stocks
7. Initialize patient state
8. Run simulation step
9. Generate aggregate flows
10. Generate patient events
11. Reconcile patient state with aggregate state
12. Run validation
13. Write outputs
14. Generate simulation summary
15. Generate validation report

All simulation steps MUST follow the rules in MODEL.md.


---

8. Scenario Architecture

All scenarios use the same engine:

┌── S1
                 ├── S2
                 ├── S3
                 ├── S4
                 ├── S5
Configuration ───┼── S6 ──→ Same Core Engine
                 ├── S7
                 ├── S8
                 └── CUSTOM

The scenario system MUST NOT branch into separate mathematical implementations.

A scenario modifies approved parameters only.


---

9. Reproducibility Architecture

Each simulation must have an identifiable execution context containing:

model version;

configuration version;

scenario ID;

simulation ID;

random seed;

generation timestamp.


The random-number generation system MUST be controlled by the simulation seed.

A fixed configuration and seed must reproduce the defined test fixture.


---

10. Batch Architecture

Large Dataset generation MUST use incremental processing.

Logical flow:

Scenario
    ↓
Simulation Run
    ↓
Generate Patient Chunk
    ↓
Generate Event Chunk
    ↓
Validate Chunk / State
    ↓
Write Parquet
    ↓
Release Memory
    ↓
Next Chunk / Run

The entire Dataset MUST NOT be accumulated in RAM.
Approved planning values include:

patient chunk: 50,000;

event chunk: 100,000;

compression: ZSTD;

partition key: scenario_id.



---

11. Output Architecture

The output structure must preserve separation between:

Patient Data

patients.parquet

Event Data

patient_events.parquet

Aggregate Data

aggregate_timeseries.parquet

Run-Level Data

simulation_summary.parquet

Metadata and Validation

dataset_manifest.json
validation_report.json
used_configuration.yaml

Scenario comparison output:

scenario_comparison.csv


---

12. Error and Failure Handling

The system MUST distinguish between normal execution errors and specification-level problems.

Configuration Error

Invalid configuration MUST prevent simulation from starting.

Validation Failure

A failed invariant MUST be reported by the Validation Layer.

Critical Failure

Mass-balance failure or aggregate/patient reconciliation failure MUST be treated as critical for production Batch generation.

Specification Conflict

If project documents conflict:

SPEC_CONFLICT

must be reported.

Missing Decision

If an implementation decision is required but not approved:

DECISION_REQUIRED

must be reported.

The system MUST NOT silently invent a resolution.


---

13. Testing Architecture

Testing SHOULD be organized around component responsibilities.

At minimum, tests must cover:

configuration validation;

scenario configuration;

aggregate equations;

capacity constraints;

simultaneous updates;

mass balance;

patient uniqueness;

event uniqueness;

patient state invariants;

aggregate-to-patient reconciliation;

random-seed reproducibility;

scenario execution;

output readability.


Tests MUST NOT bypass validation rules.


---

14. Architecture Boundaries

Phase 1 architecture MUST NOT require:

cloud infrastructure;

microservices;

external databases;

public APIs;

authentication;

payment infrastructure;

HIS/EHR/FHIR integration;

machine learning infrastructure;

LLM infrastructure;

digital twin infrastructure.


These are outside the approved Phase 1 architecture.


---

15. Implementation Principle

The architecture should remain as simple as possible while satisfying the approved Phase 1 requirements.

The implementation MUST prioritize:

1. correctness;


2. reproducibility;


3. validation;


4. configuration-driven behaviour;


5. aggregate/patient consistency;


6. maintainability;


7. scalable Batch output.



Do not introduce architectural complexity without an approved requirement.


---

16. Architecture Completion Criteria

The Phase 1 architecture is considered implemented when:

the approved configuration can reach the simulation engine;

the same Core Engine can execute Standard-8 and CUSTOM;

Model B is implemented without duplicated scenario engines;

patient generation follows aggregate arrivals;

patient events follow aggregate flows;

reconciliation is enforced;

validation is integrated into execution;

outputs are generated in the approved formats;

Batch generation can operate without holding the complete Dataset in memory;

reproducibility requirements are preserved.
