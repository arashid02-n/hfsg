# HFSG — OpenCode Agent Instructions

**Project:** Hospital Flow Scenario Generator  
**Document Status:** FROZEN v1.0  
**Frozen Date:** 2026-08-18  
**Implementation Target:** Phase 1 — MVP

---

## 1. Project Identity

HFSG is a synthetic hospital-flow simulation and data-generation system.

Phase 1 must produce a small but fully executable system capable of:

- aggregate hospital-flow simulation;
- synthetic initial and arrival patient generation;
- patient-event generation;
- integer patient quota allocation;
- Standard-8 scenarios;
- one CUSTOM scenario;
- aggregate/patient reconciliation;
- validation;
- reproducible simulation;
- Parquet output;
- Batch generation;
- final validation and dataset packaging.

---

## 2. Authoritative Project Documents

| Concern | Authority |
|---|---|
| Agent behaviour | `AGENTS.md` |
| Model behaviour/equations/invariants | `MODEL.md` |
| Parameter values | approved YAML |
| Product scope | `PRODUCT.md` |
| Software structure | `ARCHITECTURE.md` |
| Operational workflow | `OPERATIONS.md` |
| Scientific provenance | original scientific paper |
| Reference material | supporting PDFs/XLSX |

Rules:

- `AGENTS.md` MUST NOT override `MODEL.md` on mathematical/simulation behaviour.
- `ARCHITECTURE.md` MUST NOT override `MODEL.md` on model behaviour.
- `OPERATIONS.md` MUST NOT override `PRODUCT.md` or `MODEL.md`.
- the source paper MUST NOT silently override approved Model B.

---

## 3. Model Distinction

Model A is scientific reference/provenance.

Model B is the production model.

HFSG engineering extensions include:

- stochastic arrivals;
- explicit capacity controls;
- integer flow allocation;
- initial patient population;
- patient-level entities;
- Patient Generator;
- Patient Event Generator;
- scenario framework;
- Batch generation;
- Parquet output;
- reconciliation;
- validation;
- product versioning.

Do not claim these extensions are directly published findings/equations from the source article.

---

## 4. Scope Control

Implement only approved Phase 1 requirements.

Do NOT independently add:

- ML;
- LLM functionality;
- digital twin functionality;
- clinical variables;
- diagnoses;
- medications;
- labs;
- vital signs;
- clinical notes;
- new departments;
- new patient routes;
- HIS/EHR/FHIR;
- public APIs;
- authentication;
- payment systems;
- multi-user administration;
- database infrastructure;
- cloud architecture.

Do not turn Phase 1 into a larger platform.

---

## 5. No Silent Decisions

If a required decision is missing or ambiguous, report:

`DECISION_REQUIRED`

Do not invent it.

Examples:

- missing scenario values;
- missing capacity rules;
- missing patient routes;
- missing patient distributions;
- missing selection rules;
- missing calibration values;
- unapproved replacement integerization rule;
- unapproved intra-timestep behaviour;
- unspecified initial-patient prior-stay rule where required.

---

## 6. Conflict Handling

If authoritative documents disagree, report:

`SPEC_CONFLICT`

Identify:

1. conflicting documents;
2. conflicting statements;
3. required implementation decision.

Do not silently rewrite a specification to match code.

---

## 7. Configuration Rules

Model parameters MUST come from approved configuration.

Do not silently hard-code configurable parameters.

Scenario definitions MUST come from configuration.

Scenario logic MUST NOT change the mathematical model.

---

## 8. Standard Scenario Pack

Approved scenarios:

- S1 — Normal Operation
- S2 — Busy Week
- S3 — Crisis Mode
- S4 — ICU Capacity Loss
- S5 — Bed Block
- S6 — Compound Stress
- S7 — Emergency Wave
- S8 — Recovery Strategy
- CUSTOM — Customer Scenario

All use the same Core Engine.

---

## 9. Model Invariants

All implementation MUST preserve `MODEL.md` invariants.

In particular:

- no negative stocks;
- no flow greater than source stock;
- no unauthorized capacity violation;
- destination shares sum to one;
- no NaN/Inf;
- mass balance passes;
- valid integer allocation;
- unique patient IDs;
- unique event IDs;
- chronological events;
- no post-terminal events;
- one active location per patient;
- aggregate/patient reconciliation passes;
- seed reproducibility.

Do not weaken validation to make a run pass.

---

## 10. Aggregate-to-Patient Authority

The Aggregate Engine determines HOW MANY patients move.

The Patient Event Generator determines WHICH patients move.

The Patient Event Generator MUST NOT independently modify approved integer patient quotas.

Raw continuous flows MUST be converted to integer patient quotas using:

`Largest Remainder Method + seeded deterministic tie-break`

Do not replace it without explicit approval.

---

## 11. Initial Patient Population

At simulation initialization, patient entities MUST be created to match approved initial active stocks:

- `E(0)`
- `C(0)`
- `G(0)`
- `I(0)`

Do not start patient-level simulation with an empty patient population when aggregate initial stocks are non-zero.

If a required initial-patient attribute is not specified, report `DECISION_REQUIRED`.

---

## 12. Timestep Eligibility

Patients arriving during timestep `t` MUST NOT be eligible for transfer, discharge, or death during timestep `t`.

Eligibility begins at `t+1`.

---

## 13. Capacity Timing

Destination capacity MUST be evaluated using beginning-of-step occupancy.

Capacity released during timestep `t` becomes available beginning at `t+1`.

Do not implement intra-timestep bed reuse in Phase 1.

---

## 14. Patient-Level Rules

Every patient has a unique `patient_id`.

Every event has a unique `event_id`.

A patient:

- cannot occupy two units simultaneously;
- cannot transfer before arrival;
- cannot have events after discharge;
- cannot have events after death;
- must have a valid terminal outcome or approved active-at-end state;
- must remain consistent with aggregate state.

---

## 15. Scientific Parameter Provenance

Every model parameter must have one appropriate provenance classification:

- `PAPER`
- `TRANSFORMED`
- `EXPERT`
- `ASSUMPTION`
- `CALIBRATED`

Do not label an assumption as `PAPER`.

---

## 16. Validation Behaviour

Validation is required.

A successful program exit does not mean valid data.

Critical reconciliation or mass-balance failure MUST fail the affected production Batch.

Do not suppress validation failures.

---

## 17. Reproducibility

Every Batch MUST use a controlled `master_seed`.

Each run MUST use a deterministic child seed derived from:

- master seed;
- scenario ID;
- run index.

The child seed MUST be recorded.

Do not introduce uncontrolled randomness.

---

## 18. Output Requirements

Approved outputs:

- `patients.parquet`
- `patient_events.parquet`
- `aggregate_timeseries.parquet`
- `simulation_summary.parquet`
- `scenario_comparison.csv`
- `dataset_manifest.json`
- `validation_report.json`
- `used_configuration.yaml`

Do not replace required formats without approval.

The complete Dataset MUST NOT be held in RAM.

---

## 19. Development Workflow

Before implementing a component:

1. read relevant specification;
2. identify inputs;
3. identify outputs;
4. identify invariants;
5. implement the smallest approved version;
6. run relevant tests;
7. inspect outputs;
8. fix failures;
9. only then continue.

Do not implement the entire project in one uncontrolled operation.

---

## 20. Phase 1 Implementation Order

```text
Documentation
    ↓
Repository / Environment
    ↓
Configuration / YAML
    ↓
Aggregate Simulation Engine
    ↓
Integer Flow Allocator
    ↓
S1 Baseline
    ↓
Validation
    ↓
Initial Patient Population
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
100k Dry Run
    ↓
Batch Generation
    ↓
Final Validation
    ↓
Release Package
```

Do not skip foundational validation.

---

## 21. Batch Generation Rules

Commercial target:

`>= 1,000,000 patient records`

Completion requires BOTH:

1. target volume reached;
2. required Standard-8 coverage complete.

Current planning values:

- patient write buffer: 50,000;
- event write buffer: 100,000;
- ZSTD compression;
- partition key: `scenario_id`.

Do not load the complete Dataset into memory.

---

## 22. Code Quality Rules

Keep implementation:

- modular;
- readable;
- testable;
- deterministic where required;
- configuration-driven;
- consistent with `MODEL.md`;
- free of duplicated scenario-specific model logic.

Do not introduce unnecessary frameworks or infrastructure.

---

## 23. Phase 1 Simplicity Rule

When multiple implementations satisfy the approved specification, prefer the simplest implementation that:

- preserves `MODEL.md` invariants;
- passes required tests;
- is reproducible;
- is readable;
- is configuration-driven;
- works within available hardware constraints.

Do not optimize for hypothetical future requirements.

---

## 24. Change Rules

Do not modify without explicit project decision:

- mathematical equations;
- model structure;
- integerization method;
- timestep eligibility;
- capacity timing;
- scenario definitions;
- validation requirements;
- patient selection rules;
- product scope;
- frozen documentation.

---

## 25. Documentation Consistency

If implementation conflicts with frozen documentation, stop and report:

`SPEC_CONFLICT`

Do not silently rewrite specifications to match code.

---

## 26. Task Completion Reporting

Before reporting an implementation task complete:

1. run relevant unit tests;
2. run relevant validation tests;
3. inspect generated outputs;
4. confirm no approved invariant is violated;
5. report files changed;
6. report tests executed;
7. report PASS/FAIL status;
8. report unresolved `DECISION_REQUIRED` or `SPEC_CONFLICT`.

Do not report completion when relevant tests have not been executed.

---

## 27. Definition of Done

A component is complete only when:

- approved behaviour is implemented;
- required tests pass;
- validation passes;
- outputs match approved schema;
- reproducibility requirements are satisfied;
- no unresolved `DECISION_REQUIRED` affects the component;
- no unresolved `SPEC_CONFLICT` affects the component.

Phase 1 is complete only when Product Success Criteria in `PRODUCT.md` are satisfied.
