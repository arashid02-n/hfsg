# HFSG FROZEN v1.0 — Repository Specification Set

This folder contains the cross-checked, frozen Phase 1 specification set:

- PRODUCT.md
- MODEL.md
- ARCHITECTURE.md
- OPERATIONS.md
- AGENTS.md
- FREEZE_MANIFEST.json

## Seven approved cross-document decisions

1. Integerization = Largest Remainder Method + seeded deterministic tie-break.
2. Initial Patient Population is mandatory.
3. Aggregate Engine determines HOW MANY; Patient Event Generator determines WHICH.
4. Arrival at timestep t becomes movement-eligible at t+1.
5. Capacity uses beginning-of-step occupancy; released capacity becomes available at t+1.
6. Batch uses master_seed and deterministic child seed per scenario/run.
7. Batch completion requires >=1,000,000 patient records AND complete Standard-8 coverage.

## Step 3 authorization

After these five root documents replace/synchronize the repository versions and the approved YAML is updated to match them:

**Step 3 — Configuration & Core Engine is authorized to begin.**

Frozen documents must not be silently edited. Any model/scope change requires an explicit project decision and a versioned specification update.
