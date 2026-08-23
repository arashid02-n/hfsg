"""Manual smoke run for the aggregate Model B engine (Steps 4-5).

Executes a full S1 baseline simulation from config/base.yaml and prints
the checks required by the Phase 1 implementation order:

    configuration loads; simulation initializes; multiple timesteps
    advance; stocks remain valid; flows remain valid; capacity
    constraints work; mass balance passes; validation reports PASS.

Usage:
    python scripts/smoke_aggregate.py [config_path] [scenario_id] [run_index]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from hfsg import (  # noqa: E402
    AggregateEngine,
    ConfigError,
    ConfigurationLoader,
    build_context,
)
from hfsg.units import ACTIVE_UNITS  # noqa: E402

CHECK = "PASS"
FAIL = "FAIL"


def main() -> int:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config/base.yaml"
    scenario_id = sys.argv[2] if len(sys.argv) > 2 else "S1"
    run_index = int(sys.argv[3]) if len(sys.argv) > 3 else 0

    print("=" * 72)
    print("HFSG aggregate smoke run")
    print("=" * 72)

    try:
        config = ConfigurationLoader().load(config_path)
    except ConfigError as exc:
        print(f"configuration load ......... {FAIL}: {exc}")
        return 1
    print(f"configuration load ......... {CHECK} ({config_path})")
    print(
        f"  model={config.name} v{config.version} "
        f"({config.document_status})"
    )

    context = build_context(config, scenario_id=scenario_id, run_index=run_index)
    print(
        f"simulation context .......... scenario={context.scenario_id} "
        f"run={context.run_index}"
    )
    print(f"  master_seed={context.master_seed}")
    print(f"  child_seed ={context.child_seed}")

    engine = AggregateEngine(config, context)
    ic = engine.initial
    print(f"initialization .............. {CHECK}")
    print(
        f"  initial stocks: ED={ic.ed_census:g} C={ic.specialty_census:g} "
        f"G={ic.general_census:g} I={ic.icu_census:g} "
        f"(total={ic.total:g}, N(0) per MODEL.md section 12)"
    )
    print(
        f"  horizon: {engine.total_steps} steps x "
        f"{config.time_step_hours:g}h (dt), capacities="
        f"{ {u: engine.capacities[u] for u in ACTIVE_UNITS} }"
    )

    result = engine.run()
    print(
        f"timestep execution .......... {CHECK} "
        f"({len(result.records)} steps completed)"
    )

    final = result.final
    capacities = engine.capacities
    maxima = {
        unit: max(r.after.stock(unit) for r in result.records)
        for unit in ACTIVE_UNITS
    }
    minima = {
        unit: min(r.after.stock(unit) for r in result.records)
        for unit in ACTIVE_UNITS
    }

    stocks_ok = all(minima[u] >= -1e-9 for u in ACTIVE_UNITS) and all(
        final.stock(u) <= capacities[u] + 1e-6 for u in ACTIVE_UNITS
    )
    print(f"stocks remain valid ......... {CHECK if stocks_ok else FAIL}")
    print("  final: "
          + " ".join(f"{u.upper()}={final.stock(u):.2f}" for u in ACTIVE_UNITS))
    print("  min   : "
          + " ".join(f"{u.upper()}={minima[u]:.2f}" for u in ACTIVE_UNITS))
    print("  max   : "
          + " ".join(
              f"{u.upper()}={maxima[u]:.2f}/{capacities[u]:g}"
              for u in ACTIVE_UNITS
          ))

    flows_ok = True
    for record in result.records:
        before, constrained = record.before, record.flows.constrained
        ed_out = sum(constrained[n] for n in ("T_EC", "T_EG", "T_EI", "T_EH"))
        c_out = sum(constrained[n] for n in ("T_CG", "T_CI", "D_C", "M_C"))
        g_out = sum(constrained[n] for n in ("T_GI", "D_G", "M_G"))
        i_out = sum(constrained[n] for n in ("D_I", "M_I"))
        if (
            ed_out > before.ed_census + 1e-9
            or c_out > before.specialty_census + 1e-9
            or g_out > before.general_census + 1e-9
            or i_out > before.icu_census + 1e-9
            or any(v < 0 for v in constrained.values())
        ):
            flows_ok = False
            break
    print(f"flows remain valid .......... {CHECK if flows_ok else FAIL}")
    totals = {
        "arrivals": sum(r.flows.arrivals_accepted for r in result.records),
        "discharges": sum(r.flows.total_discharges for r in result.records),
        "deaths": sum(r.flows.total_deaths for r in result.records),
    }
    transfers = sum(r.flows.total_transfers for r in result.records)
    print(
        f"  cumulative raw constrained flows: arrivals={totals['arrivals']:g} "
        f"transfers={transfers:.2f} discharges={totals['discharges']:.2f} "
        f"deaths={totals['deaths']:.2f}"
    )

    unmet_totals: dict = {}
    for record in result.records:
        for key, value in record.flows.unmet.items():
            unmet_totals[key] = unmet_totals.get(key, 0.0) + value
    capacity_ok = all(
        maxima[u] <= capacities[u] + 1e-6 for u in ACTIVE_UNITS
    )
    print(f"capacity constraints ........ {CHECK if capacity_ok else FAIL}")
    if unmet_totals:
        detail = ", ".join(f"{k}={v:.2f}" for k, v in sorted(unmet_totals.items()))
    else:
        detail = "none"
    print(f"  unmet demand totals: {detail}")

    mbe = abs(final.total - (result.initial.total + final.cumulative_arrivals))
    tolerance = config.mass_balance_tolerance
    mb_ok = mbe < tolerance
    print(
        f"mass balance ................ {CHECK if mb_ok else FAIL} "
        f"(|MBE|={mbe:.3e} < {tolerance:g})"
    )
    print(
        f"  N_total(final)={final.total:.6f} = N(0)={result.initial.total:g} "
        f"+ arrivals={final.cumulative_arrivals:g}"
    )
    print(
        f"  exits: H(cum discharges)={final.cumulative_discharges:.4f} "
        f"M(cum deaths)={final.cumulative_deaths:.4f}"
    )

    validation = result.validation
    val_ok = validation is not None and validation.passed
    status = CHECK if val_ok else FAIL
    warnings = sum(
        1 for i in validation.issues if i.severity == "warning"
    ) if validation else 0
    print(
        f"validation report ........... {status} "
        f"(critical issues: {len(validation.critical_issues)}, "
        f"warnings: {warnings})"
        if validation
        else "validation report ........... MISSING"
    )

    overall = all([stocks_ok, flows_ok, capacity_ok, mb_ok, val_ok])
    print("=" * 72)
    print(f"SMOKE RUN OVERALL: {'PASS' if overall else 'FAIL'}")
    print("=" * 72)
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
