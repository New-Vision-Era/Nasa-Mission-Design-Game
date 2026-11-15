"""Simple staged mission simulation.

Deterministic. No random failures are generated for drama: the only randomness
is the optional seeded event list. Onboard storage is not capped (it is unknown
for most instruments), so undelivered data simply accumulates as backlog.
"""
from __future__ import annotations

from typing import Any, Optional

from ..configuration import ScenarioParams, Selection
from ..results import CONDITIONAL
from .events import resolve_event
from .mcas import anomaly_catalog, state_manager
from .mcas.models import NOT_LAUNCHED, RunContext

SUCCESS, PARTIAL_SUCCESS, FAILURE = "SUCCESS", "PARTIAL_SUCCESS", "FAILURE"


def simulate_mission(sel: Selection, params: ScenarioParams, evaluation: dict, performance: dict,
                     seed: int) -> dict[str, Any]:
    """Whole mission in one call, with MCAS MVP scope and default player responses.

    The quick and interactive modes use the same anomaly catalogue and period arithmetic.
    This mode resolves every decision using its declared default response, so a quick run
    and an interactive run in which the player always chooses the default remain comparable.
    """
    ctx = RunContext(cfg=None, scenario_id="", mission_type=anomaly_catalog.EARTH_OBSERVATION, sel=sel,
                     params=params, evaluation=evaluation, performance=performance, seed=seed)
    progress = state_manager.advance(ctx, scope=anomaly_catalog.SCOPE_MVP, interactive=False)
    return build_mission(ctx, progress, legacy_shape=False)


def _count(value: float):
    """Whole numbers print and serialise as integers, as before; fractions keep two decimals."""
    return int(round(value)) if abs(value - round(value)) < 1e-9 else round(value, 2)


def build_mission(ctx: RunContext, progress: "state_manager.Progress", legacy_shape: bool = False) -> dict[str, Any]:
    """Mission result (objectives, outcome, stages, timeline, totals) from a finished MCAS run.

    legacy_shape=True returns exactly the keys of the original v4 result. Otherwise the result also
    carries the anomaly records and the per-period science credit.
    """
    sel, params, evaluation, performance = ctx.sel, ctx.params, ctx.evaluation, ctx.performance
    feas = evaluation["feasibility"]
    if progress.status == NOT_LAUNCHED:
        return _not_launched(feas, progress.launch)
    launch = progress.launch

    periods = params.science_periods
    generated_day, capacity_day = ctx.generated_day, ctx.capacity_day
    science_done = _count(progress.science_done)
    backlog, generated_total, downlinked_total = progress.backlog, progress.generated_total, progress.downlinked_total

    resolved = [resolve_event(e, sel, params, ctx.radio, ctx.generation_w, ctx.demand_w) for e in progress.events]
    timeline = progress.timeline
    if legacy_shape:
        keep = ("period", "elapsed_days", "science_observed", "data_generated_bits", "data_downlinked_bits",
                "backlog_bits", "event_types")
        timeline = [{k: row[k] for k in keep} for row in timeline]
    else:
        by_event = {(r["period"], r["definition_id"], r["facts"].get("instrument_id")): r
                    for r in progress.records}
        source = {d.trigger.get("source_event"): d.id for d in anomaly_catalog.CATALOG.values()}
        for e in resolved:
            rec = by_event.get((e["period"], source.get(e["type"]), e.get("instrument_id"))) \
                or by_event.get((e["period"], source.get(e["type"]), None))
            if rec is not None:
                e["anomaly_id"], e["response_id"] = rec["anomaly_id"], rec.get("response_id")
                e["explanation"] = rec["outcome"]

    observe_fraction = progress.science_done / periods if performance["has_required_instrument"] else 0.0
    equivalent = "" if isinstance(science_done, int) else "the equivalent of "
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
         "message": (f"A suitable instrument observed in {equivalent}{science_done} of {periods} operation periods."
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
    if launch is not None and launch["total_loss"]:
        outcome = FAILURE
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
    if launch is not None:
        stages = _risky_stages(stages, launch, len(progress.timeline), periods)
    mission = {
        "launched": True,
        "launch": launch,
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
        "explanation": _explain(outcome, objectives, conditional, feas, launch),
    }
    if not legacy_shape:
        mission["anomalies"] = progress.records
        mission["events_not_applicable"] = progress.not_eligible
    return mission


def _stage(stage_id: str, title: str, message: str, status: str = "completed") -> dict:
    return {"id": stage_id, "title": title, "status": status, "message": message}


def _risky_stages(stages: list[dict], launch: dict, flown: int, periods: int) -> list[dict]:
    """Rewrite stage statuses for a risky launch: where it was lost, or what it cost."""
    loss = launch["total_loss"]
    order = ["launch", "deployment", "commissioning", "science_operations", "data_downlink", "mission_completion"]
    lost_index = {"launch": 0, "orbit_insertion": 1, "commissioning": 2}.get(loss["stage"]) if loss else None
    out = []
    for i, st in enumerate(stages):
        if lost_index is not None and i == lost_index:
            st = {**st, "status": "failed", "message": loss["reason"]}
        elif lost_index is not None and i > lost_index:
            st = {**st, "status": "not_reached", "message": "Not reached: the spacecraft was lost."}
        elif st["id"] == "launch":
            st = {**st, "status": "degraded", "message": st["message"] + " Risky launch: "
                  + " ".join(r["consequence"] for r in launch["risks"])}
        elif st["id"] == "science_operations" and flown < periods:
            st = {**st, "status": "degraded", "message": st["message"] + f" Re-entered after {flown} periods."}
        out.append(st)
    return out


def _not_launched(feas: dict, launch: Optional[dict] = None) -> dict:
    if launch and launch.get("blocking"):
        msg = ("Launch refused: " + " ".join(b["reason"] for b in launch["blocking"]))
    else:
        msg = ("The design fails hard constraint(s): " + ", ".join(feas["hard_failed"])
               + ". It cannot launch, so no mission was flown.")
    names = ["launch", "deployment", "commissioning", "science_operations", "data_downlink", "mission_completion"]
    return {
        "launched": False, "launch": launch, "conditional_launch": False, "outcome": FAILURE,
        "objective_fraction": 0.0,
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


def _explain(outcome: str, objectives: list[dict], conditional: bool, feas: dict,
             launch: Optional[dict] = None) -> str:
    parts = [f"Outcome: {outcome}."]
    if launch is not None and launch["total_loss"]:
        parts.append(f"The spacecraft was lost during {launch['total_loss']['stage'].replace('_', ' ')}: "
                     + launch["total_loss"]["reason"])
    elif launch is not None:
        parts.append("Risky launch: " + " ".join(r["consequence"] for r in launch["risks"]))
    parts += [o["message"] for o in objectives]
    if conditional:
        parts.append("This result is conditional: " + ", ".join(feas["hard_not_evaluated"])
                     + " could not be evaluated from real data and are assumed to hold for the simulation.")
    return " ".join(parts)
