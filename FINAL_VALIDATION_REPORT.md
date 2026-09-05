# HFSG — Phase 1 Final Validation Report

**Dataset ID:** `HFSG-DS-STD8-2026-20260905-120702`
**Release state:** PHASE 1 — RELEASED / COMPLETE
**Date:** 5 September 2026

> **Phase 1 data status:** These are SYNTHETIC, SCENARIO-DRIVEN simulated data. They MUST NOT be represented or used as clinically validated, real-world-equivalent, or patient-identifiable clinical data.

## Record Counts (from actual written files)

- Actual generated patient records: **109,119**
- Actual patient event records: **316,010**
- Aggregate timeseries records: **58,320**
- Simulation summary runs: **81**
- Target (approved Phase 1 scale): **approximately 100,000 synthetic patients**

## Scenario Coverage

Standard-8 + CUSTOM, 9 runs per scenario (81 runs total). Partitioned by `scenario_id`.
Coverage: S1, S2, S3, S4, S5, S6, S7, S8, CUSTOM — complete, 0 missing.

## Per-Scenario Validation

- S1 (Normal Operation) — **PASS**
- S2 (Busy Week) — **PASS**
- S3 (Crisis Mode) — **PASS**
- S4 (ICU Capacity Loss) — **PASS**
- S5 (Bed Block) — **PASS**
- S6 (Compound Stress) — **PASS**
- S7 (Emergency Wave) — **PASS**
- S8 (Recovery Strategy) — **PASS**
- CUSTOM (Customer Scenario) — **PASS**

All scenarios: 0 reconciliation issues, 0 event/quota mismatches, max_abs_mbe = 0.0, 0 CRITICAL failures.

## Core Validation

- Mass Balance — **PASS** (max_abs_mbe = 0.0, 0 violations over all 81 runs)
- Aggregate-Patient Reconciliation — **PASS** (0 replay violations)
- Event-Quota Reconciliation — **PASS** (0 quota mismatches)
- Capacity / Source invariants — **PASS** (0 violations)
- Uniqueness (patient_id, event_id) — **PASS** (0 violations)
- Temporal consistency — **PASS** (0 violations)
- Post-terminal events — **PASS** (0)
- Population Identity — **PASS** (initial population 115 per run, entry_type INITIAL)
- Seed Reproducibility — **PASS** (9-run sample replayed under master_seed 20260805: 0 failures; child seeds 81/81 re-derived correctly)
- Configuration Hash — **PASS** (`f5e1bc49e1bb43a8e10e0a2b9f135501eb07598567728b2c429a403b7673d8cd`, matches re-hash of used_configuration.yaml)
- Manifest Consistency — **PASS** (record counts and configuration hash match actual files)
- Dataset read-back — **PASS** (243 part files + summary read successfully)
- Critical failures: **0**; unresolved DECISION_REQUIRED: **0**; unresolved SPEC_CONFLICT: **0**

## Automated Tests

- `pytest tests/ -q` — **177 passed**
- `compileall src tests` — PASS
- `git diff --check` — clean

## Configuration

- master_seed: 20260805 (seed policy master_seed_to_child_seed)
- Engine version: 0.6.0
- License: HFSG-EULA-1.0
- Storage: Parquet, ZSTD, partition key scenario_id
- Batch ID: HFSG-BATCH-20260905-120523

## Scale Qualification

- Phase 1 validated production scale: **approximately 100,000 synthetic patients**.
- Actual generated patient records in released dataset: **109,119**.
- Future scale-qualification target: **>= 1,000,000 synthetic patients — DEFERRED by Project Owner** to a future milestone requiring adequate hardware/storage/cloud infrastructure.

## Final State

**PHASE 1 — RELEASED / COMPLETE**

Primary evidence: `validation_report.json` (VALIDATED, 0 critical failures) + Project Owner commercial release approval (Mohammad Nazari, 2026-09-05).