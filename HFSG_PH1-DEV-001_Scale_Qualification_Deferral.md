# HFSG-PH1-DEV-001 — Scale Qualification Deferral

**Document Type:** Project decision record
**Status:** APPROVED
**Date:** 2026-09-05
**Authority:** Project Owner (Mohammad Nazari)
**Applies to:** HFSG Phase 1 (MVP 1.0)

---

## 1. Decision

The Project Owner has officially approved the following acceptance decision for HFSG Phase 1:

1. **Approximately 100,000 synthetic patients (`~100K`) is the approved Acceptance Scale for Phase 1.**
   - The released production dataset `HFSG-DS-STD8-2026-20260905-120702` contains 109,119 patient records,
     which satisfies and exceeds the approved Acceptance Scale.
2. **The `>= 1,000,000` patient Batch was NOT executed in Phase 1 because of current hardware/storage limitations.**
   - The build workstation (3.7 GiB RAM, ~1.3 GiB free disk, 2 CPU cores) cannot feasibly hold, write or validate
     a full 1,000,000-record dataset.
3. **The `>= 1,000,000` patient Batch is DEFERRED to Phase 2 as Scale Qualification.**
   - Phase 2 Scale Qualification will be executed when adequate hardware/storage/cloud infrastructure is available.
4. **This deferral is NOT a defect, failure, or non-acceptance of Phase 1.**
   - PRODUCT.md §12 success criterion 6 ("complete a 100,000-patient dry run") is satisfied and exceeded at
     production scale; every other Phase 1 success criterion is satisfied (see `FINAL_ACCEPTANCE_SUMMARY.md`).

## 2. Effective scope

- Phase 1 validated/approved Acceptance Scale: **approximately 100,000 synthetic patients**.
- Phase 2 future Scale Qualification target: **`>= 1,000,000` synthetic patients**.
- Release state of the Phase 1 dataset `HFSG-DS-STD8-2026-20260905-120702`: **RELEASED** (validation conditions PASS;
  commercial release approved by the Project Owner subject to final PASS conditions, which are confirmed).

## 3. What this decision does NOT do

- Does NOT change Model B equations, invariants, or scientific provenance.
- Does NOT change implementation logic, schemas, scenarios, validation logic, or the released dataset.
- Does NOT start Phase 2.
- Does NOT relax any technical validation requirement for the released dataset.

## 4. Documentation consequences

References in the frozen specification set that state a `>= 1,000,000` Phase 1 production/completion target are
amended by this decision for Phase 1 acceptance purposes:

- PRODUCT.md §3.2 (HFSG Dataset Edition target) and §8 (Batch Target)
- PRODUCT.md §12 (Product Success Criteria) item 7
- MODEL.md §26 (Batch Generation)
- OPERATIONS.md §17 (Production Batch — Gate G3) and §29 item 12
- AGENTS.md §21 (Batch Generation Rules)
- README_FREEZE.md decision 7 and FREEZE_MANIFEST.json decision 7
- HFSG_Step8_Execution_Instruction.md (Step 9 Stop Rule)

The model/specification meaning is preserved; the Phase 1 acceptance-scale reading is clarified to match this
decision. No implementation logic was modified.

## 5. Related records

- Dataset manifest `scale_qualification`, `commercial_release`, `production_target_notes`
  (`data/output/step9/dataset_manifest.json`)
- `HFSG_Phase1_Release_Closeout.md`
- `FINAL_ACCEPTANCE_SUMMARY.md`

---

Approved by the Project Owner on 5 September 2026. Phase 1 does NOT require a 1M build to be accepted.