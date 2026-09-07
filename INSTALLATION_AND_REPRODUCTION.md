# HFSG — Installation and Reproduction Guide

This guide tells another engineer how to take the HFSG source in this handover
package (`01_SOURCE/`), build a Python environment, run the simulation system,
generate a dataset, validate it, and reproduce a deterministic run.

All commands are the actual commands used in this project (Python 3 + venv).
Paths below assume a checkout named `hfsg` with an independent venv.

> **Phase 1 data status:** All HFSG Phase 1 generated data are SYNTHETIC, SCENARIO-DRIVEN simulated data.
> They MUST NOT be represented or used as clinically validated, real-world-equivalent, or patient-identifiable clinical data.
> Phase 1 approved Acceptance Scale = approximately 100,000 synthetic patients (actual released dataset: 109,119 patient records);
> the `>= 1,000,000` target is deferred to Phase 2 as Scale Qualification (HFSG-PH1-DEV-001).

## 1. Obtain the source

The complete final source is in `01_SOURCE/`. On a new machine:

```bash
git clone https://github.com/arashid02-n/hfsg.git   # final handover commit: 0764a3d
cd hfsg
git checkout 0764a3d
```

Source-commit reference (verified from Git history):

- **Validated/Audited Core Commit:** `08032c3` (last commit affecting Core/Model logic — Step 9: 100k-patient batch generation and validation)
- **Final Handover Commit:** `0764a3d` (final documentation/closeout commit — technical/commercial separation and unified commit references)
- The difference between the two is **documentation/closeout only**; Core/Model logic was
  NOT changed between `08032c3` and `0764a3d` (verified: the diff of `src/`, `config/`,
  `scripts/`, `tests/`, `requirements.txt` between the two commits is empty).

or unpack the handover `01_SOURCE/` directory directly. The released dataset
ships in `02_RELEASED_DATASET/` (see section "11. Reproduce a deterministic run" for
the difference between reproducing the data and regenerating the engine).

## 2. Create the Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 3. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

`requirements.txt` contains the runtime/test dependencies actually used:
`numpy`, `pandas`, `pyyaml`, `pyarrow`. For byte-exact reproduction of the final
release environment, use the lock file instead:

```bash
pip install -r requirements-lock.txt
```

which pins numpy 2.5.2, pandas 3.0.5, pyarrow 25.0.1, PyYAML 6.0.3, pytest 9.1.1, etc.
(`openpyxl` is included in the lock and is only needed to rebuild the Excel preview files;
it is not a runtime dependency.)

## 4. Load configuration

The model, scenario, batch and validation parameters come from approved YAML:

```bash
python -c "import sys; sys.path.insert(0,'src'); from hfsg.config import ConfigurationLoader; c=ConfigurationLoader().load('config/base.yaml'); print('master_seed=', c.data['reproducibility']['master_seed']); print('scenarios=', list(c.data['scenarios']['definitions']))"
```

## 5. Run the tests

```bash
python -m pytest tests/ -q
```

Expected result at release: entirely PASS; on the final handover commit `0764a3d`
the suite contains 177 passing tests.

## 6. Run one scenario

Use the Step 8 driver, which runs the full pipeline for one or more scenarios
and writes the output set to a directory:

```bash
python scripts/run_step8.py --out data/output/run_s1 --scenario S1
python scripts/run_step8.py --out data/output/run_s4 --scenario S4
```

## 7. Run Standard-8

```bash
python scripts/run_step8.py --out data/output/step8_all --scenario S1,S2,S3,S4,S5,S6,S7,S8
```

## 8. Run CUSTOM

```bash
python scripts/run_step8.py --out data/output/run_custom --scenario CUSTOM --custom '{"arrivals_multiplier":1.25,"icu_capacity_multiplier":1.0,"discharge_multiplier":1.1}'
```

CUSTOM parameters must stay inside the approved limits in
`config/base.yaml` (`scenarios.custom_parameter_limits`); out-of-limit profiles
are rejected by the configuration validator.

## 9. Generate a new dataset (batch)

The batch orchestrator derives one child seed per (scenario, run) from the
`master_seed` in `config/base.yaml` (`reproducibility.master_seed = 20260805`),
writes scenario-partitioned ZSTD Parquet, and checkpoints progress so an
interrupted batch can be resumed:

```bash
python scripts/run_step9.py --mode dryrun --out data/output/new_dryrun          # small verification batch
python scripts/run_step9.py --mode production --out data/output/new_dataset     # full target batch
python scripts/run_step9.py --mode resume --planned-runs 120 --out data/output/new_dataset   # resume if interrupted
```

Prefer run_step9's built-in modes; they handle the full write pipeline
(patients, patient events, aggregate timeseries, summary, scenario comparison,
manifest, used configuration, validation report).

## 10. Validate the generated dataset

```bash
python scripts/run_step9.py --mode validate --out data/output/new_dataset
```

This re-reads every written part file and re-checks: parquet readability,
row counts, scenario coverage (S1–S8 + CUSTOM), mass balance, aggregate-patient
reconciliation, event-quota reconciliation, capacity/source invariants,
uniqueness, temporal consistency, summary alignment, manifest consistency,
configuration-hash match, and a reproducibility sample (run index 0 of every
scenario). It reports `VALIDATED` only when all checks pass.

## 11. Reproduce a deterministic run

Every run is deterministic given the `master_seed`, the scenario schedule, the
configuration and the run index (MODEL.md §27). To reproduce exactly what was
released (dataset `HFSG-DS-STD8-2026-20260905-120702`, master seed 20260805):

```bash
cd <hfsg checkout>                          # final handover commit 0764a3d (core: 08032c3)
python -m pytest tests/ -q                  # 177 tests
python scripts/run_step9.py --mode validate --out data/output/step9    # validates the released dataset
```

Because the released dataset was built from `master_seed = 20260805` with the
exact configuration preserved in `02_RELEASED_DATASET/used_configuration.yaml`
(configuration hash `f5e1bc49e1bb43a8e10e0a2b9f135501eb07598567728b2c429a403b7673d8cd`),
re-running `--mode production` with the same master seed and configuration
regenerates the same 109,119 patients / 316,010 events (timestamp and batch
metadata fields are the only volatile values and are excluded from
reproducibility comparisons).

Single-run reproducibility check (fixture-style; the seed is derived from the
`master_seed` in the loaded configuration, default 20260805):

```bash
python scripts/smoke_patient_events.py            # S1, run index 0, 720h
python scripts/smoke_patient_events.py config/base.yaml S4 3 720   # explicit config/scenario/run/horizon
```

This prints the derived `child_seed` and runs the engine->quota->patient->event
loop with seed-reproducibility checks against the deterministic fixture.

## Notes

- Do not load the whole dataset into memory; the batch writes in bounded chunks
  (write buffers configured in `config/base.yaml`).
- Do not commit `data/output/` to git; the dataset is a separate deliverable.
- Frozen project documents (`PRODUCT.md`, `MODEL.md`, `ARCHITECTURE.md`,
  `OPERATIONS.md`, `AGENTS.md`, `FREEZE_MANIFEST.json`, `README_FREEZE.md`)
  govern model semantics; do not modify them without a project decision.