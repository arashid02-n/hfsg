PRODUCT.md

HFSG — Product Specification

Product: Hospital Flow Scenario Generator
Product Family: HFSG
Current Release: MVP 1.0
Status: Pilot / Market Validation
Primary Data Label: simulated_patient_event_data


---

1. Product Purpose

HFSG is a lightweight synthetic hospital operational data product.

It generates reproducible synthetic patient-flow datasets representing movement through:

Emergency Department (ED)

Specialty Ward

General Medical Ward

Intensive Care Unit (ICU)

Discharge

Death


The MVP combines an aggregate hospital-flow model with a Patient Event Generator.

The purpose of Phase 1 is to build the smallest technically credible and commercially presentable product that can be demonstrated to potential customers and used to test market demand.


---

2. Product Principle

HFSG is not a digital twin and does not claim to reproduce a real hospital.

It generates synthetic operational data under explicitly defined model assumptions.

All commercial datasets MUST be labelled:

simulated_patient_event_data


---

3. Product Family

The same HFSG Core Engine supports three commercial products.

3.1 HFSG Demo Edition

Product ID: HFSG-DEMO

Purpose:
Demonstrate HFSG functionality to prospective customers.

Required capabilities:

run predefined scenarios;

run a customer-defined scenario;

generate a small synthetic patient dataset;

show ED/Ward/ICU operational charts;

show summary KPIs;

export sample data.


Demo target:

Approximately 2,000–10,000 synthetic patients.

The Demo is not the large-scale production environment.


---

3.2 HFSG Dataset Edition

Product ID: HFSG-DS

Purpose:
Produce a versioned synthetic hospital-flow data package that can be supplied as a standalone data product.

Target production volume:

>= 1,000,000 patient records

Patient event volume is expected to be larger than the patient table and MUST be reported from the actual generated dataset rather than hard-coded.

Primary outputs:

patients.parquet

patient_events.parquet

aggregate_timeseries.parquet

simulation_summary.parquet

scenario_comparison.csv

dataset_manifest.json

validation_report.json

used_configuration.yaml


Each commercial dataset MUST receive a unique Dataset ID.

Example:

HFSG-DS-STD8-2026-0001

Dataset metadata MUST include at least:

Product ID

Dataset ID

Dataset Version

Engine Version

Scenario Pack

Patient Record Count

Patient Event Count

Generation Timestamp

Data Type

Configuration Hash

Validation Status

License ID


A Dataset MUST NOT be released when:

validation_status != PASS


---

3.3 HFSG Generator Edition

Product ID: HFSG-GEN

Purpose:
Allow an authorized user to generate new HFSG datasets using the same approved model.

Required capabilities:

load versioned configuration;

select scenario;

run Standard-8 scenarios;

run a customer-defined scenario;

generate patient-level records;

generate patient-event records;

run Batch generation;

write partitioned Parquet;

generate Manifest;

generate Validation Report;

support reproducible generation using random seeds.


Generator Edition is built from the same HFSG Core Engine as Demo and Dataset Edition.


---

4. Shared Core

The three products MUST NOT be implemented as three independent modelling systems.

They MUST use one common HFSG Core Engine.

Conceptually:

Scenario Configuration
        ↓
Aggregate Flow Engine
        ↓
Patient Generator
        ↓
Patient Event Engine
        ↓
Reconciliation / Validation
        ↓
Parquet Output
        ↓
Product-specific interface

The model logic MUST NOT be duplicated separately for Demo, Dataset and Generator editions.


---

5. MVP Scope

Phase 1 MUST implement:

1. aggregate ED/Ward/ICU flow simulation;


2. synthetic patient generation;


3. patient event generation;


4. eight predefined operational scenarios;


5. one configurable customer scenario;


6. patient-to-aggregate reconciliation;


7. reproducible random generation;


8. small Demo generation;


9. Batch dataset generation;


10. partitioned Parquet output;


11. Dataset ID and version metadata;
12. automated validation;


13. scenario comparison;


14. rule-based operational summary.




---

6. Standard Scenario Pack

The MVP Scenario Pack is:

Standard-8

It contains:

S1 Normal Operation

S2 Busy Week

S3 Crisis Mode

S4 ICU Capacity Loss

S5 Bed Block

S6 Compound Stress

S7 Emergency Wave

S8 Recovery Strategy


The product MUST also support:

CUSTOM

Customer Scenario parameters MUST remain configurable.

Scenario definitions MUST come from configuration and MUST NOT be silently hard-coded into the simulation engine.


---

7. MVP Data Products

Patient Table

One record per synthetic patient.

Primary format:

Parquet

Patient Event Table

One record per synthetic patient event.

Events may include:

ARRIVAL

TRANSFER

DISCHARGE

DEATH


Aggregate Time Series

Hourly system-level data describing:

ED census

Specialty census

General Ward census

ICU census

arrivals

transfers

discharges

deaths

capacity utilization

unmet demand


Simulation Summary

One summary record per simulation run.


---

8. Batch Target

Default commercial Batch target:

1,000,000 patient records

Current planning configuration:

Standard scenarios: 8

planned runs per scenario: 120

initial planned runs: 960

standard simulation horizon: 30 days

patient write chunk: 50,000 rows

event write chunk: 100,000 rows

Parquet compression: ZSTD

partition key: scenario_id


These are configurable operational settings, not scientific constants.

The Batch process MUST NOT keep the complete dataset in memory.


---

9. Intended Uses

HFSG MVP is intended for:

software testing;

data-pipeline testing;

dashboard development;

research prototyping;

education;

demonstrations;

scenario experimentation;

early commercial pilots.



---

10. Explicitly Out of Scope

Phase 1 MUST NOT implement or claim:

real patient data;

re-identification of real patients;

clinically validated synthetic data;

clinical prediction;

clinical decision support;

diagnosis generation;

ICD coding;

medication data;

laboratory data;

vital signs;

clinical notes;

digital twin functionality;

HIS/EHR/FHIR integration;

public API;

authentication;

payment system;

multi-user administration.


Any such feature requires a future approved product version.


---

11. Commercial Release Rule

A dataset may be packaged as an HFSG commercial data product only when:

required files exist;

Dataset ID is assigned;

version is assigned;

configuration is preserved;

random seed policy is recorded;

patient/event reconciliation passes;

mass balance passes;

uniqueness tests pass;

temporal consistency passes;

scenario coverage passes;

Parquet files are readable;

validation_status = PASS.


Otherwise the release status is:

NOT RELEASABLE


---

12. Product Success Criteria for Phase 1

Phase 1 is successful when the system can:

1. run the Demo;


2. generate valid patient journeys;


3. reconcile patient events with aggregate hospital flows;


4. run Standard-8;


5. execute a customer scenario;


6. complete a 100,000-patient dry run;


7. complete a >=1,000,000-patient Batch;


8. generate versioned Parquet packages;


9. generate Manifest and Validation Report automatically;


10. package the output as an identifiable HFSG Data Product.




---

13. Product Boundary

The scientific source provides the conceptual compartmental hospital-flow foundation.

HFSG adds engineering layers required for synthetic data generation, including:

balanced production flows;

stochastic arrivals;

capacity constraints;

Patient Generator;

Patient Event Generator;

scenario framework;

Batch generation;

Parquet storage;

validation;

product versioning.


These extensions MUST NOT be represented as equations or findings directly published in the source article.


---

14. Change Control

During MVP development, OpenCode and developers MUST NOT independently expand product scope.

New features MUST be placed in the backlog unless explicitly approved.

In particular, do not add:

machine learning;

LLM functionality;

digital twin functionality;

clinical variables;
new hospital departments;

database infrastructure;

APIs;

cloud architecture;


unless the project owner explicitly changes the specification.

PRODUCT.md defines WHAT is being built.

MODEL.md defines HOW the simulation model must behave.