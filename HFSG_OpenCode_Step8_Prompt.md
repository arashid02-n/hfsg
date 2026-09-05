# OpenCode Execution Prompt — HFSG Step 8
Execute Step 8 ONLY: **Standard-8 + CUSTOM Scenario Integration and Output Pipeline**.

Prerequisite: Step 7 APPROVED/CLOSED at `6b5ba6e`.

Read repository FROZEN specifications, Model Clarification v1.0.1, `HFSG_Step8_Execution_Instruction.md`, and `HFSG_Step8_Acceptance_Checklist.md`.

Use the SAME Core Engine for S1–S8 and CUSTOM. Implement approved configuration overrides exactly. Verify S7 x2 arrivals lasts exactly 48 hours. Prevent scenario/base-config mutation.

Preserve Step-7 semantics:
`requested_raw_flow -> constrained_raw_flow -> realized_integer_flow`.
Realized integer flow drives patient events and operational aggregate stocks. Reconciliation remains validation, not repair.

Implement:
`patients.parquet`, `patient_events.parquet`, `aggregate_timeseries.parquet`, `simulation_summary.parquet`, `scenario_comparison.csv`, `dataset_manifest.json`, `validation_report.json`, `used_configuration.yaml`.

Use ZSTD, scenario_id partitioning, chunked writing, actual output counts and exact used-configuration hashing. Do not keep production-scale full data in RAM.

Add/execute tests required by the Step-8 instruction. Existing `test_s1_reconciliation_720h` MUST remain PASS. Run S1–S8 and at least one approved CUSTOM validation run.

Do NOT start Step 9 or the >=1,000,000-patient production Batch.

At completion provide the exact 20-item engineer report defined in the Step-8 Execution Instruction, then STOP for approval.
