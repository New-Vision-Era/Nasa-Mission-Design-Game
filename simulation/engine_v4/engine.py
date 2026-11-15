"""Entry point: configuration in, explainable result out.

    from simulation.engine_v4 import run_simulation
    result = run_simulation(config_dict, scenario_parameters=None, seed=0)

Independent of the frontend and of FastAPI. Deterministic for a given input and seed.
"""
from __future__ import annotations

import copy
from typing import Any, Optional

from .configuration import (MissionConfig, ScenarioParams, Selection, load_scenario, parse_config,
                            resolve_selection)
from .data_loader import Catalog, load_catalog
from .evaluation import evaluate_engineering
from .mission.operations import simulate_mission
from .mission.performance import science_performance
from .mission.scoring import compute_score
from .results import FAIL, HARD, NOT_EVALUATED, WARNING

ENGINE_VERSION = "engine_v4-mvp-0.2"

# Caveat fields shown in the debrief when a record has them (platforms since equipment_v5).
PROVENANCE_EXTRA_FIELDS = ("bus_mass_kg", "bus_mass_basis", "bus_mass_range_kg", "bus_mass_method",
                           "bus_mass_sources", "bus_mass_note", "price_note", "ownership_note")

LIMITATIONS = [
    "Simplified MVP model for a game, not a high-fidelity engineering simulation.",
    "Platform bus mass is not a manufacturer value: an estimate for GSAT-20 and GSAT-50, derived with an "
    "inference for GSAT-200. It is dry, so propellant carried by the bus is not counted. Results that depend "
    "on it (launch mass, rideshare price, delta-v) report its range.",
    "Whether GSAT platforms include their own power, radio and ADCS hardware is unknown; the power mode "
    "is an explicit modelling choice.",
    "Science performance uses transparent rules, not information gain: there is no measurement or noise model.",
    "Instrument data rates are mostly unpublished; data balance is evaluated only when rates are available.",
    "Orbit values are derived (circular orbit, spherical Earth). Orbital lifetime is not modelled.",
    "Combined volume fit is a conservative approximation, not geometric packing.",
    "Delta-v uses the impulse approximation, not the rocket equation.",
    "Most component prices are unpublished; the budget covers platform and launch only.",
    "Event probabilities and effects, duty cycles, pass counts and score weights are gameplay assumptions.",
]


def evaluate_design(config: MissionConfig, params: ScenarioParams, catalog: Catalog) -> tuple[Selection, dict, dict]:
    """Engineering evaluation plus science rules, without the mission run. Used by the optimizer too."""
    sel = resolve_selection(config, catalog)
    evaluation = evaluate_engineering(sel, params)
    performance = science_performance(sel, params, evaluation["instruments_at_orbit"])
    return sel, evaluation, performance


def run_simulation(config: Any, scenario_parameters: Optional[dict] = None, seed: int = 0,
                   catalog: Optional[Catalog] = None, scenario_dir=None) -> dict[str, Any]:
    """Validate, evaluate, simulate, score and explain one mission configuration.

    Raises ConfigError for an invalid request or selection, CatalogError for a broken dataset.
    """
    catalog = catalog or load_catalog()
    cfg = parse_config(config)
    scenario = load_scenario(cfg.scenario_id, scenario_parameters, scenario_dir)
    params = scenario.params
    sel, evaluation, performance = evaluate_design(cfg, params, catalog)
    mission = simulate_mission(sel, params, evaluation, performance, seed)
    score = compute_score(sel, params, evaluation, performance, mission)

    return {
        "engine_version": ENGINE_VERSION,
        "dataset_id": catalog.dataset_id,
        "seed": seed,
        "scenario": {"id": scenario.id, "name": scenario.name, "briefing": scenario.briefing},
        "configuration": cfg.model_dump(),
        "feasibility": evaluation["feasibility"],
        "resources": evaluation["resources"],
        "margins": evaluation["margins"],
        "constraints": [r.to_dict() for r in evaluation["constraints"]],
        "orbit": evaluation["orbit"],
        "instruments_at_orbit": evaluation["instruments_at_orbit"],
        "power": evaluation["power"],
        "propulsion": evaluation["propulsion"],
        "performance": performance,
        "score": score,
        "mission": mission,
        "explanations": build_explanations(evaluation, performance, mission, score),
        "assumptions": list_assumptions(params, sel),
        "limitations": LIMITATIONS,
        "provenance": provenance(sel, catalog),
    }


def build_explanations(evaluation: dict, performance: dict, mission: dict, score: dict) -> list[dict]:
    """Debrief findings: what failed, what is unknown, what to watch, what went well."""
    out = []
    for r in evaluation["constraints"]:
        if r.status == FAIL:
            kind = "problem" if r.severity == HARD else "weakness"
        elif r.status == NOT_EVALUATED:
            kind = "unknown"
        elif r.status == WARNING:
            kind = "warning"
        else:
            continue
        out.append({"kind": kind, "severity": r.severity, "constraint_id": r.id, "related_step": r.related_step,
                    "message": f"{r.title}: {r.message}"})
    for rule in performance["rules"]:
        if rule["evaluable"] and rule["score"] < 1.0:
            out.append({"kind": "weakness", "severity": "soft", "constraint_id": f"science.{rule['id']}",
                        "related_step": "orbit" if rule["id"] == "orbit_choice" else "instruments",
                        "message": f"{rule['title']}: {rule['reason']}"})
    margins = evaluation["margins"]
    for key, label, step in (("mass_margin_fraction", "payload mass", "instruments"),
                             ("power_margin_fraction", "power", "power")):
        m = margins[key]
        if m is not None and 0 <= m < 0.1:
            out.append({"kind": "warning", "severity": "soft", "constraint_id": key, "related_step": step,
                        "message": f"Only {m * 100:.0f}% {label} margin remains: this is the limiting resource."})
    if not any(e["kind"] in ("problem", "weakness") for e in out):
        out.append({"kind": "strength", "severity": "soft", "constraint_id": None, "related_step": None,
                    "message": "No evaluated constraint failed and every evaluable science rule is met."})
    out.append({"kind": "outcome", "severity": "soft", "constraint_id": None, "related_step": None,
                "message": mission["explanation"]})
    if score["completeness"] < 1.0:
        out.append({"kind": "unknown", "severity": "soft", "constraint_id": None, "related_step": None,
                    "message": f"Only {score['completeness'] * 100:.0f}% of the score weight could be evaluated "
                               "from available data."})
    return out


def list_assumptions(params: ScenarioParams, sel: Selection) -> list[dict]:
    """Every scenario parameter, labelled. None of them is a published real-world value."""
    out = [{"id": f"scenario.{name}", "value": value, "value_kind": "gameplay_assumption"}
           for name, value in params.model_dump().items()]
    out.append({"id": "power_mode", "value": sel.power_mode, "value_kind": "gameplay_assumption",
                "note": "Whether the platform includes its own power hardware is unknown in the dataset."})
    return out


def provenance(sel: Selection, catalog: Catalog) -> dict:
    """Sources and caveats of every selected component, for the debrief."""
    comps = {}
    for rec in sel.all_records():
        entry = {"name": rec.get("name"), "source_urls": list(rec.get("source_urls") or []),
                 "value_notes": rec.get("value_notes"),
                 "price_type": rec.get("price_type"), "value_kind": rec.get("value_kind")}
        for key in PROVENANCE_EXTRA_FIELDS:
            if rec.get(key) is not None:
                entry[key] = copy.deepcopy(rec[key])
        comps[rec["id"]] = entry
    return {"dataset_id": catalog.dataset_id, "value_kinds": catalog.value_kinds, "components": comps}
