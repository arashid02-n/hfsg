# HFSG — Step 8 Execution Instruction
**Phase:** Phase 1 MVP  
**Step:** 8 of 9  
**Title:** Standard-8 + CUSTOM Scenario Integration and Output Pipeline  
**Status:** APPROVED TO EXECUTE  
**Prerequisite:** Step 7 APPROVED/CLOSED, commit `6b5ba6e`  
**Basis:** HFSG FROZEN v1.0 + Model Clarification v1.0.1

## Objective
Integrate and validate Standard-8 plus CUSTOM using the SAME approved Core Engine and implement the approved output pipeline. Step 8 is not the final >=1,000,000-patient production Batch.

## Scope
Implement S1–S8, CUSTOM, configuration-driven overrides, scenario validation, Parquet/CSV/JSON/YAML outputs, scenario comparison, Manifest, Validation Report, used-configuration preservation, partitioning, record-count verification and reproducibility.

Do NOT modify Model B, integerization, reconciliation semantics, patient routes, departments, clinical scope, or start the final production Batch.

## Scenario Pack
- S1 Normal Operation: baseline.
- S2 Busy Week: arrivals +20%.
- S3 Crisis Mode: arrivals +50%.
- S4 ICU Capacity Loss: ICU capacity -20%.
- S5 Bed Block: discharge rates -20%.
- S6 Compound Stress: arrivals +20% and ICU capacity -20%.
- S7 Emergency Wave: arrivals x2 for exactly 48 hours.
- S8 Recovery Strategy: ICU capacity +20% and discharge rates +20%.
- CUSTOM: only approved configurable parameters/ranges.

All overrides MUST come from configuration. No separate scenario-specific model engines and no mutation of the base configuration.

## Preserve Step 7
`requested_raw_flow -> constrained_raw_flow -> realized_integer_flow`

`realized_integer_flow` remains authoritative for patient events AND operational aggregate stock updates. Reconciliation is validation, not repair.

Preserve admitted-arrival rule, initial population, t+1 eligibility, beginning-of-step capacity, no intra-timestep bed reuse, Largest Remainder + seeded tie-break, mass balance and reproducibility.

## Required Outputs
- `patients.parquet`
- `patient_events.parquet`
- `aggregate_timeseries.parquet`
- `simulation_summary.parquet`
- `scenario_comparison.csv`
- `dataset_manifest.json`
- `validation_report.json`
- `used_configuration.yaml`

Parquet: ZSTD. Partition key: `scenario_id`. Patient write threshold: 50,000 rows. Event write threshold: 100,000 rows. Thresholds are storage/memory settings only and MUST NOT change simulation semantics.

## Manifest Minimum
Include Product ID, Dataset ID, Dataset Version, Engine Version, Scenario Pack, actual Patient Record Count, actual Patient Event Count, Generation Timestamp, `data_type=simulated_patient_event_data`, Configuration Hash, Validation Status, License ID.

Step-8 validation artifacts MUST NOT be falsely marked commercial RELEASED.

## Validation Report
Report mass balance, aggregate/patient reconciliation, event/quota reconciliation, uniqueness, temporal consistency, capacity/source invariants, scenario coverage, Parquet readability, actual record counts, reproducibility, CRITICAL failures, DECISION_REQUIRED and SPEC_CONFLICT.

## Critical Scenario Tests
S7 MUST be tested to ensure x2 arrivals applies for exactly 48 hours and baseline resumes afterwards. Scenario execution MUST NOT mutate base config; e.g. S2 followed by S1 with equivalent clean inputs must preserve S1 behaviour.

## Required Automated Coverage
Test all S1–S8 overrides; valid/invalid CUSTOM; scenario isolation; same Core Engine; all Parquet write/read paths; ZSTD; scenario partitioning; actual-count/Manifest reconciliation; configuration hash; used config; Validation Report; scenario comparison; post-serialization uniqueness, temporal consistency and reconciliation; reproducibility; and no regression of `test_s1_reconciliation_720h`.

## Step 8 Acceptance Gate
PASS only if:
- all automated tests PASS;
- S1 720-hour reconciliation regression remains PASS;
- S1–S8 each PASS;
- at least one approved CUSTOM run PASS;
- all eight required outputs are generated/readable;
- Parquet partitioning and ZSTD PASS;
- Manifest actual counts equal written data;
- configuration hash matches exact preserved configuration;
- scenario coverage PASS;
- post-write/read invariants PASS;
- reproducibility PASS;
- zero CRITICAL failures;
- zero unresolved Step-8 DECISION_REQUIRED/SPEC_CONFLICT.

Use a validation-sized dataset sufficient to exercise all scenarios and outputs. Do not use the final >=1M Batch as the Step-8 debugging mechanism.

## Required Completion Report
Report:
1. files changed;
2. tests added/changed;
3. total automated tests/PASS count;
4. S1–S8 individually;
5. CUSTOM result;
6. S1 720h regression;
7. max absolute MBE;
8. reconciliation failures;
9. event/quota mismatches;
10. Step-8 patient count;
11. Step-8 event count;
12. output files/readability;
13. Manifest count cross-check;
14. configuration-hash cross-check;
15. scenario coverage;
16. reproducibility;
17. peak memory if measured;
18. DECISION_REQUIRED/SPEC_CONFLICT;
19. commit hash;
20. origin/main push status.

## Stop Rule
After Step 8 PASS, STOP and request approval for Step 9:
**100k Dry Run -> >=1,000,000-patient Production Batch -> Final Validation / Release Candidate Packaging.**

> **Amendment 2026-09-05 (HFSG-PH1-DEV-001 — Project Owner decision):** the Step 9 Production Batch for Phase 1 was executed at the approved approximately-100,000-patient Acceptance Scale (released dataset `HFSG-DS-STD8-2026-20260905-120702`, 109,119 patient records); the `>=1,000,000`-patient Batch is DEFERRED to Phase 2 as Scale Qualification.
