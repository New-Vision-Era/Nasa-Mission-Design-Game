"""Simple staged mission simulation.

Deterministic. No random failures are generated for drama: the only randomness
is the optional seeded event list. Onboard storage is not capped (it is unknown
for most instruments), so undelivered data simply accumulates as backlog.
"""
from __future__ import annotations

from typing import Any, Optional

from ..configuration import ScenarioParams, Selection
from ..results import CONDITIONAL, INFEASIBLE
from .events import generate_events, resolve_event

SUCCESS, PARTIAL_SUCCESS, FAILURE = "SUCCESS", "PARTIAL_SUCCESS", "FAILURE"


def simulate_mission(sel: Selection, params: ScenarioParams, evaluation: dict, performance: dict,
                     seed: int) -> dict[str, Any]:
    feas = evaluation["feasibility"]
    if feas["status"] == INFEASIBLE:
        return _not_launched(feas)

    relevant = set(performance["relevant_instrument_ids"])
    periods = params.science_periods
    days_per_period = params.mission_duration_days / periods
    generated_day = evaluation["data"]["generated_bits_per_day"]
    capacity_day = evaluation["downlink"]["bits_per_day"]
    radio = next((r for r in sel.comms if r["id"] == evaluation["downlink"]["radio_id"]), None)
    generation_w = (evaluation["power"].get("generation") or {}).get("value_w")
    demand_w = evaluation["power"]["demand"]["known_avg_w"]

    resolved = [resolve_event(e, sel, params, radio, generation_w, demand_w)
                for e in generate_events(sel, params, seed)]
    by_period: dict[int, list[dict]] = {}
    for e in resolved:
        by_period.setdefault(e["period"], []).append(e)

    science_done, backlog, generated_total, downlinked_total = 0, 0.0, 0.0, 0.0
    timeline = []
    for period in range(1, periods + 1):
        effects = [e["effect"] for e in by_period.get(period, []) if e["effect"]["applies"]]
        off = {e["instrument_off"] for e in effects if e["instrument_off"]}
        science_lost = any(e["science_lost"] for e in effects)
        downlink_lost = any(e["downlink_lost"] for e in effects)
        observing = bool(relevant - off) and not science_lost
        science_done += 1 if observing else 0
        produced = sent = None
        if generated_day is not None:
            active_share = 0.0 if science_lost else _active_share(sel, off)
            produced = generated_day * days_per_period * active_share
            generated_total += produced
            backlog += produced
            if capacity_day is not None:
                sent = 0.0 if downlink_lost else min(backlog, capacity_day * days_per_period)
                backlog -= sent
                downlinked_total += sent
        timeline.append({"period": period, "elapsed_days": round(period * days_per_period, 2),
                         "science_observed": observing, "data_generated_bits": produced,
                         "data_downlinked_bits": sent, "backlog_bits": backlog if produced is not None else None,
                         "event_types": [e["type"] for e in by_period.get(period, [])]})

    observe_fraction = science_done / periods if performance["has_required_instrument"] else 0.0
    if generated_day is None or capacity_day is None:
        return_fraction = None
        return_msg = ("Data return is not evaluated: instrument data rates or downlink capacity are unknown "
                      "and no rate was invented.")
    elif generated_total <= 0:
        return_fraction, return_msg = 0.0, "No science data was generated."
    else:
        return_fraction = min(1.0, downlinked_total / generated_total)
        return_msg = (f"{downlinked_total / 8e9:.1f} GB of {generated_total / 8e9:.1f} GB generated was "
                      f"downlinked ({return_fraction * 100:.0f}%).")
    objectives = [
        {"id": "observe_target", "title": "Observe with a suitable instrument",
         "achieved_fraction": round(observe_fraction, 4),
         "message": (f"A suitable instrument observed in {science_done} of {periods} operation periods."
                     if performance["has_required_instrument"] else
                     "No instrument of a required family was on board, so the observation objective was not met.")},
        {"id": "return_data", "title": "Return the science data to Earth",
         "achieved_fraction": None if return_fraction is None else round(return_fraction, 4),
         "message": return_msg},
    ]
    evaluable = [o["achieved_fraction"] for o in objectives if o["achieved_fraction"] is not None]
    objective_fraction = sum(evaluable) / len(evaluable) if evaluable else None

    if not performance["has_required_instrument"] or objective_fraction is None:
        outcome = FAILURE
    elif objective_fraction >= params.success_threshold:
        outcome = SUCCESS
    elif objective_fraction >= params.partial_threshold:
        outcome = PARTIAL_SUCCESS
    else:
        outcome = FAILURE

    conditional = feas["status"] == CONDITIONAL
    stages = [
        _stage("launch", "Launch", f"Launched on {sel.launcher['name']} to {sel.orbit['name']}."
               + (" Launch-mass compatibility could not be fully verified from real data." if conditional else "")),
        _stage("deployment", "Deployment", "Spacecraft separated and deployed. Deployment failures are not "
                                           "simulated; deployable arrays lower the reliability score instead."),
        _stage("commissioning", "Commissioning",
               f"Subsystems checked out. ADCS: {sel.adcs['name']}. Radios: "
               + (", ".join(c["name"] for c in sel.comms) or "none") + "."),
        _stage("science_operations", "Science operations",
               f"{science_done} of {periods} operation periods produced observations."),
        _stage("data_downlink", "Data downlink", return_msg),
        _stage("mission_completion", "Mission completion",
               f"Mission ended after {params.mission_duration_days:g} days with outcome {outcome}."),
    ]
    return {
        "launched": True,
        "conditional_launch": conditional,
        "outcome": outcome,
        "objective_fraction": None if objective_fraction is None else round(objective_fraction, 4),
        "objectives": objectives,
        "stages": stages,
        "events": resolved,
        "timeline": timeline,
        "totals": {"science_periods_completed": science_done, "science_periods": periods,
                   "data_generated_bits": generated_total if generated_day is not None else None,
                   "data_downlinked_bits": downlinked_total if (generated_day is not None
                                                                and capacity_day is not None) else None,
                   "backlog_bits": backlog if generated_day is not None else None},
        "explanation": _explain(outcome, objectives, conditional, feas),
    }


def _active_share(sel: Selection, off: set) -> float:
    """Share of instruments still producing data this period."""
    if not sel.instruments:
        return 0.0
    return sum(1 for i in sel.instruments if i["id"] not in off) / len(sel.instruments)


def _stage(stage_id: str, title: str, message: str, status: str = "completed") -> dict:
    return {"id": stage_id, "title": title, "status": status, "message": message}


def _not_launched(feas: dict) -> dict:
    msg = ("The design fails hard constraint(s): " + ", ".join(feas["hard_failed"])
           + ". It cannot launch, so no mission was flown.")
    names = ["launch", "deployment", "commissioning", "science_operations", "data_downlink", "mission_completion"]
    return {
        "launched": False, "conditional_launch": False, "outcome": FAILURE, "objective_fraction": 0.0,
        "objectives": [
            {"id": "observe_target", "title": "Observe with a suitable instrument", "achieved_fraction": 0.0,
             "message": "Not flown."},
            {"id": "return_data", "title": "Return the science data to Earth", "achieved_fraction": 0.0,
             "message": "Not flown."}],
        "stages": [_stage(n, n.replace("_", " ").capitalize(), msg if n == "launch" else "Not reached.",
                          "blocked" if n == "launch" else "not_reached") for n in names],
        "events": [], "timeline": [],
        "totals": {"science_periods_completed": 0, "science_periods": 0, "data_generated_bits": None,
                   "data_downlinked_bits": None, "backlog_bits": None},
        "explanation": msg,
    }


def _explain(outcome: str, objectives: list[dict], conditional: bool, feas: dict) -> str:
    parts = [f"Outcome: {outcome}."] + [o["message"] for o in objectives]
    if conditional:
        parts.append("This result is conditional: " + ", ".join(feas["hard_not_evaluated"])
                     + " could not be evaluated from real data and are assumed to hold for the simulation.")
    return " ".join(parts)
