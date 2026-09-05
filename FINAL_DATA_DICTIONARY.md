# HFSG — Final Data Dictionary (Phase 1 Release)

**Dataset:** `HFSG-DS-STD8-2026-20260905-120702`
**Schema source:** actual written Parquet files in `data/output/step9/` and `src/hfsg/output.py`, `src/hfsg/units.py`, `src/hfsg/events.py`, `src/hfsg/patients.py`, `config/base.yaml`, MODEL.md.

> **Phase 1 data status:** These are SYNTHETIC, SCENARIO-DRIVEN simulated data. They MUST NOT be represented or used as clinically validated, real-world-equivalent, or patient-identifiable clinical data.

**Global conventions**

- `simulation_id`: string (large_string). Unique identifier of the simulation run that generated the row (algorithmically derived; one value per run, shared across the three primary outputs of that run).
- `scenario_id`: string (large_string). Allowed values `S1`…`S8`, `CUSTOM`. Identifies the approved scenario definition pack.
- Time model: discrete hourly timesteps `hour = 0 … 719` (720 hours = 30 days). Datetimes are ISO-8601 UTC strings (`YYYY-MM-DDTHH:MM:SS+00:00`), simulated start `2026-01-01T00:00:00+00:00`.
- Integer flows are implemented with the Largest Remainder Method + seeded deterministic tie-break (MODEL.md §16). `realized_*` flows are the authoritative integer patient flows.

---

## 1. Patients — `patients/patients_*.parquet`

One row per synthetic patient. 109,119 rows.

| Variable | Data Type | Definition | Unit | Allowed Range / Allowed Values | Variable Origin / Source |
|---|---|---|---|---|---|
| `simulation_id` | string | Run identifier the patient belongs to | — | 1 value per run | Pipeline (derived per run) |
| `scenario_id` | string | Scenario pack identifier | — | `S1, S2, S3, S4, S5, S6, S7, S8, CUSTOM` | Scenario framework (configuration) |
| `patient_id` | int64 | Patient identifier, unique within the run | count | `1 .. total_patients_in_run` | Patient Generator (sequential) |
| `arrival_datetime` | string | Simulation datetime when the patient entered the system (hour of ARRIVAL or of initial occupancy) | ISO-8601 UTC | `2026-01-01T00:00:00+00:00` + `hour` | Patient Generator / clock |
| `entry_type` | string | How the patient entered the simulation | — | `INITIAL`, `ARRIVAL` | `INITIAL`: initial patient population (MODEL.md §13); `ARRIVAL`: stochastic arrival stream (MODEL.md §6) |
| `initial_unit` | string | Unit the patient occupied on entry | — | `ed`, `specialty`, `general`, `icu` | Patient Generator (initial census for `INITIAL`; `ed` for `ARRIVAL`) |
| `age_group` | string | Synthetic age band | — | `0-17`, `18-44`, `45-64`, `65-79`, `80+` | Config `patient_attributes.age_group` (provenance `ASSUMPTION`) |
| `sex` | string | Synthetic sex label | — | `Female`, `Male` | Config `patient_attributes.sex` (provenance `ASSUMPTION`) |
| `severity_level` | string | Synthetic severity class (selection driver, not a clinical diagnosis) | — | `Low`, `Medium`, `High`, `Critical` | Config `patient_attributes.severity_level` (provenance `ASSUMPTION`) |
| `arrival_mode` | string | Synthetic mode of arrival | — | `Walk-in`, `Ambulance`, `Transfer` | Config `patient_attributes.arrival_mode` (provenance `ASSUMPTION`) |

---

## 2. Patient Events — `patient_events/patient_events_*.parquet`

One row per patient event. 316,010 rows.

| Variable | Data Type | Definition | Unit | Allowed Range / Allowed Values | Variable Origin / Source |
|---|---|---|---|---|---|
| `simulation_id` | string | Run identifier the event belongs to | — | 1 value per run | Pipeline (derived per run) |
| `scenario_id` | string | Scenario pack identifier | — | `S1`…`S8`, `CUSTOM` | Scenario framework (configuration) |
| `patient_id` | int64 | Patient the event belongs to | count | patient range of the run | Patient Event Generator |
| `event_id` | int64 | Event identifier, unique within the run, chronological | count | `1 .. total_events_in_run` | Patient Event Generator (sequential) |
| `event_datetime` | string | Simulation datetime of the event | ISO-8601 UTC | simulated start + `event_hour` | Patient Event Generator / clock |
| `event_hour` | int64 | Hour index of the event | hour | `0 .. 719` | Simulation clock |
| `event_type` | string | Kind of event | — | `ARRIVAL`, `TRANSFER`, `DISCHARGE`, `DEATH` | Patient Event Generator (MODEL.md §17) — note: 0 `DEATH` events occur in this released dataset; the type and its `M_*` quotas are defined and supported |
| `from_unit` | string | Source unit/location of the movement | — | `ed`, `specialty`, `general`, `icu`, `external` | Patient Event Generator |
| `to_unit` | string | Destination unit/location of the movement | — | `ed`, `specialty`, `general`, `icu`, `discharged`, `deceased` | Patient Event Generator |
| `quota_flow` | string | The approved integer flow (aggregate quota) that the event realizes | — | `arrivals`, `T_EC`, `T_EG`, `T_EI`, `T_CG`, `T_CI`, `T_GI`, `T_EH`, `D_C`, `D_G`, `D_I`, `M_C`, `M_G`, `M_I` | Aggregate integer flow allocation (realized_integer_flow) |

---

## 3. Aggregate Time Series — `aggregate_timeseries/aggregate_timeseries_*.parquet`

One row per hour per run. 58,320 rows.

### 3.1 Identity and stock columns

| Variable | Data Type | Definition | Unit | Allowed Range / Allowed Values | Variable Origin / Source |
|---|---|---|---|---|---|
| `simulation_id` | string | Run identifier | — | 1 value per run | Pipeline |
| `scenario_id` | string | Scenario pack identifier | — | `S1`…`S8`, `CUSTOM` | Scenario framework |
| `hour` | int64 | Hour index | hour | `0 .. 719` | Simulation clock |
| `ed_census` | int64 | ED occupied beds at end of hour, `E(h)` | patients | `0 .. 40` (capacity) | Aggregate Engine state |
| `specialty_census` | int64 | Specialty occupied beds, `C(h)` | patients | `0 .. 60` (capacity) | Aggregate Engine state |
| `general_census` | int64 | General Ward occupied beds, `G(h)` | patients | `0 .. 100` (capacity) | Aggregate Engine state |
| `icu_census` | int64 | ICU occupied beds, `I(h)` | patients | `0 .. 20` (capacity) | Aggregate Engine state |
| `discharged` | int64 | Cumulative discharges by hour `h`, `D(h)` | patients | `0 .. total_discharged` | Aggregate Engine state |
| `deceased` | int64 | Cumulative deaths by hour `h`, `M(h)` | patients | `0 .. total_deceased` (0 in released dataset) | Aggregate Engine state |
| `cumulative_arrivals` | int64 | Cumulative accepted arrivals by hour `h` | patients | `0 .. cumulative_arrivals` | Aggregate Engine state |
| `arrivals_drawn` | int64 | Stochastic arrivals drawn in hour `h` (before capacity constraint) | patients/hour | `>= 0` | Stochastic arrival process (Poisson, MODEL.md §6) |
| `arrivals_accepted` | int64 | Arrivals admitted in hour `h` (capacity-constrained, integer) | patients/hour | `0 .. arrivals_drawn` | Constrained/integer flow allocation |
| `unmet_arrivals` | int64 | Arrival demand not admitted in hour `h` | patients/hour | `0 .. arrivals_drawn` | Arrival constraint (never admitted later) |

### 3.2 Flow columns

Each approved flow appears in four variants. Allowed flow set per MODEL.md §10/§14 (subset present in released data is recorded in the Value column family):

- Stocks that must never go negative: `no negative stocks`
- `_requested` — unconstrained flow implied by rates and census (continuous).
- `_constrained` — flow after capacity/source constraints (continuous).
- `_realized` — final integer flow that was actually executed (authoritative; equals patient-event count for that flow; `int64`). Note `arrivals_accepted` is reported separately.
- `_integerization_difference` — `realized - constrained` rounding residue (continuous).

| Flow | Meaning | Allowed (integer hours) | Occurrence in released dataset |
|---|---|---|---|
| `T_EC` | ED → Specialty transfers | `>= 0` | present |
| `T_EG` | ED → General transfers | `>= 0` | present |
| `T_EI` | ED → ICU transfers | `>= 0` | present |
| `T_CG` | Specialty → General transfers | `>= 0` | present |
| `T_CI` | Specialty → ICU transfers | `>= 0` | present |
| `T_GI` | General → ICU transfers | `>= 0` | present |
| `T_EH` | ED → Home (discharge to community) | `>= 0` | present |
| `D_C` | Specialty discharges | `>= 0` | present |
| `D_G` | General Ward discharges | `>= 0` | present |
| `D_I` | ICU discharges | `>= 0` | present |
| `M_C` | Specialty deaths | `>= 0` | 0 in released dataset |
| `M_G` | General Ward deaths | `>= 0` | 0 in released dataset |
| `M_I` | ICU deaths | `>= 0` | 0 in released dataset |

Column names therefore are exactly one of:

`T_EC_realized`, `T_EC_constrained`, `T_EC_requested`, `T_EC_integerization_difference`, …, `D_G_…`, `M_I_…`
(full 13 flow names × 4 variants).

- Data types: `realized` → `int64`; `constrained`, `requested`, `integerization_difference` → `double`.
- Units: patients per hour (continuous variants are non-integer synthetic flows).
- Constraint invariances (MODEL.md): realized requests never exceed source stock; destinations never exceed beginning-of-step vacancy; no negative stocks; mass-balance residuals `abs(MBE) < 1e-6`.

---

## 4. Simulation summary (reference) — `simulation_summary.parquet`

One row per run (81 rows): `simulation_id`, `scenario_id`, `run_index`, `master_seed`, `child_seed`, `total_patients`, `total_events`, `total_arrivals`, `total_transfers`, `total_discharges`, `total_deaths`, `final_ed`, `final_specialty`, `final_general`, `final_icu`, `final_discharged`, `final_deceased`, `mean_active_census`, `max_active_census`, `max_abs_mbe`, `reconciliation_issues`, `configuration_hash` (all derived from the simulation; seeds and configuration hash recorded for reproducibility).

## 5. Scenario comparison (reference) — `scenario_comparison.csv`

One aggregate row per scenario (9 rows) summarising run count, totals, census, `max_abs_mbe`, reconciliation/event-quota/invariant counts, `configuration_hash`, `reference_child_seed`.