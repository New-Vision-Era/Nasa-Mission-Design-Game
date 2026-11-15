"""Recommend alternative designs: bounded candidate set, early rejection, Pareto filter.

Deliberately not exhaustive: 21 instruments alone give millions of subsets.
Candidates vary the platform, one science instrument, a few ADCS and radio
kits, and launcher/orbit pairs the dataset lists as supported. No optimisation
library is used. Unknown values never count as good: an unknown cost or margin
is treated as worse than any known value when comparing designs.
"""
from __future__ import annotations

from typing import Any, Optional

from ..configuration import MissionConfig, ScenarioParams, load_scenario
from ..constraints.mass import component_mass_kg
from ..constraints.volume import fits_envelope
from ..data_loader import Catalog, load_catalog
from ..engine import evaluate_design
from ..mission.scoring import reliability_category
from ..results import INFEASIBLE

OBJECTIVES = ("science", "reliability", "known_cost_usd", "mass_margin", "power_margin")
MINIMISE = {"known_cost_usd"}


def dominates(a: dict, b: dict) -> bool:
    """a is no worse than b on every objective and strictly better on one. None is worst."""
    better = False
    for key in OBJECTIVES:
        va, vb = a["objectives"][key], b["objectives"][key]
        if va is None and vb is None:
            continue
        if va is None:
            return False
        if vb is None:
            better = True
            continue
        if key in MINIMISE:
            va, vb = -va, -vb
        if va < vb:
            return False
        if va > vb:
            better = True
    return better


def pareto_front(candidates: list[dict]) -> list[dict]:
    return [c for c in candidates if not any(dominates(o, c) for o in candidates if o is not c)]


def _adcs_options(catalog: Catalog) -> list[str]:
    """Up to three accuracy classes (coarsest, middle, finest), the lightest known unit in each."""
    best: dict[float, dict] = {}
    for a in catalog.all("adcs_systems"):
        acc, m = a.get("pointing_accuracy_deg"), a.get("mass_kg")
        if acc is None or m is None:
            continue
        if acc not in best or m < best[acc]["mass_kg"]:
            best[acc] = a
    ordered = [a["id"] for _, a in sorted(best.items(), reverse=True)]
    if len(ordered) <= 3:
        return ordered
    return [ordered[0], ordered[len(ordered) // 2], ordered[-1]]  # coarsest, middle, finest


def _comm_kits(catalog: Catalog, params: ScenarioParams) -> list[list[str]]:
    """Each command-capable radio alone, and paired with each transmit-only downlink radio."""
    usable = [r for r in catalog.all("communication_systems")
              if r.get("ground_station_type") in params.ground_station_types]
    ttc = [r["id"] for r in usable if r.get("can_receive_commands") is True]
    tx = [r["id"] for r in usable if r.get("can_receive_commands") is False and r.get("mass_kg") is not None]
    kits = [[t] for t in ttc]
    kits += [[t, x] for t in ttc[:1] for x in tx]
    return kits


def generate_candidates(base: MissionConfig, params: ScenarioParams, catalog: Catalog,
                        limit: int = 20000) -> list[MissionConfig]:
    families = params.science.required_instrument_families_any
    instruments = [i for i in catalog.all("instruments") if not families or i.get("family") in families]
    pairs = [(lv["id"], oid) for lv in catalog.all("launch_vehicles")
             for oid in lv.get("orbit_ids_supported") or [] if catalog.get("orbits", oid)]
    out: list[MissionConfig] = []
    for platform in catalog.all("platforms"):
        cap, env = platform.get("payload_mass_capacity_kg"), platform.get("payload_volume_mm")
        for inst in instruments:
            m = component_mass_kg("instruments", inst)
            # early rejection on definite failures only; unknowns are kept and reported later
            if m is not None and cap is not None and m > cap:
                continue
            if fits_envelope(inst.get("dimensions_mm"), env) is False:
                continue
            for adcs_id in _adcs_options(catalog):
                for kit in _comm_kits(catalog, params):
                    for lv_id, orbit_id in pairs:
                        out.append(base.model_copy(update={
                            "platform_id": platform["id"], "instrument_ids": [inst["id"]],
                            "adcs_system_id": adcs_id, "communication_system_ids": kit,
                            "orbit_id": orbit_id, "launch_vehicle_id": lv_id}))
                        if len(out) >= limit:
                            return out
    return out


def _summarise(cfg: MissionConfig, sel, evaluation: dict, performance: dict, params: ScenarioParams) -> dict:
    rel = reliability_category(sel, evaluation, params, 1.0)
    return {
        "configuration": cfg.model_dump(),
        "feasibility": evaluation["feasibility"]["status"],
        "hard_not_evaluated": evaluation["feasibility"]["hard_not_evaluated"],
        "objectives": {
            "science": performance["score"],
            "reliability": rel["score_fraction"],
            "known_cost_usd": evaluation["cost"]["known_cost_usd"],
            "mass_margin": evaluation["margins"]["mass_margin_fraction"],
            "power_margin": evaluation["margins"]["power_margin_fraction"],
        },
    }


def recommend(config: Any, scenario_parameters: Optional[dict] = None, catalog: Optional[Catalog] = None,
              max_results: int = 5, scenario_dir=None) -> dict:
    """Return a few non-dominated alternatives with different trade-offs."""
    catalog = catalog or load_catalog()
    base = config if isinstance(config, MissionConfig) else MissionConfig.model_validate(config)
    params = load_scenario(base.scenario_id, scenario_parameters, scenario_dir).params
    generated = generate_candidates(base, params, catalog)
    kept = []
    for cfg in generated:
        sel, evaluation, performance = evaluate_design(cfg, params, catalog)
        if evaluation["feasibility"]["status"] == INFEASIBLE or not performance["has_required_instrument"]:
            continue
        kept.append(_summarise(cfg, sel, evaluation, performance, params))
    front = pareto_front(kept)
    picks = _diverse(front, max_results)
    return {
        "method": "bounded candidate enumeration + Pareto filter (no weights)",
        "objectives": {k: ("minimise" if k in MINIMISE else "maximise") for k in OBJECTIVES},
        "candidates_generated": len(generated),
        "candidates_not_infeasible": len(kept),
        "pareto_front_size": len(front),
        "alternatives": picks,
        "notes": ["Not exhaustive: one science instrument per candidate and a reduced set of subsystem kits.",
                  "Unknown cost or margin is treated as worse than any known value, never as zero.",
                  "CONDITIONAL designs still have hard constraints that real data cannot confirm."],
    }


def _diverse(front: list[dict], n: int) -> list[dict]:
    """Best design per objective first, then fill by science score."""
    picks: list[dict] = []
    labels = {"science": "Best science", "reliability": "Most reliable", "known_cost_usd": "Lowest known cost",
              "mass_margin": "Largest mass margin", "power_margin": "Largest power margin"}

    def key(c, k):
        v = c["objectives"][k]
        if v is None:
            return float("-inf")
        return -v if k in MINIMISE else v

    order = lambda c: tuple(sorted(str(x) for x in c["configuration"].items()))
    for k in OBJECTIVES:
        taken = [p["configuration"] for p in picks]
        pool = [c for c in front if c["objectives"][k] is not None and c["configuration"] not in taken]
        if not pool or len(picks) >= n:
            continue
        best = max(sorted(pool, key=order), key=lambda c: key(c, k))
        picks.append({**best, "label": labels[k]})
    for c in sorted(sorted(front, key=order), key=lambda c: key(c, "science"), reverse=True):
        if len(picks) >= n:
            break
        if not any(p["configuration"] == c["configuration"] for p in picks):
            picks.append({**c, "label": "Alternative trade-off"})
    return picks
