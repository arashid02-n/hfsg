# HFSG — Phase 1 Final Release Verification and Closeout

**Date:** 5 September 2026
**Status:** PHASE 1 — RELEASED / COMPLETE

---

## 1. Project Owner Decision

Recorded per Project Owner instruction of 5 September 2026:

- **Phase 1 MVP:** APPROVED / COMPLETE
- **Validated production scale:** 100,000 synthetic patients
- **Future scale qualification:** >= 1,000,000 synthetic patients — DEFERRED to a future Scale Qualification milestone when adequate hardware/storage/cloud infrastructure is available
- **Commercial dataset:** `HFSG-DS-STD8-2026-20260905-120702`
- **Commercial release:** RELEASED, subject to all final validation conditions being PASS

The >= 1M deferral is NOT a failure of Phase 1. PRODUCT.md §12 success criterion 6 ("complete a 100,000-patient dry run") is satisfied and exceeded by the production batch.

- Project Owner: Mohammad Nazari
- Approval Date: 5 September 2026

## 2. Release Status Final Validation

**PHASE 1 — RELEASED / COMPLETE**

- [x] S1 PASS
- [x] S2 PASS
- [x] S3 PASS
- [x] S4 PASS
- [x] S5 PASS
- [x] S6 PASS
- [x] S7 PASS
- [x] S8 PASS
- [x] CUSTOM PASS
- [x] Aggregate mass balance PASS (max_abs_mbe = 0.0, violations = 0)
- [x] Aggregate-to-patient reconciliation PASS (0 violations)
- [x] Realized integer flow == patient event count (0 quota mismatches)
- [x] Operational aggregate stock == patient population count (0 replay violations)
- [x] Population identity PASS (initial population 115 per run, entry_type INITIAL)
- [x] No unresolved CRITICAL (0 critical failures)
- [x] No unresolved SPEC_CONFLICT (0)
- [x] No unresolved DECISION_REQUIRED (0)
- [x] Deterministic seed reproducibility PASS (9-run sample replayed, 0 failures; child seeds 81/81 re-derive)
- [x] Configuration hash PASS
- [x] Manifest consistency PASS
- [x] Dataset read-back PASS

## 3. Dataset Deliverable

- Dataset ID: `HFSG-DS-STD8-2026-20260905-120702`
- Location: `data/output/step9`
- Production scale: 100,000 (recorded target); **109,119 patients actually written**
- Scenario pack: `Standard-8+CUSTOM`
- Record counts from actual written files (scanned, not inferred):
  - patients: 109,119 (81 part files)
  - patient_events: 316,010 (81 part files)
  - aggregate_timeseries: 58,320 (81 part files)
  - simulation_summary.parquet: 81 rows
- Scenario coverage: S1, S2, S3, S4, S5, S6, S7, S8, CUSTOM — 9 runs each, 81 runs total
- Partitioning: `scenario_id` (9 partitions per dataset; part-0000..part-0008 per scenario)
- Compression: ZSTD (verified in all row groups)
- Master seed: 20260805
- Configuration hash: `f5e1bc49e1bb43a8e10e0a2b9f135501eb07598567728b2c429a403b7673d8cd`
- Configuration hash matches re-hash of `used_configuration.yaml`: PASS
- Engine version: 0.6.0; Dataset version: 1.0; License: `HFSG-EULA-1.0`

## 4. Reproductibility

- Replayed `run_index 0` of every scenario (9 runs) under the same master seed and preserved configuration:
  - checked_runs = 9, failures = 0
- Independent re-derivation of `child_seed(master_seed, scenario_id, run_index)` for all 81 runs: 81/81 match the recorded seeds.
- The written data is reproducible from the recorded configuration and seeds.

## 5. Scale Qualification Note

- Approved Phase 1 target: 100,000 patient records — APPROVED (achieved 109,119).
- MODEL.md §26 commercial target of >= 1,000,000 patient records — DEFERRED to a future Scale Qualification milestone requiring adequate hardware/storage/cloud infrastructure.
- Deviation is recorded as an explicit Project Owner decision in `dataset_manifest.json` (`scale_qualification`, `commercial_release`, `production_target_notes`) and below.

## 6. Release Artifacts

The release package is `data/output/step9` and identifies:

- Dataset ID: `HFSG-DS-STD8-2026-20260905-120702`
- Production scale: 109,119 patients (target 100,000 APPROVED)
- Scenario coverage: Standard-8 + CUSTOM
- Output directory: `data/output/step9`
- Record counts: patients 109,119; events 316,010; aggregate rows 58,320
- Validation status: VALIDATED (final) / RELEASED
- Configuration hash: `f5e1bc49e1bb43a8e10e0a2b9f135501eb07598567728b2c429a403b7673d8cd`
- Dataset manifest: `dataset_manifest.json`
- Used configuration: `used_configuration.yaml`
- Validation report: `validation_report.json`
- Commercial release status: RELEASED

---

No new application features were introduced during closeout. Phase 1 is complete; no Phase 2 work has started.