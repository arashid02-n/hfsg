AGENTS.md

HFSG — OpenCode Agent Instructions

1. Project Identity

Project: Hospital Flow Scenario Generator
Abbreviation: HFSG

HFSG is a synthetic hospital-flow simulation and data-generation system.

The current implementation target is Phase 1 — MVP.

The goal of Phase 1 is to produce a small but fully executable system capable of:

aggregate hospital-flow simulation;

synthetic patient generation;

patient-event generation;

Standard-8 scenarios;

one CUSTOM scenario;

aggregate/patient reconciliation;

validation;

reproducible simulation;

Parquet output;

Batch generation;

final validation and dataset packaging.



---

2. Authoritative Project Documents

Before making implementation decisions, read the relevant project documentation.

The repository contains:

PRODUCT.md
MODEL.md
ARCHITECTURE.md
OPERATIONS.md
AGENTS.md

Their responsibilities are:

File Authority

AGENTS.md Agent behaviour and development rules
MODEL.md Model behaviour, equations, invariants and validation rules
Approved YAML configuration Parameter values
PRODUCT.md Product scope and requirements
ARCHITECTURE.md Approved software structure
OPERATIONS.md Approved operational workflow
Original scientific paper Scientific provenance
Supporting PDFs/XLSX Reference material


For model behaviour, MODEL.md is authoritative.

For product scope, PRODUCT.md is authoritative.

For implementation parameters, approved YAML configuration is authoritative.

The original scientific paper provides scientific provenance and MUST NOT silently override the approved HFSG production model.


---

3. Model Distinction

HFSG contains two conceptually separate model layers.

Model A — Scientific Reference Model

Based on Al-Karkhi & Byatt (2025).

It is used for:

scientific provenance;

comparison;

understanding the original compartmental model.


The paper does not define the HFSG individual synthetic Patient Generator or Patient Event Generator.

Model B — HFSG Production Model

Model B is the actual model to be implemented by the HFSG Core Engine.

The following are HFSG engineering extensions and MUST remain distinguishable from the original paper:

stochastic arrival generation;

explicit capacity controls;

patient-level entities;

Patient Generator;

Patient Event Generator;

scenario framework;

Batch generation;

Parquet output;

reconciliation;

product validation;

product versioning.


Do not claim these extensions are findings or equations directly published in the source paper.


---

4. Scope Control

Implement only approved requirements.

Do NOT independently expand the project.

Do NOT add:

machine learning;

LLM functionality;

digital twin functionality;

clinical variables;

diagnosis generation;

medication data;

laboratory data;

vital signs;

clinical notes;

new hospital departments;

new patient routes;

HIS/EHR/FHIR integration;

public APIs;

authentication;

payment systems;

multi-user administration;

database infrastructure;

cloud architecture;


unless explicitly approved by the project owner.

Do not turn Phase 1 into a larger commercial platform.


---

5. No Silent Decisions

If a required implementation decision is missing or ambiguous, do NOT invent it.

Use:

DECISION_REQUIRED

Examples include:

missing clinical variables;

missing diagnosis probabilities;

missing mortality parameters;

missing patient attribute distributions;

missing scenario multipliers;

missing capacity rules;

missing patient routes;

missing ICU priorities;

missing discharge/death selection rules;

missing real-hospital calibration parameters.


Stop the affected implementation and identify the missing decision.


---

6. Conflict Handling

If authoritative project documents disagree, do NOT silently choose one.

Report:

SPEC_CONFLICT

Identify:

1. the conflicting documents;


2. the conflicting statements;


3. the implementation decision that is required.



Do not modify one specification merely to remove the conflict.


---

7. Configuration Rules

Model parameters MUST come from approved configuration.
Do not silently hard-code configurable parameters into the simulation engine.

Scenario definitions MUST come from configuration.

Scenario logic MUST NOT modify the mathematical model or create separate mathematical engines.

A scenario changes approved parameters, not model structure.


---

8. Standard Scenario Pack

The approved scenario set is:

S1 — Normal Operation
S2 — Busy Week
S3 — Crisis Mode
S4 — ICU Capacity Loss
S5 — Bed Block
S6 — Compound Stress
S7 — Emergency Wave
S8 — Recovery Strategy
CUSTOM — Customer Scenario

All Standard-8 scenarios and CUSTOM must use the same approved HFSG Core Engine.

Do not create separate simulation engines for individual scenarios.


---

9. Model Invariants

All implementation MUST preserve the invariants defined in MODEL.md.

In particular:

no negative stocks;

no flow greater than source stock;

no unauthorized capacity violation;

destination shares sum to one;

no NaN/Inf;

mass balance passes;

unique patient IDs;

unique event IDs;

chronological events;

no post-terminal events;

one active location per patient;

aggregate/patient reconciliation passes;

seed reproducibility.


Do not weaken or remove validation rules to make a simulation pass.


---

10. Patient-Level Rules

Every synthetic patient must have a unique:

patient_id

Every event must have a unique:

event_id

Patient events MUST obey the rules in MODEL.md.

A patient:

cannot occupy two units simultaneously;

cannot transfer before arrival;

cannot have events after discharge;

cannot have events after death;

must have a valid terminal outcome;

must remain consistent with aggregate flows.


Patient-level behaviour must reconcile with the aggregate model.


---

11. Scientific Parameter Provenance

Every model parameter must have an appropriate provenance classification:

PAPER
TRANSFORMED
EXPERT
ASSUMPTION
CALIBRATED

Do not label an assumed parameter as PAPER.

Patient attributes such as age group, sex, severity and arrival mode must remain configurable assumptions unless explicitly supported by an approved source.


---

12. Validation Behaviour

Validation is a required part of the implementation.

A successful execution is not defined merely by the program completing without an exception.

The system must verify the approved validation requirements.

A critical reconciliation or mass-balance failure MUST cause the affected production Batch to fail.

Do not suppress validation errors.

Do not convert validation failures into warnings without explicit approval.


---

13. Reproducibility

Every simulation must preserve:

model version;

configuration version;

scenario ID;

simulation ID;

random seed;

generation timestamp.


Fixed configuration and fixed seed must reproduce the defined deterministic/stochastic test fixture.

Do not introduce uncontrolled randomness.


---

14. Output Requirements

The approved outputs include:

patients.parquet
patient_events.parquet
aggregate_timeseries.parquet
simulation_summary.parquet
scenario_comparison.csv
dataset_manifest.json
validation_report.json
used_configuration.yaml

Do not replace required outputs with arbitrary formats without approval.

The complete dataset MUST NOT be kept in RAM during Batch generation.


---

15. Development Workflow

Work incrementally.

Before implementing a new component:

1. read the relevant specification;


2. identify its inputs;


3. identify its outputs;


4. identify its invariants;


5. implement the smallest approved version;


6. run the relevant tests;


7. inspect the output;


8. fix failures;


9. only then continue.



Do not implement the entire project in one uncontrolled operation.


---

16. Phase 1 Implementation Order

The intended implementation sequence is:

Documentation
    ↓
Repository / Environment
    ↓
Configuration / YAML
    ↓
Aggregate Simulation Engine
    ↓
S1 Baseline
    ↓
Validation
    ↓
Patient Generator
    ↓
Patient Event Generator
    ↓
Aggregate ↔ Patient Reconciliation
    ↓
S1–S8 + CUSTOM
    ↓
Output Pipeline
    ↓
Batch Generation
    ↓
Final Validation
    ↓
Release Package
Do not skip foundational validation and move directly to large-scale Batch generation.


---

17. Batch Generation Rules

The commercial Dataset target is:

>= 1,000,000 patient records

The Batch process must use chunked generation and writing.

Current approved planning configuration:

patient chunk: 50,000 rows;

event chunk: 100,000 rows;

Parquet compression: ZSTD;

partition key: scenario_id.


Do not load the complete Dataset into memory.


---

18. Code Quality Rules

Keep the implementation:

modular;

readable;

testable;

deterministic where required;

configuration-driven;

consistent with MODEL.md;

free of duplicated scenario-specific model logic.


Do not introduce unnecessary frameworks or infrastructure.

Prefer simple implementations that satisfy the approved specification.


---

19. Change Rules

Do not modify:

mathematical equations;

model structure;

scenario definitions;

validation requirements;

patient selection rules;

product scope;

authoritative documentation;


without an explicit project decision.

If a change is necessary, identify it before implementing it.


---

20. Documentation Consistency

When implementation changes an approved behaviour, documentation must not silently become outdated.

If a proposed implementation conflicts with PRODUCT.md or MODEL.md, stop and report:

SPEC_CONFLICT

Do not silently rewrite the specification to match the code.


---

21. Definition of Done

A component is not considered complete merely because its code runs.

It is complete only when:

its approved behaviour is implemented;

required tests pass;

validation rules pass;

outputs match the approved schema;

reproducibility requirements are satisfied;

no unresolved DECISION_REQUIRED remains for that component;

no unresolved SPEC_CONFLICT affects the implementation.


Phase 1 is complete only when its approved Product Success Criteria in PRODUCT.md are satisfied.
