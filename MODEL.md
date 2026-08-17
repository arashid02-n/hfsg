MODEL.md

HFSG — Model Specification

Model: HFSG Balanced Synthetic Hospital Flow Model
Model Version: 1.0
Implementation Status: MVP Baseline
Time Unit: hour
Default Time Step: 1 hour
Default Horizon: 720 hours
Primary Data Label: simulated_patient_event_data


---

1. Model Authority

HFSG uses two conceptually separate model layers.

Model A — Scientific Reference Model

Source:

Al-Karkhi & Byatt (2025),
A compartmental model to describe acute medical in-patient flow through a hospital.

Model A exists for scientific provenance and comparison.

It MUST NOT be used directly as the HFSG production data generator.

The source article describes aggregate hospital flow through compartments and focuses on net changes between compartments rather than individual patient-level event generation.

Model B — HFSG Production Model

Model B is the balanced engineering model used by the HFSG Core Engine.

It adapts the compartment concept for reproducible synthetic operational data generation.

The production engine MUST implement Model B.

The Patient Generator and Patient Event Generator are HFSG project extensions and MUST NOT be represented as components of the original source article.


---

2. Model Boundary

The aggregate system contains six stocks:

Symbol Engine Name Meaning Unit

E ed_census Emergency Department census patient
C specialty_census Specialty Ward census patient
G general_census General Medical Ward census patient
I icu_census ICU census patient
H cumulative_discharges Cumulative live exits patient
M cumulative_deaths Cumulative deaths patient


All internal patient movements MUST be represented as flows between these states.


---

3. Time Convention

Default:

dt = 1 hour

Default simulation horizon:

720 hours

All production rates MUST be converted to compatible hourly units before simulation.

Stocks are measured in patients.

Flows represent patients per simulation time step.


---

4. Aggregate Flow Equations

Production stock equations:

dE/dt = A - T_EC - T_EG - T_EI - T_EH

dC/dt = T_EC - T_CG - T_CI - D_C - M_C

dG/dt = T_EG + T_CG - T_GI - D_G - M_G

dI/dt = T_EI + T_CI + T_GI - D_I - M_I

dH/dt = T_EH + D_C + D_G + D_I

dM/dt = M_C + M_G + M_I

These equations are the authoritative production mass-balance equations.


---

5. Arrivals

Arrival intensity:

λ(t) = λ₀ [1 + A_d sin(2π(t - φ) / 24)]

When daily seasonality is disabled:

λ(t) = λ₀

Synthetic arrivals:

A_t ~ Poisson(λ(t) Δt)

Current baseline configuration:

baseline_rate_per_hour = 1.5

seasonality.enabled = true

amplitude = 0.30

period_hours = 24

phase_shift_hours = 8


These baseline values are project configuration values and MUST NOT be represented as universally validated hospital parameters.


---

6. ED Processing

Requested ED processing:

T_E_requested = aE / (1 + b₁E)

Actual ED processing:

T_E = min(T_E_requested, E)

Current configuration:

mean processing time: 4 hours

a = 0.25 / hour

b1 = 0.02 / patient


The implementation MUST read these values from configuration.


---

7. ED Destination Allocation

Processed ED flow is divided into:

T_EC = p_C T_E

T_EG = p_G T_E

T_EI = p_I T_E

T_EH = p_H T_E

Mandatory invariant:

p_C + p_G + p_I + p_H = 1

Current baseline shares:

Specialty: 0.30

General Ward: 0.45

ICU: 0.05

Home: 0.20


The engine MUST reject a configuration where destination shares do not sum to 1 within numerical tolerance.


---

8. Inter-Ward Transfers

Requested transfers:

T_CG_requested = k_CG C Q_I

T_CI_requested = k_CI C Q_I

T_GI_requested = k_GI G

ICU pressure auxiliary:

Q_I = 1 + ζI / (1 + εI)

For the current MVP baseline:

Q_I = 1

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

9. Discharge Flows

D_C = d_C C

D_G = d_G G

D_I = d_I I

Rates MUST be loaded from configuration.


---

10. Death Flows

M_C = m_C C

M_G = m_G G

M_I = m_I I
Rates MUST be loaded from configuration.

Mortality parameters in the production model are operational synthetic-data parameters and MUST retain provenance metadata.


---

11. Capacity Constraints

For destination j:

AvailableCapacity_j = max(0, K_j - X_j)

Actual transfer:

ActualTransfer_ij =
min(RequestedTransfer_ij, AvailableCapacity_j)

If requested transfer exceeds available capacity:

the excess patient demand remains in the source stock;

unmet demand MUST be recorded.


Current baseline capacities:

ED: 40

Specialty: 60

General Ward: 100

ICU: 20


These are configurable MVP baseline assumptions.


---

12. Initial Conditions

Current baseline:

E(0) = 20
C(0) = 25
G(0) = 60
I(0) = 10
H(0) = 0
M(0) = 0

Required:

0 ≤ X(0) ≤ K_X

for each active hospital stock.

Initial conditions MUST be loaded from configuration.


---

13. Simultaneous Update Rule

For each simulation step:

1. read beginning-of-step stocks;


2. calculate arrival demand;


3. calculate all requested internal flows;


4. apply source-stock constraints;


5. apply destination-capacity constraints;


6. calculate discharges;


7. calculate deaths;


8. scale outflows if total outflow exceeds source stock;


9. update ALL stocks simultaneously;


10. calculate validation metrics;


11. pass aggregate quotas to Patient Event Generator;


12. reconcile patient-level state with aggregate state;


13. write output.



Sequential mutation of stocks while flows are still being calculated is prohibited.


---

14. Mass Balance

Define:

N_total(t) = E + C + G + I + H + M

Expected identity:

N_total(t) =
N_total(0) + CumulativeArrivals(t)

Mass-balance error:

MBE_t =
N_total(t) - N_total(0) - CumulativeArrivals(t)

Acceptance:

|MBE_t| < 10^-6

A mass-balance failure is a Critical validation failure.


---

15. Patient Generator

The Patient Generator is an HFSG project extension.

It is NOT part of the source article.

Each synthetic arrival MUST create one synthetic patient entity containing at minimum:

simulation_id

scenario_id

patient_id

arrival_datetime

age_group

sex

severity_level

arrival_mode

initial_unit


Every patient_id MUST be unique.


---

16. Patient Attribute Distributions

Current MVP configuration includes assumed distributions for:

age group;

sex;

severity;

arrival mode.


These distributions are:

ASSUMPTION

not:

PAPER

They MUST therefore remain configurable.

They MUST NOT be described as empirically validated population distributions.


---

17. Patient Event Generator

The Patient Event Generator converts aggregate flow quotas into individual synthetic events.

Required event types:

ARRIVAL

TRANSFER

DISCHARGE

DEATH


Every event MUST contain:

simulation_id

scenario_id

patient_id

event_id

event_datetime

event_hour

event_type

from_unit

to_unit


Additional synthetic state fields may be included only when defined in the approved schema.


---

18. Patient Selection Rules

ED non-ICU movement

Use:

FIFO

ICU transfer

Priority:

1. highest severity;


2. longest waiting time;


3. seeded-random tie breaker.



Discharge

Patient must first satisfy minimum-stay eligibility.

Among eligible patients:

longest_stay_first

Death

Current MVP uses a configurable weighted selection based on:

severity;

ICU status;

elapsed stay.


Current weights:

severity: 0.50

ICU status: 0.30

elapsed stay: 0.20


These weights are project assumptions.

They MUST NOT be described as findings from the source article.


---

19. Aggregate-to-Patient Reconciliation

For every simulation hour and every active unit:

PatientCount(unit,t) = AggregateStock(unit,t)

For every flow:

PatientEvents(flow,t) = AggregateFlow(flow,t)

Examples:

Count(ED → ICU,t) = T_EI(t)

Count(ICU → Discharge,t) = D_I(t)

Any reconciliation failure is:

CRITICAL

and MUST stop a production Batch.


---

20. Patient State Invariants

The engine MUST guarantee:

1. one patient has one unique patient_id;


2. one event has one unique event_id;


3. event time never moves backward;


4. a patient cannot occupy two units simultaneously;
5. a patient cannot transfer before arrival;


6. no event may occur after death;


7. no event may occur after discharge;


8. all active patients must belong to a valid active stock;


9. all patient-level movements must correspond to aggregate flow;


10. terminal outcome is unique.




---

21. Scenario Model

Required scenario IDs:

S1

S2

S3

S4

S5

S6

S7

S8

CUSTOM


Scenario modifications MUST be applied through configuration.

Scenario logic MUST NOT modify the mathematical engine itself.

A scenario changes approved parameters, not model structure.


---

22. Batch Generation

Commercial Dataset target:

target_patient_records >= 1,000,000

Current plan:

120 planned runs per Standard-8 scenario;

approximately 960 initial planned runs;

stop after target patient volume is reached.


Patient chunks:

50,000 rows

Event chunks:

100,000 rows

Storage:

Apache Parquet

Compression:

ZSTD

Partition:

scenario_id

The full dataset MUST NOT be held in RAM.


---

23. Reproducibility

Every run MUST record:

model version;

configuration version;

scenario ID;

simulation ID;

random seed;

generation timestamp.


A fixed configuration and fixed seed MUST reproduce the defined deterministic/stochastic test fixture.


---

24. Parameter Provenance

Every model parameter MUST have one provenance class:

PAPER

TRANSFORMED

EXPERT

ASSUMPTION

CALIBRATED


CALIBRATED means estimated from external real-world data.

No assumed parameter may be labelled as PAPER.


---

25. Validation Requirements

Production validation MUST include:

no negative stocks;

no flow greater than source stock;

no unauthorized capacity violation;

destination shares sum to one;

no NaN/Inf;

mass balance PASS;

unique patient IDs;

unique event IDs;

chronological events;

no post-terminal events;

one active location per patient;

aggregate/patient reconciliation PASS;

seed reproducibility;

scenario coverage.



---

26. Required Outputs

Patient level

patients.parquet

Event level

patient_events.parquet

Aggregate level

aggregate_timeseries.parquet

Run level

simulation_summary.parquet

Product metadata

dataset_manifest.json

validation_report.json

used_configuration.yaml



---

27. Model Decisions Not to Be Invented by OpenCode

If any of the following are absent or ambiguous in approved configuration, OpenCode MUST NOT invent a value:

new clinical variables;

diagnosis probabilities;

disease-specific mortality;

new departments;

new patient routes;

new scenario multipliers;

new capacity rules;

new ICU allocation priorities;

clinical severity interpretation;

new patient attribute distributions;

new discharge/death selection logic;

real-hospital calibration parameters.


The implementation must stop, flag the issue as:

DECISION_REQUIRED

and request a project decision.


---

28. Scientific Provenance Warning

The source article provides the scientific foundation for the compartmental hospital-flow concept and its original differential-equation model.

HFSG Model B, stochastic arrival generation, explicit capacity controls, patient-level entities, Patient Event Generator, scenario packaging, Batch generation and commercial Parquet output are engineering adaptations of this project.

They MUST remain distinguishable in code, documentation and metadata.


---

29. Implementation Authority

For coding purposes, precedence is:

1. MODEL.md — model behaviour and invariants;


2. approved YAML configuration — parameter values;


3. PRODUCT.md — product scope;


4. source article — scientific provenance;


5. supporting PDFs/XLSX — explanatory material.



If these sources conflict, OpenCode MUST NOT silently choose one.

It must report:

SPEC_CONFLICT

and wait for an explicit decision.
