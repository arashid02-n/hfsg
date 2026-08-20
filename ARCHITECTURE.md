# HFSG — Software Architecture Specification

**Project:** Hospital Flow Scenario Generator  
**Architecture Version:** 1.0  
**Document Status:** FROZEN v1.0  
**Frozen Date:** 2026-08-18  
**Implementation Target:** Phase 1 — MVP

---

## 1. Architecture Purpose

This document defines the software architecture required to implement the approved HFSG Phase 1 MVP.

The architecture MUST:

- implement approved Model B from `MODEL.md`;
- respect product scope defined in `PRODUCT.md`;
- separate model logic from configuration;
- separate aggregate simulation from patient-level generation;
- preserve aggregate-to-patient reconciliation;
- support Standard-8 and CUSTOM scenarios;
- support reproducible simulation;
- support validation;
- support chunked dataset generation.

The architecture MUST remain simple and focused on Phase 1.

---

## 2. Core Architecture

```text
Approved Configuration
        ↓
Configuration Loader
        ↓
Scenario Manager
        ↓
Simulation Context
        ↓
Initial Aggregate State + Initial Patient Population
        ↓
Aggregate Flow Engine
        ↓
Raw Constrained Aggregate Flows
        ↓
Integer Flow Allocator
        ↓
Integer Patient Quotas
        ↓
Patient Event Generator
        ↓
Updated Patient State
        ↓
Aggregate ↔ Patient Reconciliation
        ↓
Validation
        ↓
Output Buffer
        ↓
Chunked Output Writer
        ↓
Final Validation
        ↓
Release Gate
```

The same Core Engine MUST be used for Demo, Dataset, Generator, Standard-8, and CUSTOM.

The simulation model MUST NOT be duplicated for different products or scenarios.

---

## 3. Major Components

### 3.1 Configuration Layer
Loads and validates approved YAML configuration. It contains no simulation logic.

### 3.2 Scenario Layer
Selects S1-S8 or CUSTOM and applies approved parameter overrides. It MUST NOT alter equations or model structure.

### 3.3 Simulation Context
Carries stable execution identity:

- `simulation_id`
- `scenario_id`
- `model_version`
- `configuration_version`
- `master_seed` where applicable
- `child_seed`
- `start_datetime`
- `generation_timestamp`

### 3.4 Aggregate Flow Engine
Implements Model B and calculates arrivals, ED processing, transfers, discharges, deaths, capacity constraints, unmet demand, and simultaneous stock updates.

### 3.5 Integer Flow Allocator
Converts constrained continuous flows into integer patient quotas using:

`Largest Remainder Method + seeded deterministic tie-break`

It MUST preserve source-stock limits, destination-capacity limits, and approved total integer outflow.

### 3.6 Patient Generator / Patient State
Creates:

1. initial patient population matching initial stocks;
2. one new patient entity for each synthetic arrival.

### 3.7 Patient Event Generator
Converts integer quotas into individual ARRIVAL/TRANSFER/DISCHARGE/DEATH events.

The Aggregate Engine determines HOW MANY.  
The Event Generator determines WHICH patients.

### 3.8 Reconciliation Layer
Verifies:

```text
Patient stock = Aggregate stock
Patient events = Integer patient quotas
```

A critical reconciliation failure MUST stop production Batch generation.

### 3.9 Validation Layer
Implements all validation requirements from `MODEL.md`.

### 3.10 Output Layer
Buffers and writes:

- `patients.parquet`
- `patient_events.parquet`
- `aggregate_timeseries.parquet`
- `simulation_summary.parquet`
- `scenario_comparison.csv`
- `dataset_manifest.json`
- `validation_report.json`
- `used_configuration.yaml`

The full dataset MUST NOT be held in memory.

---

## 4. Data Flow

```text
YAML Configuration
        ↓
Configuration Loader
        ↓
Scenario Selection / Overrides
        ↓
Simulation Context / Controlled RNG
        ↓
Initial Aggregate State
        +
Initial Patient Population
        ↓
Aggregate Flow Engine
        ↓
Raw Constrained Flows
        ↓
Integer Flow Allocator
        ↓
Integer Patient Quotas
        ↓
Patient Event Generator
        ↓
Updated Patient State
        ↓
Reconciliation
        ↓
Runtime Validation
        ↓
Output Buffer
        ↓
Chunked Writer
        ↓
Run/Dataset Validation
        ↓
Release Gate
```

---

## 5. Separation of Responsibilities

| Component | Primary Responsibility |
|---|---|
| Configuration | Parameters and configuration validation |
| Scenario | Approved parameter overrides |
| Simulation Context | Run identity and controlled randomness |
| Aggregate Engine | Model B hospital-flow simulation |
| Integer Allocator | Fractional flow → integer patient quota |
| Patient Generator | Initial and arrival patient creation |
| Event Generator | Which patients move |
| Reconciliation | Aggregate ↔ patient consistency |
| Validation | Correctness and invariant checks |
| Output | Dataset and metadata writing |
| Release Gate | Prevent invalid commercial release |

A component SHOULD NOT silently take over another component's responsibility.

---

## 6. Configuration-Driven Design

Configurable values MUST remain outside the mathematical engine whenever practical.

Scenario changes MUST be expressed as configuration changes rather than duplicated code paths.

---

## 7. Simulation Execution

### Initialization

1. Load configuration.
2. Validate configuration.
3. Select scenario.
4. Apply approved overrides.
5. Revalidate configuration.
6. Create Simulation Context.
7. Initialize controlled RNG.
8. Initialize aggregate stocks.
9. Generate initial patient population.
10. Reconcile initial state.

### Every Timestep

11. Read beginning-of-step aggregate state.
12. Read beginning-of-step patient state.
13. Generate arrivals and arrival patient entities.
14. Calculate requested aggregate flows.
15. Apply source constraints.
16. Apply beginning-of-step capacity constraints.
17. Calculate discharge/death flows.
18. Integerize movement quotas.
19. Select WHICH patients move.
20. Generate events.
21. Update aggregate stocks simultaneously.
22. Update patient states.
23. Reconcile aggregate ↔ patient state.
24. Run runtime validation.
25. Buffer outputs.

### Completion

26. Flush buffers.
27. Generate summary.
28. Run run-level validation.
29. Write validation report and metadata.

---

## 8. Capacity Timing

Phase 1 uses beginning-of-step occupancy for destination-capacity allocation.

Capacity released during timestep `t` becomes available beginning at timestep `t+1`.

Intra-timestep bed reuse MUST NOT be implemented in Phase 1.

---

## 9. Timestep Eligibility

Patients arriving during timestep `t` are not eligible for transfer, discharge, or death until timestep `t+1`.

---

## 10. Scenario Architecture

All scenarios use the same Core Engine.

Scenario logic MUST NOT branch into separate mathematical implementations.

---

## 11. Reproducibility Architecture

Every Batch has one `master_seed`.

Each run derives a deterministic child seed from:

- master seed;
- scenario ID;
- run index.

Uncontrolled randomness is prohibited.

---

## 12. Batch Architecture

Simulation proceeds timestep-by-timestep.

Storage buffering proceeds chunk-by-chunk.

Chunk sizes are output/memory-management settings and MUST NOT change simulation semantics.

Approved planning values:

- patient write buffer: 50,000 rows;
- event write buffer: 100,000 rows;
- compression: ZSTD;
- partition key: `scenario_id`.

The entire dataset MUST NOT be accumulated in RAM.

---

## 13. Validation Architecture

### Runtime Validation
At minimum:

- negative stocks;
- source-stock limits;
- capacity limits;
- NaN/Inf;
- mass balance;
- integer allocation validity;
- aggregate/patient reconciliation.

### Run/Dataset Validation
At minimum:

- patient ID uniqueness;
- event ID uniqueness;
- temporal integrity;
- no post-terminal events;
- one active location;
- scenario coverage;
- Parquet readability;
- record counts;
- Manifest completeness;
- reproducibility fixture.

Tests MUST NOT bypass validation.

---

## 14. Error and Failure Handling

Recognized states:

- configuration error;
- validation failure;
- critical failure;
- `SPEC_CONFLICT`;
- `DECISION_REQUIRED`.

A reconciliation or mass-balance failure is critical for production Batch.

---

## 15. Release Gate

Commercial packaging MUST NOT occur unless:

`validation_status = PASS`

Technical validation produces status:

`VALIDATED`

Commercial release additionally requires project-owner approval and becomes:

`RELEASED`

A failed critical dataset becomes:

`REJECTED`

---

## 16. Architecture Boundaries

Phase 1 MUST NOT require:

- cloud infrastructure;
- microservices;
- external databases;
- public APIs;
- authentication;
- payment infrastructure;
- HIS/EHR/FHIR integration;
- ML infrastructure;
- LLM infrastructure;
- digital twin infrastructure.

---

## 17. Implementation Principle

When multiple implementations satisfy the approved specification, prefer the simplest implementation that preserves correctness, reproducibility, validation, configuration-driven behaviour, aggregate/patient consistency, maintainability, and Batch output.

Do not optimize for hypothetical future requirements.

---

## 18. Architecture Completion Criteria

The architecture is implemented when:

- approved configuration reaches the engine;
- same Core Engine executes Standard-8 and CUSTOM;
- Model B is implemented without duplicated scenario engines;
- initial patient population matches initial stocks;
- raw flows are converted to approved integer quotas;
- patient events follow integer quotas;
- reconciliation is enforced;
- validation is integrated;
- required outputs are generated;
- Batch runs without holding the complete dataset in memory;
- reproducibility requirements are preserved;
- release gate blocks invalid commercial packaging.
