# HFSG — Step 7 Execution Instruction

**Phase:** Phase 1 MVP  
**Step:** 7 of 9  
**Title:** Aggregate ↔ Patient Reconciliation  
**Status:** APPROVED TO EXECUTE  
**Basis:** HFSG FROZEN v1.0 + Model Clarification v1.0.1

## Objective
Complete end-to-end reconciliation between the integer patient/event layer and the operational aggregate state.

Step 7 is complete only when a full 720-hour S1 run finishes with zero reconciliation failure and all required tests pass.

## Authoritative flow semantics
HFSG MUST distinguish:

```text
requested_raw_flow
        ↓
constrained_raw_flow
        ↓
realized_integer_flow
```

- `requested_raw_flow`: continuous flow requested by Model B.
- `constrained_raw_flow`: continuous flow after source/capacity constraints.
- `realized_integer_flow`: integer quota from the approved Largest Remainder + seeded deterministic tie-break allocator.

## Operational authority
`realized_integer_flow` is authoritative for BOTH:
1. patient-event generation;
2. operational aggregate stock updates.

Required:
```text
PatientEventCount(flow,t) = realized_integer_flow(flow,t)
PatientCount(unit,t) = OperationalAggregateStock(unit,t)
```

Reconciliation is a validation mechanism, not a post-hoc repair mechanism.

## Arrival rule
```text
arrival_demand = Poisson-generated demand
available_ED_capacity = max(0, K_ED - E_begin)
admitted_arrivals = min(arrival_demand, available_ED_capacity)
unmet_arrival_demand = arrival_demand - admitted_arrivals
```

Only `admitted_arrivals` enter patient generation, ARRIVAL events and mass balance.

## Stock update rule
All operational stock updates MUST use realized integer flows.

Example:
```text
E_next =
E_begin
+ admitted_arrivals
- realized_ED_to_specialty
- realized_ED_to_general
- realized_ED_to_ICU
- realized_ED_to_home
```

The same principle applies to C, G, I, H and M.

## Diagnostics
For every flow and timestep preserve:
```text
requested_raw_flow
constrained_raw_flow
realized_integer_flow
integerization_difference
```

where:
```text
integerization_difference =
realized_integer_flow - constrained_raw_flow
```

## Required reconciliation
For every timestep:
```text
active_patient_count(ED,t) == E(t)
active_patient_count(Specialty,t) == C(t)
active_patient_count(General,t) == G(t)
active_patient_count(ICU,t) == I(t)
```

For every movement:
```text
event_count(flow,t) == realized_integer_flow(flow,t)
```

Terminal:
```text
count(discharged up to t) == H(t)
count(dead up to t) == M(t)
```

Population identity:
```text
active + discharged + dead
=
initial_patients + cumulative_admitted_arrivals
```

Mass balance:
```text
E + C + G + I + H + M
=
N_initial + cumulative_admitted_arrivals
```

Acceptance:
```text
abs(MBE) < 1e-6
```

## Frozen timestep rules
- arrivals at `t` become movement-eligible at `t+1`;
- capacity uses beginning-of-step occupancy;
- released capacity becomes available at `t+1`;
- no intra-timestep movement;
- no intra-timestep bed reuse.

## Failure policy
Stop the affected run on:
- aggregate/patient mismatch;
- event count != realized quota;
- mass-balance failure;
- negative stock;
- unauthorized capacity violation;
- impossible patient state;
- post-terminal event;
- duplicate IDs.

DO NOT patch counts, round stocks after the fact, insert correction events, alter realized quotas, or suppress failures.

## Required tests
Add/retain tests for:
1. raw → constrained → realized chain;
2. Largest Remainder allocation;
3. seeded tie-break reproducibility;
4. source-stock preservation;
5. capacity preservation;
6. beginning-of-step capacity timing;
7. `t+1` eligibility;
8. event count = realized quota;
9. active patient count = aggregate stock;
10. H/M terminal reconciliation;
11. population identity;
12. admitted-arrival mass balance;
13. no post-hoc correction.

Required regression test:
`test_s1_reconciliation_720h`

## Step 7 acceptance gate
PASS only if:
- all automated tests pass;
- `test_s1_reconciliation_720h` passes;
- manual S1 completes 720/720 hours;
- reconciliation failures = 0;
- event/quota mismatches = 0;
- mass balance PASS for all 720 hours;
- seed reproducibility PASS;
- no CRITICAL failure;
- no unresolved Step-7 `SPEC_CONFLICT`;
- no unresolved Step-7 `DECISION_REQUIRED`.

## Required engineer report
Report:
1. files changed;
2. tests added/changed;
3. total automated test count;
4. PASS/FAIL;
5. S1 720/720 status;
6. maximum absolute MBE;
7. reconciliation failure count;
8. event/quota mismatch count;
9. reproducibility result;
10. DECISION_REQUIRED/SPEC_CONFLICT status;
11. commit hash;
12. confirmation pushed to `origin/main`.

Do NOT begin Step 8 until Step 7 is accepted.
