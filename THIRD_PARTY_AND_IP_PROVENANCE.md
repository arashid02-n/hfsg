# HFSG — Third-Party / IP / Data Provenance Audit (Phase 1)

**Audit date:** 2026-09-05
**Dataset audited:** `HFSG-DS-STD8-2026-20260905-120702` (final Phase 1 release)
**Validated/Audited Core Commit:** `08032c3`
**Final Handover Commit:** `7f5a117` (audited at the Final Handover Commit; the difference from the Core Commit is documentation/closeout only — Core/Model logic was NOT changed between `08032c3` and `7f5a117`)
**Requested by:** Project Owner (Mohammad Nazari)
**Scope:** final owner-requested Third-Party / IP / Data Provenance audit for Final Acceptance preparation.
**Result:** **PASS** — no real patient data, no PII, no proprietary third-party code, no undeclared third-party assets; all third-party software is permissive open source and fully declared.

> **Property note:** All HFSG Phase 1 generated data are SYNTHETIC, SCENARIO-DRIVEN simulated data. They MUST NOT be represented or used as clinically validated, real-world-equivalent, or patient-identifiable clinical data.

---

## 1. Audit method (what was inspected)

| Item | Method |
|---|---|
| Repositories / files | `git ls-files` (full inventory) + filesystem scan of the working tree (excluding `.venv`) |
| Source code import inventory | AST parse of every `.py` in `src/`, `scripts/`, `tests/` (all `import`/`from` statements collected) |
| Installed dependencies | `pip list` + `importlib.metadata` reading of each package's `METADATA` (Name, Version, License, Home-page, Author) |
| Dependency lock | `requirements.txt` and `requirements-lock.txt` |
| Models / weights / ML assets | tree scan for `*.pkl *.pt *.onnx *.h5 *.joblib *.npz *.mat` etc. |
| Dataset | full `step9` release read via pyarrow: all string/dictionary columns of `patients` (109,119 rows), `patient_events` (316,010 rows), `aggregate_timeseries` (58,320 rows), plus `simulation_summary.parquet` |
| Preview / sample assets | all 4 xlsx previews in `03_PREVIEW` parsed cell-by-cell via openpyxl |
| Reference material | search of the repository and git history for `*.pdf *.xlsx *.xls` and the cited paper |
| Secrets / credentials | tree scan for `*.env`, `.env*`, `*.pem`, `*.key`, `*.p12`, `*credential*`, `*token*`; scan of the handover ZIP index |

**Determination rules:** any item whose license, version or provider could not be verified is recorded as `NOT VERIFIED`. No item required a `NOT VERIFIED` marking (every listed dependency is verified from its installed package `METADATA`).

---

## 2. Third-party software inventory

All third-party software is open source, permissively licensed, and obtained from the official upstream providers via PyPI (`pip`). **No commercial-use restrictions** apply to any listed component for HFSG's commercial use. **Redistribution restrictions** are limited to the standard notice-retention rules of each permissive license (BSD *and-clause*, MIT, Apache-2.0 NOTICE/attribution). None are copyleft, so none impose any obligation to open-source HFSG's own code.

### 2.1 Runtime dependencies (used directly by HFSG source code)

| Name | Source / Provider | Exact version | License | Commercial-use restrictions | Redistribution restrictions | How it is used |
|---|---|---|---|---|---|---|
| CPython (Python) | python.org, PSF | 3.12.3 | PSF License v2 (BSD-style); Zero-Clause BSD for docs | None | Retain PSF license on redistribution | Runtime interpreter for the whole system |
| NumPy | numpy.org, NumPy Developers | 2.5.2 | BSD-3-Clause overall (METADATA expression additionally lists per-module 0BSD/MIT/Zlib/CC0-1.0) | None | Retain BSD notices on redistribution | Array math: aggregate engine, quota allocation, validation, patients, events, output |
| pandas | pandas.pydata.org, Pandas Development Team | 3.0.5 | BSD-3-Clause | None | Retain BSD notices on redistribution | DataFrames in output pipeline and batch processing |
| PyArrow | arrow.apache.org, Apache Software Foundation | 25.0.1 | Apache-2.0 (incl. bundled C++ Arrow runtime) | None | Include Apache-2.0 license copy and attribution notices on redistribution | Parquet read/write, partitioned output, dataset validation/readability |
| PyYAML | pyyaml.org / GitHub, Kirill Simonov | 6.0.3 | MIT | None | Retain MIT notice on redistribution | Parsing approved YAML configuration and scenario files |

### 2.2 Test-time dependencies

| Name | Provider | Exact version | License | How it is used |
|---|---|---|---|---|
| pytest | pytest-dev | 9.1.1 | MIT | Test runner (test suite: 177 tests) |
| pluggy | pytest-dev | 1.6.0 | MIT | pytest plugin machinery (transitive; not imported by HFSG code) |
| iniconfig | pytest-dev | 2.3.0 | MIT | pytest config parsing (transitive; not imported by HFSG code) |
| packaging | PyPA | 26.3 | Apache-2.0 OR BSD-2-Clause | pytest support (transitive; not imported by HFSG code) |
| Pygments | pygments.org | 2.21.0 | BSD-2-Clause | pytest terminal output styling (transitive; not imported by HFSG code) |

All of §2.2 are MIT/BSD/Apache-2.0 permissive; no commercial-use or redistribution restrictions beyond notice retention.

### 2.3 Transitive runtime dependencies (not imported directly by HFSG code)

| Name | Provider | Exact version | License | How it is used |
|---|---|---|---|---|
| python-dateutil | dateutil project (GitHub) | 2.9.0.post0 | Dual: Apache-2.0 (contribs ≥2017-12-01) + BSD-3-Clause (legacy) | pandas dependency (datetime handling) |
| six | benjaminp (GitHub) | 1.17.0 | MIT | legacy Python-2/3 compatibility utility (transitive) |

### 2.4 Preview-generation dependency (NOT a runtime dependency)

| Name | Provider | Exact version | License | How it is used |
|---|---|---|---|---|
| openpyxl | openpyxl project | 3.1.5 | MIT | Excel preview files (03_PREVIEW) generation only; not imported by any file in `src/`, `scripts/`, or `tests/` |
| et_xmlfile | openpyxl project | 2.0.0 | MIT | openpyxl dependency |

### 2.5 Tooling (not part of the distributed product)

| Name | Provider | Exact version | License | How it is used |
|---|---|---|---|---|
| pip | PyPA | 26.2.1 | MIT | Python package installer |

**Delivery of dependencies:** dependencies are obtained from upstream via `pip` at install time; dependency code is **not** vendored into the HFSG repository or handover package (verified: no `site-packages`, `dist-info`, or `.venv` content exists inside the handover ZIP). Release reproducibility is pinned by `requirements-lock.txt` (all 14 package versions above are captured in that lock file).

---

## 3. IP / data findings (explicit verification)

| Question | Finding | Evidence |
|---|---|---|
| Real patient data | **NONE** | Dataset and previews contain only HFSG-generated fields. `patients` is limited to categorical/temporal identifiers and synthetic attributes; `patient_events` and `aggregate_timeseries` are event/quota/census records. No source-of-truth clinical feed is connected to the system. |
| PII | **NONE** | Regex sweep over every string/dictionary value of all three release tables (745,449 rows total) and all 4 preview xlsx (128,522 cells): **0** email, phone, SSN, ZIP+4, or `Firstname Lastname` hits. Patient identifiers are integer `patient_id` in range (~thousands, per run) with no names, dates of birth, contact details, addresses or national identifiers. |
| Proprietary code from another employer/client | **NONE** | All code under `src/`, `scripts/`, `tests/`, `config/` is authored for this project. AST import scan shows only: (a) Python standard library, (b) HFSG-internal modules (`.hfsg`), and (c) the declared OSS dependencies of §2.1–§2.4. No copied/vendored source and no third-party copyright headers found in repository files. |
| Undeclared third-party assets | **NONE** | Every file in the released dataset and handover package is accounted for by `dataset_manifest.json`, `SHA256SUMS.txt`, and `HANDOVER_MANIFEST.json`; every file in `02_RELEASED_DATASET` (249 files) is a declared release artifact. No PDFs, spreadsheets, models/weights, or databases are bundled. The only stray item, `data/funda.db`, is a 0-byte empty SQLite placeholder outside the release and is NOT included in the dataset or handover package. |

**Also verified — no secrets:** no `.env`, `.pem`, `.key`, `.p12`, credential, token, or private-key files exist in the repository or handover package.

---

## 4. Ownership distinction (as requested)

1. **Open-source third-party dependencies** — the packages in §2 above (numpy, pandas, pyarrow, PyYAML at runtime; pytest stack at test time; openpyxl for previews; python-dateutil/six/et_xmlfile transitive). Imported, not included; licenses permissive.
2. **HFSG-owned source code** — everything under `src/hfsg/`, `scripts/`, `tests/`, `config/base.yaml`, and all project documentation (MODEL.md, PRODUCT.md, ARCHITECTURE.md, OPERATIONS.md, AGENTS.md, manifests, closeout/acceptance/report documents). Authored for this project. The project's declared license identifier is `HFSG-EULA-1.0` (stated in `src/hfsg/pipeline.py` and `dataset_manifest.json`).
3. **HFSG-generated synthetic data** — dataset `HFSG-DS-STD8-2026-20260905-120702` (109,119 patients / 316,010 events / 58,320 aggregate rows) and the 4 xlsx previews. Produced entirely by HFSG Phase 1 code; represent no real individuals.

## 5. Scientific reference / model provenance

- **Cited scientific article (NOT bundled, NOT redistributed):** Al-Karkhi & Byatt (2025), *A compartmental model to describe acute medical in-patient flow through a hospital* — referenced for provenance only in `MODEL.md` (Model A / Scientific Reference Model). The article itself is not contained in the repository or handover package; its license is therefore **NOT VERIFIED** (not applicable — it is not redistributed).
- **Model B** (HFSG Production Model) is HFSG's engineering adaptation of the compartment concept. Every parameter in `config/base.yaml` carries a provenance classification (`PAPER`, `TRANSFORMED`, `EXPERT`, `ASSUMPTION`, `CALIBRATED`) per `MODEL.md` §26; no `ASSUMPTION` parameter is mislabelled as `PAPER`. HFSG engineering extensions (patient layer, integer quota allocation, scenario framework, batch, Parquet, etc.) are documented as HFSG extensions and are not claimed to be direct published findings.

## 6. Dependency declarations vs actual environment

- `requirements.txt` (numpy, pandas, pyyaml, pyarrow) — subset actually imported by HFSG source.
- `requirements-lock.txt` — records the exact installed environment (all §2 packages + preview tooling), generated 2026-09-05, Python 3.12.3 / Linux x86_64.
- Environment check: `pip list` of the release venv matches `requirements-lock.txt` exactly (versions above). **No unexpected packages installed.**

## 7. NOT VERIFIED items

- License of the cited scientific article (article not redistributed — out of scope; the system never ships or executes it).
- Nothing else required a `NOT VERIFIED` marking.

## 8. Residual notes for the Project Owner

- `HFSG-EULA-1.0` is a declared license identifier; no full EULA/license text file is yet distributed alongside the product. Consider publishing the EULA text as a Phase 2 release item (recommendation only; not a Phase 1 defect).
- `git diff --check` and all 177 tests PASS; the released dataset and previews carry no third-party content.

**Audit author:** HFSG Phase 1 release engineering (prepared for Project Owner Final Acceptance review; Final Acceptance is issued by the Project Owner, not by this document).