# HFSG — Product Specification

**Product:** Hospital Flow Scenario Generator  
**Product Family:** HFSG  
**Current Release:** MVP 1.0  
**Document Status:** FROZEN v1.0  
**Frozen Date:** 2026-08-18  
**Primary Data Label:** `simulated_patient_event_data`

---

## 1. Product Purpose

HFSG is a lightweight synthetic hospital operational data product.

It generates reproducible synthetic patient-flow datasets representing movement through:

- Emergency Department (ED)
- Specialty Ward
- General Medical Ward
- Intensive Care Unit (ICU)
- Discharge
- Death

The MVP combines an aggregate hospital-flow model with a Patient Generator and Patient Event Generator.

The purpose of Phase 1 is to build the smallest technically credible and commercially presentable product that can be demonstrated to potential customers and used to test market demand.

---

## 2. Product Principle

HFSG is **not** a digital twin and does not claim to reproduce a real hospital.

It generates synthetic operational data under explicitly defined model assumptions.

All commercial datasets MUST be labelled:

`simulated_patient_event_data`

---

## 3. Product Family

The same HFSG Core Engine supports three commercial editions.

### 3.1 HFSG Demo Edition

**Product ID:** `HFSG-DEMO`

Purpose: demonstrate HFSG functionality to prospective customers.

Required capabilities:

- run predefined scenarios;
- run one customer-defined scenario using only approved configurable parameters and ranges;
- generate a small synthetic patient dataset;
- show ED/Ward/ICU operational charts;
- show summary KPIs;
- export sample data.

Demo target:

`approximately 2,000–10,000 synthetic patients`

The Demo is not the large-scale production environment.

### 3.2 HFSG Dataset Edition

**Product ID:** `HFSG-DS`

Purpose: produce a versioned synthetic hospital-flow data package that can be supplied as a standalone data product.

Target production volume:

`>= 1,000,000 patient records`

Patient event volume MUST be calculated from the generated data and MUST NOT be hard-coded.

Primary outputs:

- `patients.parquet`
- `patient_events.parquet`
- `aggregate_timeseries.parquet`
- `simulation_summary.parquet`
- `scenario_comparison.csv`
- `dataset_manifest.json`
- `validation_report.json`
- `used_configuration.yaml`

Each commercial dataset MUST receive a unique Dataset ID.

Official Dataset ID pattern:

`HFSG-[PRODUCT]-[SCENARIO_PACK]-[YEAR]-[SERIAL]`

Example:

`HFSG-DS-STD8-2026-0001`

Dataset metadata MUST include at least:

- Product ID
- Dataset ID
- Dataset Version
- Engine Version
- Scenario Pack
- Patient Record Count
- Patient Event Count
- Generation Timestamp
- Data Type
- Configuration Hash
- Validation Status
- License ID

A dataset becomes technically eligible for release only when:

`validation_status = PASS`

Commercial `RELEASED` status additionally requires explicit release approval by the project owner.

### 3.3 HFSG Generator Edition

**Product ID:** `HFSG-GEN`

Purpose: allow an authorized user to generate new HFSG datasets using the same approved model.

Required capabilities:

- load versioned configuration;
- select scenario;
- run Standard-8 scenarios;
- run a customer-defined scenario;
- generate patient-level records;
- generate patient-event records;
- run Batch generation;
- write partitioned Parquet;
- generate Manifest;
- generate Validation Report;
- support reproducible generation using controlled random seeds.

Generator Edition MUST NOT permit users to modify protected model equations, validation invariants, or unsupported patient-routing logic through the user interface.

---

## 4. Shared Core

The three products MUST NOT be implemented as independent modelling systems.

They MUST use one common HFSG Core Engine.

Conceptually:

```text
Scenario Configuration
        ↓
Aggregate Flow Engine
        ↓
Integer Flow Allocator
        ↓
Patient State / Patient Generator
        ↓
Patient Event Generator
        ↓
Aggregate ↔ Patient Reconciliation
        ↓
Validation
        ↓
Parquet / Product Outputs
        ↓
Product-specific Interface
```

Commercial editions may expose different interfaces, limits, and packaging, but they MUST share the same approved model implementation, scenario logic, integerization logic, reconciliation rules, and validation rules.

The model logic MUST NOT be duplicated separately for Demo, Dataset, or Generator editions.

---

## 5. MVP Scope

Phase 1 MUST implement:

1. aggregate ED/Ward/ICU flow simulation;
2. synthetic patient generation, including approved initial patient population and new arrivals;
3. patient event generation;
4. integer allocation of aggregate flows to patient-event quotas;
5. eight predefined operational scenarios;
6. one configurable customer scenario;
7. patient-to-aggregate reconciliation;
8. reproducible random generation;
9. small Demo generation;
10. Batch dataset generation;
11. partitioned Parquet output;
12. Dataset ID and version metadata;
13. automated validation;
14. scenario comparison;
15. rule-based operational summary.

---

## 6. Standard Scenario Pack

The MVP Scenario Pack is:

`Standard-8`

It contains:

- `S1` — Normal Operation
- `S2` — Busy Week
- `S3` — Crisis Mode
- `S4` — ICU Capacity Loss
- `S5` — Bed Block
- `S6` — Compound Stress
- `S7` — Emergency Wave
- `S8` — Recovery Strategy

The product MUST also support:

`CUSTOM`

Customer Scenario parameters MUST remain configurable.

Scenario definitions MUST come from configuration and MUST NOT be silently hard-coded into the simulation engine.

---

## 7. MVP Data Products

### Patient Table

One record per synthetic patient entity, including approved initial-state patients and newly arriving patients.

Primary format: `Parquet`

### Patient Event Table

One record per synthetic patient event.

Required event types:

- `ARRIVAL`
- `TRANSFER`
- `DISCHARGE`
- `DEATH`

### Aggregate Time Series

Hourly system-level data describing:

- ED census
- Specialty census
- General Ward census
- ICU census
- arrivals
- transfers
- discharges
- deaths
- capacity utilization
- unmet demand

### Simulation Summary

One summary record per simulation run.

---

## 8. Batch Target

Default commercial Batch target:

`>= 1,000,000 patient records`

A Standard-8 commercial Batch is complete only when BOTH:

1. `actual_patient_count >= target_patient_records`; and
2. required Standard-8 scenario coverage is complete.

Current planning configuration:

- Standard scenarios: 8
- planned runs per scenario: 120
- initial planned runs: 960
- standard simulation horizon: 30 days
- patient write chunk: 50,000 rows
- event write chunk: 100,000 rows
- Parquet compression: ZSTD
- partition key: `scenario_id`

These are configurable operational settings, not scientific constants.

The Batch process MUST NOT keep the complete dataset in memory.

---

## 9. Intended Uses

HFSG MVP is intended for:

- software testing;
- non-clinical software development and quality assurance;
- data-pipeline testing;
- dashboard development;
- research prototyping;
- education;
- demonstrations;
- scenario experimentation;
- early commercial pilots.

---

## 10. Explicitly Out of Scope

Phase 1 MUST NOT implement or claim:

- real patient data;
- re-identification of real patients;
- clinically validated synthetic data;
- clinical prediction;
- clinical decision support;
- diagnosis generation;
- ICD coding;
- medication data;
- laboratory data;
- vital signs;
- clinical notes;
- digital twin functionality;
- HIS/EHR/FHIR integration;
- public API;
- authentication;
- payment system;
- multi-user administration.

Any such feature requires a future approved product version.

---

## 11. Commercial Release Rule

A dataset may be packaged as an HFSG commercial data product only when:

- required files exist;
- Dataset ID is assigned;
- version is assigned;
- configuration is preserved;
- random seed policy is recorded;
- patient/event reconciliation passes;
- mass balance passes;
- uniqueness tests pass;
- temporal consistency passes;
- scenario coverage passes;
- Parquet files are readable;
- `validation_status = PASS`.

Release states are:

- `DEVELOPMENT`
- `VALIDATED`
- `RELEASED`
- `REJECTED`

`VALIDATED` does not automatically mean `RELEASED`.

Commercial release requires explicit project-owner approval.

---

## 12. Product Success Criteria for Phase 1

Phase 1 is successful when the system can:

1. run the Demo;
2. generate valid patient journeys;
3. reconcile patient events with aggregate hospital flows;
4. run Standard-8;
5. execute a customer scenario;
6. complete a 100,000-patient dry run;
7. complete a `>=1,000,000` patient Batch;
8. generate versioned Parquet packages;
9. generate Manifest and Validation Report automatically;
10. package the output as an identifiable HFSG Data Product;
11. provide at least one commercially presentable Demo package and one versioned Dataset package suitable for market testing with external users.

---

## 13. Product Boundary

The scientific source provides the conceptual compartmental hospital-flow foundation.

HFSG adds engineering layers required for synthetic data generation, including:

- balanced production flows;
- stochastic arrivals;
- explicit capacity constraints;
- Integer Flow Allocator;
- Initial Patient Population generation;
- Patient Generator;
- Patient Event Generator;
- scenario framework;
- Batch generation;
- Parquet storage;
- validation;
- product versioning.

These extensions MUST NOT be represented as equations or findings directly published in the source article.

---

## 14. Change Control

During MVP development, OpenCode and developers MUST NOT independently expand product scope.

New features MUST be placed in the backlog unless explicitly approved.

In particular, do not add:

- machine learning;
- LLM functionality;
- digital twin functionality;
- clinical variables;
- new hospital departments;
- database infrastructure;
- APIs;
- cloud architecture;

unless the project owner explicitly changes the specification.

`PRODUCT.md` defines WHAT is being built.

`MODEL.md` defines HOW the simulation model must behave.
