"""Deterministic seed derivation for HFSG simulation runs.

Implements the Batch Seed Policy from MODEL.md section 27: every run derives
a deterministic child seed from the master seed, the scenario ID and the run
index. The derivation algorithm is versioned by implementation so that a
fixed master seed, scenario schedule and configuration always reproduce the
same child seed.
"""

from __future__ import annotations

import hashlib

CHILD_SEED_ALGORITHM_VERSION = "hfsg-child-seed-v1"

_SEED_MASK = (1 << 63) - 1


def derive_child_seed(
    master_seed: int | str, scenario_id: str, run_index: int
) -> int:
    """Derive a deterministic child seed.

    The payload binds the algorithm version, master seed, scenario ID and
    run index; SHA-256 is truncated into the signed-safe 63-bit range used
    by common RNG seeding APIs.
    """
    if run_index < 0:
        raise ValueError(f"run_index must be non-negative, got {run_index}")
    scenario = str(scenario_id)
    if not scenario:
        raise ValueError("scenario_id must be a non-empty string")
    payload = (
        f"{CHILD_SEED_ALGORITHM_VERSION}|{master_seed}|{scenario}|{run_index}"
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return int(digest[:16], 16) & _SEED_MASK
