# HFSG — Model Specification

**Model:** HFSG Balanced Synthetic Hospital Flow Model  
**Model Version:** 1.0  
**Document Status:** FROZEN v1.0  
**Frozen Date:** 2026-08-18  
**Implementation Status:** Phase 1 MVP Baseline  
**Time Unit:** hour  
**Default Time Step:** 1 hour  
**Default Horizon:** 720 hours  
**Primary Data Label:** `simulated_patient_event_data`

---

## 1. Model Authority

HFSG uses two conceptually separate model layers.

### Model A — Scientific Reference Model

Source: Al-Karkhi & Byatt (2025), *A compartmental model to describe acute medical in-patient flow through a hospital.*

Model A exists for scientific provenance and comparison.

It MUST NOT be used directly as the HFSG production data generator.

The source article describes aggregate hospital flow through compartments and focuses on net changes between compartments rather than individual patient-level event generation.

### Model B — HFSG Production Model

Model B is the balanced engineering model used by the HFSG Core Engine.

It adapts the compartment concept for reproducible synthetic operational data generation.

The production engine MUST implement Model B.

The Patient Generator and Patient Event Generator are HFSG project extensions and MUST NOT be represented as components of the original source article.

---

## 2. Model Boundary

| Symbol | Engine Name | Meaning | Unit |
|---|---|---|---|
| E | `ed_census` | Emergency Department census | patient |
| C | `specialty_census` | Specialty Ward census | patient |
| G | `general_census` | General Medical Ward census | patient |
| I | `icu_census` | ICU census | patient |
| H | `cumulative_discharges` | Cumulative live exits | patient |
| M | `cumulative_deaths` | Cumulative deaths | patient |

All internal patient movements MUST be represented as flows between these states.

---

## 3. Time Convention

Default: `dt = 1 hour`

Default simulation horizon: `720 hours`

All production rates MUST be converted to compatible hourly units before simulation.

Stocks are measured in patients.

Raw model flows may be continuous/fractional before integer patient allocation.

---

## 4. Aggregate Flow Equations

```text
dE/dt = A - T_EC - T_EG - T_EI - T_EH
dC/dt = T_EC - T_CG - T_CI - D_C - M_C
dG/dt = T_EG + T_CG - T_GI - D_G - M_G
dI/dt = T_EI + T_CI + T_GI - D_I - M_I
dH/dt = T_EH + D_C + D_G + D_I
dM/dt = M_C + M_G + M_I
```

These equations are the authoritative production mass-balance equations.

---

## 5. Arrivals

```text
lambda(t) = lambda_0 * [1 + A_d * sin(2*pi*(t - phi)/24)]
```

When daily seasonality is disabled:

```text
lambda(t) = lambda_0
```

Synthetic arrivals:

```text
A_t ~ Poisson(lambda(t) * dt)
```

Current baseline configuration:

- `baseline_rate_per_hour = 1.5`
- `seasonality.enabled = true`
- `amplitude = 0.30`
- `period_hours = 24`
- `phase_shift_hours = 8`

These baseline values are project configuration values and MUST NOT be represented as universally validated hospital parameters.

---

## 6. ED Processing

```text
T_E_requested = aE / (1 + b1*E)
T_E = min(T_E_requested, E)
```

Current configuration:

- mean processing time: 4 hours
- `a = 0.25 / hour`
- `b1 = 0.02 / patient`

The implementation MUST read these values from configuration.

---

## 7. ED Destination Allocation

```text
T_EC = p_C * T_E
T_EG = p_G * T_E
T_EI = p_I * T_E
T_EH = p_H * T_E
```

Mandatory invariant:

```text
p_C + p_G + p_I + p_H = 1
```

Current baseline shares:

- Specialty: `0.30`
- General Ward: `0.45`
- ICU: `0.05`
- Home: `0.20`

The engine MUST reject a configuration where destination shares do not sum to 1 within numerical tolerance.

---

## 8. Inter-Ward Transfers

```text
T_CG_requested = k_CG * C * Q_I
T_CI_requested = k_CI * C * Q_I
T_GI_requested = k_GI * G
```

ICU pressure auxiliary:

```text
Q_I = 1 + zeta*I / (1 + epsilon*I)
```

For the current MVP baseline:

`Q_I = 1`

unless an explicitly approved configuration enables the ICU-pressure function.

Actual transfers MUST be constrained by:

1. source stock;
2. destination capacity;
3. ICU allocation priority.

Current ICU priority:

1. ED → ICU
2. Specialty → ICU
3. General Ward → ICU

---

## 9. Discharge Flows

```text
D_C = d_C * C
D_G = d_G * G
D_I = d_I * I
```

Rates MUST be loaded from configuration.

---

## 10. Death Flows

```text
M_C = m_C * C
M_G = m_G * G
M_I = m_I * I
```

Rates MUST be loaded from configuration.

Mortality parameters in the production model are operational synthetic-data parameters and MUST retain provenance metadata.

---

## 11. Capacity Constraints

For destination `j`:

```text
AvailableCapacity_j = max(0, K_j - X_j)
```

### Phase 1 Capacity Timing Rule

Destination capacity is evaluated using **beginning-of-step occupancy**.

Capacity released by discharge, death, or transfer during timestep `t` becomes available for allocation beginning at timestep `t+1`.

Phase 1 MUST NOT implement intra-timestep bed reuse.

If requested transfer exceeds available capacity:

- excess demand remains in the source stock;
- unmet demand MUST be recorded.

Current baseline capacities:

- ED: `40`
- Specialty: `60`
- General Ward: `100`
- ICU: `20`

These are configurable MVP baseline assumptions.

---

## 12. Initial Conditions

```text
E(0) = 20
C(0) = 25
G(0) = 60
I(0) = 10
H(0) = 0
M(0) = 0
```

Required:

```text
0 <= X(0) <= K_X
```

Initial conditions MUST be loaded from configuration.

---

## 13. Initial Patient Population

Patient-level simulation MUST NOT begin with an empty patient population when aggregate initial stocks are non-zero.

At initialization, patient entities MUST be created to match exactly:

- `E(0)`
- `C(0)`
- `G(0)`
- `I(0)`

Current baseline therefore requires 115 initial patient entities.

Initial patient entities MUST include:

`entry_type = INITIAL`

If prior-stay duration or another initial-patient attribute is required but not explicitly configured, report:

`DECISION_REQUIRED`

OpenCode MUST NOT invent a prior-stay distribution.

Initial aggregate-to-patient reconciliation MUST PASS before normal timestep execution proceeds.

---

## 14. Integer Flow Allocation

Raw aggregate flows may contain fractional patient values.

Patient-level events require integer patient counts.

Before patient-event generation, constrained aggregate movement flows MUST be converted into integer patient quotas.

### Approved Phase 1 Method

**Largest Remainder Method with seeded deterministic tie-breaking.**

Required behaviour:

1. calculate approved constrained raw flow quantities;
2. take the integer floor of each competing flow;
3. calculate the remaining integer allocation required to preserve the approved total integer outflow;
4. rank fractional remainders from largest to smallest;
5. allocate remaining patients to the largest remainders;
6. use controlled seeded RNG only to break exact ties;
7. preserve source-stock limits;
8. preserve destination-capacity limits;
9. record raw flow and integerized quota.

The allocator MUST NOT modify model parameters, scenario parameters, patient-selection rules, or model structure.

Patient-level reconciliation uses:

```text
PatientEvents(flow,t) = IntegerizedFlow(flow,t)
```

Raw constrained flow MUST remain available for numerical diagnostics.

---

## 15. Aggregate-to-Patient Authority

The Aggregate Flow Engine determines:

**HOW MANY patients move.**

The Patient Event Generator determines:

**WHICH patients move.**

The Patient Event Generator MUST NOT independently increase or decrease approved integer quotas.

Patient-selection rules define ordering/selection only.

---

## 16. Simultaneous Update Rule

For each simulation step:

1. read beginning-of-step aggregate stocks;
2. read beginning-of-step patient state;
3. generate arrivals;
4. create patient entities for new arrivals;
5. calculate requested aggregate flows from beginning-of-step stocks;
6. apply source-stock constraints;
7. apply destination-capacity constraints using beginning-of-step occupancy;
8. calculate discharge/death requested flows;
9. derive integer patient quotas using the Integer Flow Allocator;
10. select WHICH eligible patients satisfy each quota;
11. generate patient events;
12. update ALL aggregate stocks simultaneously;
13. update patient states;
14. reconcile aggregate and patient state;
15. calculate validation metrics;
16. buffer/write output.

Sequential mutation of aggregate stocks while flows are still being calculated is prohibited.

---

## 17. Timestep Eligibility Rule

Patients arriving during timestep `t` MUST NOT be eligible for transfer, discharge, or death during the same timestep.

They become eligible for movement beginning at timestep `t+1`.

Phase 1 MUST NOT introduce intra-timestep patient movement.

---

## 18. Mass Balance

```text
N_total(t) = E + C + G + I + H + M
N_total(t) = N_total(0) + CumulativeArrivals(t)
MBE_t = N_total(t) - N_total(0) - CumulativeArrivals(t)
```

Acceptance:

```text
abs(MBE_t) < 1e-6
```

A mass-balance failure is a Critical validation failure.

---

## 19. Patient Generator

The Patient Generator is an HFSG project extension.

It has two responsibilities:

1. Initial Population Generation
2. Arrival Patient Generation

Each new synthetic arrival creates one synthetic patient entity containing at minimum:

- `simulation_id`
- `scenario_id`
- `patient_id`
- `arrival_datetime`
- `age_group`
- `sex`
- `severity_level`
- `arrival_mode`
- `initial_unit`

Every `patient_id` MUST be unique.

---

## 20. Patient Attribute Distributions

Current MVP configuration includes assumed distributions for:

- age group;
- sex;
- severity;
- arrival mode.

These distributions are `ASSUMPTION`, not `PAPER`.

They MUST remain configurable and MUST NOT be described as empirically validated population distributions.

---

## 21. Patient Event Generator

The Patient Event Generator converts integer aggregate movement quotas into individual synthetic events.

Required event types:

- `ARRIVAL`
- `TRANSFER`
- `DISCHARGE`
- `DEATH`

Every event MUST contain:

- `simulation_id`
- `scenario_id`
- `patient_id`
- `event_id`
- `event_datetime`
- `event_hour`
- `event_type`
- `from_unit`
- `to_unit`

Additional synthetic state fields may be included only when defined in the approved schema.

---

## 22. Patient Selection Rules

### ED non-ICU movement

`FIFO`

### ICU transfer

Priority:

1. highest severity;
2. longest waiting time;
3. seeded-random tie breaker.

### Discharge

For Phase 1, aggregate quota is authoritative.

Minimum-stay eligibility is **not active unless explicit minimum-stay parameters are approved in configuration**.

When minimum-stay parameters are absent, discharge selection uses:

`longest_stay_first`

without introducing an unapproved eligibility threshold.

### Death

Current MVP uses a configurable weighted selection based on:

- severity;
- ICU status;
- elapsed stay.

Current weights:

- severity: `0.50`
- ICU status: `0.30`
- elapsed stay: `0.20`

These weights are project assumptions.

If a valid integer quota cannot be satisfied because patient-state eligibility contradicts the approved model state, report:

`CRITICAL_RECONCILIATION_FAILURE`

Do not silently change the quota.

---

## 23. Aggregate-to-Patient Reconciliation

For every simulation hour and every active unit:

```text
PatientCount(unit,t) = AggregateStock(unit,t)
```

For every patient movement:

```text
PatientEvents(flow,t) = IntegerizedFlow(flow,t)
```

The system MUST also record:

```text
IntegerizationDifference(flow,t)
= IntegerizedFlow(flow,t) - RawConstrainedFlow(flow,t)
```

Any patient/event versus integer-quota reconciliation failure is `CRITICAL` and MUST stop a production Batch.

---

## 24. Patient State Invariants

The engine MUST guarantee:

1. unique `patient_id`;
2. unique `event_id`;
3. event time never moves backward;
4. a patient cannot occupy two units simultaneously;
5. a patient cannot transfer before arrival;
6. no event may occur after death;
7. no event may occur after discharge;
8. all active patients belong to a valid active stock;
9. all patient-level movements correspond to integer aggregate quotas;
10. terminal outcome is unique.

---

## 25. Scenario Model

Required scenario IDs:

`S1 S2 S3 S4 S5 S6 S7 S8 CUSTOM`

Scenario modifications MUST be applied through configuration.

Scenario logic MUST NOT modify the mathematical engine.

A scenario changes approved parameters, not model structure.

---

## 26. Batch Generation

Commercial Dataset target:

`target_patient_records >= 1,000,000`

Current planning values:

- 120 planned runs per Standard-8 scenario;
- approximately 960 initial planned runs;
- patient chunks: `50,000 rows`;
- event chunks: `100,000 rows`;
- storage: Apache Parquet;
- compression: ZSTD;
- partition: `scenario_id`.

Batch completion requires BOTH:

1. target patient volume reached; and
2. required Standard-8 scenario coverage complete.

The full dataset MUST NOT be held in RAM.

---

## 27. Batch Seed Policy

Every Batch MUST define one:

`master_seed`

Each simulation run MUST derive a deterministic child seed from:

- `master_seed`
- `scenario_id`
- `run_index`

The exact deterministic derivation algorithm MUST be stable and versioned by implementation.

The derived child seed MUST be recorded in run metadata.

The same master seed, scenario schedule, configuration, and run index MUST reproduce the same child seed.

Uncontrolled randomness is prohibited.

---

## 28. Reproducibility

Every run MUST record:

- model version;
- configuration version;
- scenario ID;
- simulation ID;
- random seed / child seed;
- generation timestamp.

A fixed configuration and fixed seed MUST reproduce the defined test fixture.

Volatile operational metadata such as generation timestamp MUST be excluded or normalized in reproducibility comparisons unless a fixed test timestamp is configured.

---

## 29. Parameter Provenance

Every model parameter MUST have one provenance class:

- `PAPER`
- `TRANSFORMED`
- `EXPERT`
- `ASSUMPTION`
- `CALIBRATED`

No assumed parameter may be labelled as `PAPER`.

---

## 30. Validation Requirements

Production validation MUST include:

- no negative stocks;
- no flow greater than source stock;
- no unauthorized capacity violation;
- destination shares sum to one;
- no NaN/Inf;
- mass balance PASS;
- valid Integer Flow Allocation;
- unique patient IDs;
- unique event IDs;
- chronological events;
- no post-terminal events;
- one active location per patient;
- aggregate/patient reconciliation PASS;
- seed reproducibility;
- Standard-8 scenario coverage.

---

## 31. Required Outputs

- `patients.parquet`
- `patient_events.parquet`
- `aggregate_timeseries.parquet`
- `simulation_summary.parquet`
- `dataset_manifest.json`
- `validation_report.json`
- `used_configuration.yaml`

---

## 32. Model Decisions Not to Be Invented by OpenCode

If absent or ambiguous, OpenCode MUST NOT invent:

- new clinical variables;
- diagnosis probabilities;
- disease-specific mortality;
- new departments;
- new patient routes;
- new scenario multipliers;
- new capacity rules;
- new ICU priorities;
- clinical severity interpretation;
- new patient attribute distributions;
- new discharge/death selection logic;
- real-hospital calibration parameters;
- any replacement for the approved integerization method;
- any unapproved intra-timestep movement rule.

Flag:

`DECISION_REQUIRED`

---

## 33. Scientific Provenance Warning

The source article provides the scientific foundation for the compartmental hospital-flow concept and its original differential-equation model.

HFSG Model B, stochastic arrivals, explicit capacity controls, integer allocation, patient-level entities, Patient Event Generator, scenario packaging, Batch generation, and commercial Parquet output are HFSG engineering adaptations.

They MUST remain distinguishable in code, documentation, and metadata.

---

## 34. Implementation Authority

Precedence for coding:

1. `MODEL.md` — model behaviour and invariants;
2. approved YAML — parameter values;
3. `PRODUCT.md` — product scope;
4. `ARCHITECTURE.md` — software structure;
5. `OPERATIONS.md` — operational workflow;
6. source article — scientific provenance;
7. supporting PDFs/XLSX — explanatory material.

`AGENTS.md` controls agent behaviour but MUST NOT override model behaviour in `MODEL.md`.

If authoritative sources conflict, report:

`SPEC_CONFLICT`
