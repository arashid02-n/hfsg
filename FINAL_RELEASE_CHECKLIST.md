# HFSG — Final Release Checklist

**Phase:** Phase 1 (MVP 1.0) — Final Acceptance preparation
**Date:** 2026-09-05
**Release decision authority:** Project Owner (Mohammad Nazari); HFSG-PH1-DEV-001

> **Phase 1 data status:** These are SYNTHETIC, SCENARIO-DRIVEN simulated data. They MUST NOT be represented or used as clinically validated, real-world-equivalent, or patient-identifiable clinical data.

## Actual release values (from the written dataset, not fabricated)

| Item | Value |
|---|---|
| **Dataset ID** | `HFSG-DS-STD8-2026-20260905-120702` |
| **Dataset version** | 1.0 |
| **Engine version** | 0.6.0 |
| **Model** | Model B (frozen spec set, MVP 1.0, frozen 2026-08-18) |
| **Master seed** | `20260805` |
| **Configuration hash** | `f5e1bc49e1bb43a8e10e0a2b9f135501eb07598567728b2c429a403b7673d8cd` |
| **Patients count** | **109,119** |
| **Events count** | **316,010** |
| **Aggregate record count** | **58,320** (81 runs × 720 hours) |
| **Number of scenarios** | 9 (S1–S8 + CUSTOM) |
| **Number of runs** | 81 (9 runs per scenario) |
| **Scale** | Approved Acceptance Scale: approximately 100,000 synthetic patients (109,119 actually generated) |
| **Validation result** | `VALIDATED` — all checks PASS |
| **Critical failure count** | 0 |
| **License** | `HFSG-EULA-1.0` |
| **Technical Status (Phase-1 MVP)** | `RELEASED / ACCEPTED` |
| **Commercial Distribution / Commercial Use Authorization** | `Subject to a separate Project Owner decision.` |

## Per-scenario status (ALL PASS)

S1 PASS, S2 PASS, S3 PASS, S4 PASS, S5 PASS, S6 PASS, S7 PASS, S8 PASS, CUSTOM PASS.
Mass balance: max_abs_mbe = 0.0; aggregate↔patient reconciliation: 0; event↔quota reconciliation: 0; uniqueness: 0; temporal: 0; capacity/source: 0.

## Complete release-file list

`data/output/step9/`:

- `patients/` (partitioned by `scenario_id`, ZSTD Parquet, 81 part files)
- `patient_events/` (partitioned by `scenario_id`, ZSTD Parquet, 81 part files)
- `aggregate_timeseries/` (partitioned by `scenario_id`, ZSTD Parquet, 81 part files)
- `simulation_summary.parquet`
- `scenario_comparison.csv`
- `dataset_manifest.json`
- `validation_report.json`
- `used_configuration.yaml`
- `batch_checkpoint.json` (checkpoint/resume metadata)

## Verification status

- Dataset read-back: **PASS** (243 part files read successfully)
- Manifest/config hash consistency: **PASS** (`configuration_hash` == re-hash of `used_configuration.yaml`)
- Manifest record counts == written files: **PASS** (109,119 / 316,010)
- Scenario coverage: **PASS** (0 missing)
- Seed reproducibility: **PASS** (9-run replay sample, 0 failures; child seeds 81/81 re-derived)
- Unresolved CRITICAL: **0**; unresolved SPEC_CONFLICT: **0**; unresolved DECISION_REQUIRED: **0**

## Source code status

**Technical Release / Phase-1 MVP:** RELEASED / ACCEPTED

**Commercial Distribution / Commercial Use Authorization:** Subject to a separate Project Owner decision.

- Validated/Audited Core Commit: `08032c3` (last commit affecting Core/Model logic — Step 9: 100k-patient batch generation and validation)
- Final Handover Commit: `7f5a117` (final documentation/closeout/audit commit)
- The difference between the Validated/Audited Core Commit and the Final Handover Commit is **documentation/closeout only**; Core/Model logic was NOT changed between `08032c3` and `7f5a117` (verified: `git diff 08032c3..7f5a117 -- src config scripts tests requirements.txt` is empty).
- Working tree: clean except intentionally untracked derived `data/`
- No new features, variables, model logic, scenarios or capabilities added during closeout

## Tests status

- `python -m pytest tests/ -q` → **177 passed**
- `python -m compileall src tests` → PASS
- `git diff --check` → clean

## Dependencies

- Exact locked versions: `requirements-lock.txt` (numpy 2.5.2, pandas 3.0.5, pyarrow 25.0.1, PyYAML 6.0.3, etc.; Python 3.12.3, Linux)

## Known limitations

1. `>=1,000,000`-patient Scale Qualification is **deferred to Phase 2** per HFSG-PH1-DEV-001 (current hardware: 3.7 GiB RAM, ~1.3 GiB free disk, 2 CPU cores). This is NOT a Phase 1 failure.
2. Data are **synthetic and scenario-driven**; no clinical validity, no real-world equivalence.
3. Mortality is rare in the approved scale: most runs have 0 deaths (DEATH events and `M_*` quota flows exist but are sparse).
4. Phase 1 is single-machine; no Dockerization/containerization, no distributed scale-out (Phase 2 recommendations — see `FINAL_ACCEPTANCE_SUMMARY.md`).
5. Scenario run counts are 9 per scenario (81 total) — sufficient to meet the approved ~100K Acceptance Scale; `planned_runs_per_scenario: 120` remains a Phase 2 planning value.

## Reproduction instructions

See `INSTALLATION_AND_REPRODUCTION.md`: source, Python 3.12 + `requirements-lock.txt`, run tests, run one scenario, Standard-8, CUSTOM, generate/validate a dataset, and reproduce deterministic runs from `master_seed = 20260805` and the preserved `used_configuration.yaml`.