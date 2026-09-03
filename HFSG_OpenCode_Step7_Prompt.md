# OpenCode Execution Prompt — HFSG Step 7

Execute HFSG Step 7 only.

Read and obey the current repository root specifications plus:
- `HFSG_Step7_Execution_Instruction.md`
- `HFSG_Model_Clarification_v1.0.1.md`

Primary objective:
make the full 720-hour S1 run pass exact aggregate↔patient reconciliation.

Required semantics:
`requested_raw_flow -> constrained_raw_flow -> realized_integer_flow`

`realized_integer_flow` is authoritative for both patient-event generation and operational aggregate stock updates.

Do not keep a separate fractional operational stock that diverges from patient counts.
Do not implement post-hoc reconciliation corrections.

Preserve:
- Largest Remainder + seeded deterministic tie-break;
- initial 115-patient population;
- admitted-arrival ED capacity rule;
- t+1 movement eligibility;
- beginning-of-step capacity;
- no intra-timestep bed reuse;
- all existing validation invariants.

Add `test_s1_reconciliation_720h`.

Do not proceed beyond Step 7.

When finished, report:
- files changed;
- tests added;
- total tests/pass count;
- S1 720-hour result;
- max absolute MBE;
- reconciliation failure count;
- event/quota mismatch count;
- reproducibility result;
- DECISION_REQUIRED/SPEC_CONFLICT status;
- commit hash;
- push status.
