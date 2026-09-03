# HFSG — Model Clarification v1.0.1

**Applies To:** HFSG FROZEN v1.0  
**Scope:** Aggregate ↔ Patient Reconciliation  
**Status:** APPROVED

HFSG distinguishes:
`requested_raw_flow`, `constrained_raw_flow`, and `realized_integer_flow`.

The approved Integer Flow Allocator converts constrained continuous flow into integer patient quota.

For operational simulation state, `realized_integer_flow` is authoritative for BOTH patient-event generation and operational aggregate stock updates.

Therefore:
```text
PatientEventCount(flow,t) = realized_integer_flow(flow,t)
PatientCount(unit,t) = OperationalAggregateStock(unit,t)
```

Fractional flows remain diagnostics/provenance only and MUST NOT maintain a separate operational stock state that diverges from patient counts.

Reconciliation is validation, not repair.

Only `admitted_arrivals` enter the system and participate in aggregate stocks, patient generation, ARRIVAL events and mass balance. `arrival_demand` and `unmet_arrival_demand` remain reporting variables.

This clarification does not add new product scope, clinical functionality or scientific claims.
