# HFSG — Operations Specification

**Project:** Hospital Flow Scenario Generator  
**Operations Version:** 1.0  
**Document Status:** FROZEN v1.0  
**Frozen Date:** 2026-08-18  
**Implementation Target:** Phase 1 — MVP

---

## 1. Purpose

This document defines how HFSG is configured, executed, validated, tested, and used during Phase 1.

It does NOT define the mathematical model.

- Model behaviour: `MODEL.md`
- Product scope: `PRODUCT.md`
- Software structure: `ARCHITECTURE.md`
- Agent behaviour: `AGENTS.md`

---

## 2. Operating Principle

```text
Configuration
    ↓
Configuration Validation
    ↓
Scenario Selection
    ↓
Simulation Initialization
    ↓
Aggregate Simulation
    ↓
Integer Patient Quotas
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
    ↓
Release Gate
```

Program completion does not imply data validity.

Validation MUST pass before a production Dataset can become technically releasable.

---

## 3. Required Environment

The exact OS, Python version, dependency versions, and installation commands MUST be defined by the actual implementation environment and recorded by the engineer.

They MUST NOT be invented by the agent before the environment exists.

---

## 4. Repository Structure

The repository SHOULD maintain separation between source code, configuration, tests, documentation, and generated outputs.

Large generated datasets SHOULD NOT be committed to Git unless explicitly required.

---

## 5. Configuration Workflow

Before running a simulation:

1. load approved YAML;
2. validate base configuration;
3. select scenario;
4. apply approved scenario overrides;
5. validate resulting configuration;
6. initialize simulation.

Invalid configuration MUST prevent simulation start.

---

## 6. Scenario Execution

Approved Standard-8:

- S1 — Normal Operation
- S2 — Busy Week
- S3 — Crisis Mode
- S4 — ICU Capacity Loss
- S5 — Bed Block
- S6 — Compound Stress
- S7 — Emergency Wave
- S8 — Recovery Strategy

Also supported:

- CUSTOM — Customer Scenario

Every scenario uses the same Core Engine.

---

## 7. Single Simulation Run

### Run Initialization

1. Load configuration.
2. Validate configuration.
3. Select scenario.
4. Apply approved overrides.
5. Validate resulting configuration.
6. Create simulation ID.
7. Initialize controlled RNG.
8. Initialize aggregate stocks.
9. Generate initial patient population matching `E(0), C(0), G(0), I(0)`.
10. Reconcile initial aggregate and patient states.

### For Every Timestep

11. Read beginning-of-step aggregate state.
12. Read beginning-of-step patient state.
13. Generate new arrivals.
14. Create patient entities for those arrivals.
15. Calculate requested aggregate flows.
16. Apply source-stock constraints.
17. Apply beginning-of-step destination-capacity constraints.
18. Convert constrained aggregate flows to integer patient quotas using `MODEL.md`.
19. Select WHICH patients satisfy each integer quota.
20. Generate patient events.
21. Update aggregate stocks simultaneously.
22. Update patient states.
23. Reconcile aggregate and patient states.
24. Run timestep validation.
25. Buffer approved outputs.

### Run Completion

26. Flush remaining output buffers.
27. Generate simulation summary.
28. Run run-level validation.
29. Write validation report.
30. Record run metadata.

Default horizon: `720 hours`

Default timestep: `1 hour`

---

## 8. Integer Patient Quota Operation

Approved method:

`Largest Remainder Method + seeded deterministic tie-break`

Operational sequence:

```text
Raw Constrained Aggregate Flow
    ↓
Integer Flow Allocation
    ↓
Integer Patient Quota
    ↓
Patient Selection
    ↓
Patient Events
```

The Patient Event Generator MUST NOT receive unrestricted fractional patient quotas.

---

## 9. Initial Patient Population Gate

Before the first normal simulation timestep, patient entities MUST exist for all non-zero initial active stocks.

Current baseline:

- ED = 20
- Specialty = 25
- General Ward = 60
- ICU = 10

Initial aggregate-to-patient reconciliation MUST PASS before the run continues.

---

## 10. Timestep Eligibility

Patients generated as arrivals during timestep `t` MUST NOT be eligible for transfer, discharge, or death during timestep `t`.

They become eligible beginning at timestep `t+1`.

---

## 11. Capacity Timing

For Phase 1, destination capacity is evaluated using beginning-of-step occupancy.

Beds released during timestep `t` become available beginning at timestep `t+1`.

Operations MUST NOT assume intra-timestep bed reuse.

---

## 12. Random Seed and Reproducibility

Every simulation MUST record:

- simulation ID;
- scenario ID;
- random seed / child seed;
- model version;
- configuration version;
- generation timestamp.

### Batch Seed Policy

A Batch MUST define one `master_seed`.

Each simulation run MUST derive a deterministic child seed from:

- master seed;
- scenario ID;
- run index.

The derived child seed MUST be recorded.

Volatile metadata such as generation timestamp MUST be excluded or normalized in reproducibility comparisons unless a fixed test timestamp is configured.

---

## 13. Baseline Execution — Gate G1

Before Standard-8 validation or Batch generation, S1 MUST pass a small Demo/Development run.

Recommended Demo scale:

`approximately 2,000–10,000 patients`

G1 requires:

- valid stocks;
- valid flows;
- valid integer quotas;
- mass balance PASS;
- patient generation PASS;
- event generation PASS;
- reconciliation PASS;
- readable outputs.

Failure blocks progression.

---

## 14. Validation Workflow

Validation occurs during and after simulation.

Critical failures MUST remain visible.

Do not silently repair invalid generated data.

---

## 15. Standard-8 Validation

All Standard-8 scenarios MUST execute and validate:

```text
S1 PASS
S2 PASS
S3 PASS
S4 PASS
S5 PASS
S6 PASS
S7 PASS
S8 PASS
```

CUSTOM must also be executable with approved configuration.

---

## 16. Dry Run — Gate G2

Before the production one-million-patient Batch, the system MUST successfully complete an approximately:

`100,000 patient`

dry run.

G2 must confirm:

- chunked writing;
- memory behaviour;
- checkpoint/resume behaviour;
- Parquet readability;
- metadata generation;
- validation;
- reconciliation.

Failure blocks the one-million-patient Batch.

---

## 17. Production Batch — Gate G3

Commercial target:

`>= 1,000,000 patient records`

Batch completion requires BOTH:

1. target patient count reached; and
2. required Standard-8 scenario coverage complete.

The target count alone is insufficient.

Chunk settings are memory/output settings only and MUST NOT change simulation semantics.

---

## 18. Batch Recovery and Checkpointing

Production Batch generation MUST support restart/resume.

The Batch process MUST persist enough checkpoint information to recover safely, including:

- completed simulation IDs;
- current scenario;
- current generated patient count;
- current generated event count;
- output partition state;
- deterministic seed derivation information.

An interrupted Batch MUST NOT require restarting from zero when valid completed partitions exist.

A critical reconciliation or mass-balance failure MUST stop the affected production Batch.

---

## 19. Output Generation

Production Dataset generation MUST produce:

- `patients.parquet`
- `patient_events.parquet`
- `aggregate_timeseries.parquet`
- `simulation_summary.parquet`
- `scenario_comparison.csv`
- `dataset_manifest.json`
- `validation_report.json`
- `used_configuration.yaml`

---

## 20. Output Inspection

After generation:

1. confirm expected files exist;
2. confirm files are readable;
3. inspect row counts;
4. inspect schema;
5. inspect scenario ID;
6. inspect simulation ID;
7. inspect validation status;
8. inspect patient/event uniqueness;
9. inspect reconciliation;
10. inspect metadata.

Manifest record counts MUST equal actual Parquet record counts.

`configuration_hash` MUST correspond to the preserved `used_configuration.yaml`.

---

## 21. Batch Scenario Coverage

A Standard Dataset MUST represent all eight scenarios.

The minimum completed-run requirement per scenario MUST come from approved configuration.

OpenCode MUST NOT invent a minimum coverage count.

---

## 22. Batch Failure Policy

A production Dataset is `REJECTED` / `NOT RELEASABLE` when critical validation fails, required scenario coverage is missing, required outputs are absent/unreadable, or metadata is incomplete.

---

## 23. Dataset Identity

Each production Dataset MUST receive a stable Dataset ID.

Reserved IDs MUST NOT be silently reused for a different failed or replacement build.

Example:

`HFSG-DS-STD8-2026-0001`

---

## 24. Release States

Operational release states:

1. `DEVELOPMENT`
2. `VALIDATED`
3. `RELEASED`
4. `REJECTED`

Validation PASS moves a technically valid dataset to `VALIDATED`.

Only explicit project-owner approval moves it to `RELEASED`.

---

## 25. Development vs Validation vs Production

### Development Run
Small, fast, debugging-oriented.

### Validation Run
Complete behaviour validation including Standard-8.

### Production Batch
Commercial target volume and complete product metadata.

Do not use a large production Batch as the primary debugging method.

---

## 26. Logging

At minimum logs SHOULD identify:

- simulation ID;
- scenario ID;
- configuration version;
- model version;
- master/child seed;
- execution status;
- validation status;
- errors/critical failures.

---

## 27. Operational Troubleshooting

When a run fails:

1. identify failure type;
2. identify responsible component;
3. inspect configuration;
4. inspect validation output;
5. reproduce with the smallest useful case;
6. fix the underlying issue;
7. rerun affected validation;
8. only then continue.

Do not bypass failed validation.

---

## 28. Operational Decision Rules

Missing required value: `DECISION_REQUIRED`

Specification conflict: `SPEC_CONFLICT`

Critical generated-data/model violation: `CRITICAL`

These states MUST remain visible in logs/reports.

---

## 29. Phase 1 Operational Completion

Phase 1 operations are complete when the system can:

1. load approved configuration;
2. execute S1 baseline;
3. generate valid initial and arrival patient data;
4. generate valid patient events;
5. reconcile aggregate and patient data;
6. validate simulation;
7. execute S1–S8;
8. execute CUSTOM;
9. generate required outputs;
10. pass G1 Demo;
11. pass 100,000-patient G2 dry run;
12. perform approved `>=1,000,000` patient Batch;
13. satisfy Standard-8 coverage;
14. produce Dataset metadata;
15. produce Validation Report;
16. reach `VALIDATED`;
17. support project-owner approval to `RELEASED`.

Final technical validation condition:

`validation_status = PASS`
