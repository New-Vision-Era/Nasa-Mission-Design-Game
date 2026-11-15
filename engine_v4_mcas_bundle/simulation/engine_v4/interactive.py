"""Step-by-step missions with player decisions (MCAS), behind the four-function interface.

    evaluate_design(configuration)                          -> feasibility, resources, constraints, risks
    start_run(configuration, seed)                          -> run state (stops at the first decision)
    apply_decision(mission, anomaly_id, decision_id)        -> run state (stops at the next decision)
    build_debrief(mission)                                  -> history, anomalies, objectives, score

A run state is a plain JSON-serialisable dict. It holds the configuration, the scenario parameter
overrides, the seed and the decisions taken, and every call replays the run from those, so a stored
state can be resumed later or in another process. `mission` is either such a state or the id of a
run kept in this process's memory (enough for the MVP; nothing is written to disk here).

`run_simulation()` is unchanged and still flies a whole mission in one call.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional, Union

from .configuration import ConfigError, load_scenario, parse_config
from .data_loader import Catalog, load_catalog
from .engine import (ENGINE_VERSION, LIMITATIONS, build_explanations, evaluate_design as _evaluate,
                     list_assumptions, provenance)
from .mission.mcas import anomaly_catalog, history, state_manager
from .mission.mcas.models import (ACTIVE, AWAITING_DECISION, COMPLETED, NOT_LAUNCHED, PERSISTING, DecisionError,
                                  RunContext)
from .mission.mcas.risk_assessment import assess_risk
from .mission.operations import build_mission
from .mission.scoring import compute_score

MCAS_VERSION = "mcas-mvp-0.1"

_RUNS: dict[str, dict[str, Any]] = {}  # in-memory only


def _context(configuration: Any, scenario_parameters: Optional[dict], seed: int,
             catalog: Optional[Catalog]) -> tuple[RunContext, Catalog]:
    catalog = catalog or load_catalog()
    cfg = parse_config(configuration)
    scenario = load_scenario(cfg.scenario_id, scenario_parameters)
    info = anomaly_catalog.mission_type_info(scenario.mission_type)
    if info is None:
        raise ConfigError([{"code": "invalid_request", "field": "scenario_id",
                            "message": f"Unknown mission type '{scenario.mission_type}'."}])
    if not info["implemented"]:
        raise ConfigError([{"code": "not_implemented", "field": "scenario_id",
                            "message": f"Mission type '{scenario.mission_type}' is not implemented. "
                                       + info["not_implemented_reason"]}])
    sel, evaluation, performance = _evaluate(cfg, scenario.params, catalog)
    return RunContext(cfg=cfg, scenario_id=scenario.id, mission_type=scenario.mission_type, sel=sel,
                      params=scenario.params, evaluation=evaluation, performance=performance, seed=seed), catalog


def evaluate_design(configuration: Any, scenario_parameters: Optional[dict] = None,
                    catalog: Optional[Catalog] = None) -> dict[str, Any]:
    """Engineering evaluation plus the MCAS risk assessment. Nothing is flown."""
    ctx, catalog = _context(configuration, scenario_parameters, 0, catalog)
    ev = ctx.evaluation
    return {
        "engine_version": ENGINE_VERSION, "mcas_version": MCAS_VERSION, "dataset_id": catalog.dataset_id,
        "scenario_id": ctx.scenario_id, "mission_type": ctx.mission_type,
        "configuration": ctx.cfg.model_dump(),
        "feasibility": ev["feasibility"],
        "launchable": ev["feasibility"]["status"] != "INFEASIBLE",
        "resources": ev["resources"],
        "margins": ev["margins"],
        "constraints": [r.to_dict() for r in ev["constraints"]],
        "performance": ctx.performance,
        "risk_assessment": assess_risk(ctx),
    }


def _state(ctx: RunContext, prog: state_manager.Progress, mission_id: str, scenario_parameters: Optional[dict],
           decisions: dict[str, str]) -> dict[str, Any]:
    feas = ctx.evaluation["feasibility"]
    done = prog.status in (COMPLETED, NOT_LAUNCHED)
    if prog.status == NOT_LAUNCHED:
        phase = "launch"
    elif prog.status == COMPLETED:
        phase = "mission_completion"
    else:
        phase = "science_operations"
    elapsed_periods = len(prog.timeline)
    state = {
        "mission_id": mission_id,
        "engine_version": ENGINE_VERSION,
        "mcas_version": MCAS_VERSION,
        "status": prog.status if done or prog.status == AWAITING_DECISION else ACTIVE,
        "mission_type": ctx.mission_type,
        "scenario_id": ctx.scenario_id,
        "seed": ctx.seed,
        "configuration": ctx.cfg.model_dump(),
        "scenario_parameters": scenario_parameters,
        "decisions": dict(decisions),
        "feasibility": feas,
        "conditional_launch": feas["status"] == "CONDITIONAL",
        "current_phase": phase,
        "current_period": prog.period,
        "total_periods": ctx.periods if prog.status != NOT_LAUNCHED else 0,
        "elapsed_days": round(elapsed_periods * ctx.days_per_period, 2) if prog.status != NOT_LAUNCHED else 0.0,
        "resources": state_manager.resources_view(ctx, prog),
        "objectives": {
            "observe_target": {"science_credit_periods": round(prog.science_done, 4),
                               "periods_completed": elapsed_periods},
            "return_data": {"data_generated_bits": state_manager.resources_view(ctx, prog)["data_generated_bits"],
                            "data_downlinked_bits": state_manager.resources_view(ctx, prog)["data_downlinked_bits"]},
        },
        "pending_decision": prog.pending,
        "active_anomalies": ([prog.pending] if prog.pending else [])
                            + [r for r in prog.records if r["status"] == PERSISTING],
        "resolved_anomalies": [r for r in prog.records if r["status"] != PERSISTING],
        "events_not_applicable": prog.not_eligible,
        "decision_history": prog.applied_decisions,
        "mission_history": prog.log,
        "timeline": prog.timeline,
        "outcome": None,
        "score_total": None,
    }
    if prog.status == NOT_LAUNCHED:
        state["mission_history"] = [{"phase": "launch", "period": None,
                                     "message": "Not launched: the design fails hard constraint(s) "
                                                + ", ".join(feas["hard_failed"]) + "."}]
        state["outcome"] = "FAILURE"
    elif prog.status == COMPLETED:
        mission = build_mission(ctx, prog)
        score = compute_score(ctx.sel, ctx.params, ctx.evaluation, ctx.performance, mission)
        state["outcome"], state["score_total"] = mission["outcome"], score["total"]
        state["mission_history"] = prog.log + [{"phase": "mission_completion", "period": None,
                                                "message": mission["explanation"]}]
    return state


def start_run(configuration: Any, seed: int = 0, scenario_parameters: Optional[dict] = None,
              mission_id: Optional[str] = None, catalog: Optional[Catalog] = None) -> dict[str, Any]:
    """Launch and advance to the first decision point, or to the end. An infeasible design is NOT_LAUNCHED."""
    ctx, _ = _context(configuration, scenario_parameters, seed, catalog)
    prog = state_manager.advance(ctx, {})
    state = _state(ctx, prog, mission_id or f"mission_{uuid.uuid4().hex[:12]}", scenario_parameters, {})
    _RUNS[state["mission_id"]] = state
    return state


def get_run(mission_id: str) -> dict[str, Any]:
    if mission_id not in _RUNS:
        raise DecisionError("not_found", f"No run with id '{mission_id}' in memory.")
    return _RUNS[mission_id]


def _load(mission: Union[str, dict]) -> dict[str, Any]:
    if isinstance(mission, dict):
        missing = [k for k in ("mission_id", "configuration", "seed", "decisions", "status") if k not in mission]
        if missing:
            raise DecisionError("invalid_state", f"Run state is missing: {', '.join(missing)}.")
        return mission
    return get_run(mission)


def apply_decision(mission: Union[str, dict], anomaly_id: str, decision_id: str,
                   catalog: Optional[Catalog] = None) -> dict[str, Any]:
    """Answer the pending anomaly and advance to the next decision point, or to the end.

    Raises DecisionError: no_pending_decision, wrong_anomaly, unknown_response, response_unavailable.
    """
    state = _load(mission)
    ctx, _ = _context(state["configuration"], state.get("scenario_parameters"), state["seed"], catalog)
    current = state_manager.advance(ctx, state["decisions"])  # replay: never trust a stored pending record
    if current.pending is None:
        raise DecisionError("no_pending_decision", "This run is not waiting for a decision.")
    if anomaly_id != current.pending["anomaly_id"]:
        raise DecisionError("wrong_anomaly", f"The run is waiting for a decision on "
                                             f"'{current.pending['anomaly_id']}', not '{anomaly_id}'.")
    decisions = {**state["decisions"], anomaly_id: decision_id}
    prog = state_manager.advance(ctx, decisions)  # validates the response
    new_state = _state(ctx, prog, state["mission_id"], state.get("scenario_parameters"), decisions)
    _RUNS[new_state["mission_id"]] = new_state
    return new_state


def build_debrief(mission: Union[str, dict], catalog: Optional[Catalog] = None) -> dict[str, Any]:
    """Mission history, anomaly history, objectives, outcome and score for a finished run."""
    state = _load(mission)
    ctx, catalog = _context(state["configuration"], state.get("scenario_parameters"), state["seed"], catalog)
    prog = state_manager.advance(ctx, state["decisions"])
    if prog.status == AWAITING_DECISION:
        raise DecisionError("decision_pending", f"The mission is not finished: a decision on "
                                                f"'{prog.pending['anomaly_id']}' is pending.")
    mission_result = build_mission(ctx, prog)
    score = compute_score(ctx.sel, ctx.params, ctx.evaluation, ctx.performance, mission_result)
    risk = assess_risk(ctx)

    # same design with no external event and no anomaly consequence, to show what the anomalies cost
    reference = None
    if prog.status == COMPLETED:
        quiet = ctx.params.model_copy(update={"events": ctx.params.events.model_copy(update={"enabled": False})})
        ref_ctx = RunContext(ctx.cfg, ctx.scenario_id, ctx.mission_type, ctx.sel, quiet, ctx.evaluation,
                             ctx.performance, ctx.seed)
        ref_mission = build_mission(ref_ctx, state_manager.advance(ref_ctx, {}, scope=(), interactive=False))
        ref_score = compute_score(ctx.sel, ctx.params, ctx.evaluation, ctx.performance, ref_mission)
        reference = {
            "outcome": ref_mission["outcome"], "objective_fraction": ref_mission["objective_fraction"],
            "score_total": ref_score["total"],
            "score_difference": (None if score["total"] is None or ref_score["total"] is None
                                 else round(score["total"] - ref_score["total"], 2)),
            "note": "The same design flown with no external event and no anomaly consequence. The difference "
                    "is what the anomalies and the responses to them cost. No points are subtracted per "
                    "anomaly: the score changes only through what the mission actually achieved.",
        }

    records = prog.records
    periods = ctx.periods if prog.status == COMPLETED else 0
    return {
        "mission_id": state["mission_id"],
        "engine_version": ENGINE_VERSION, "mcas_version": MCAS_VERSION, "dataset_id": catalog.dataset_id,
        "scenario_id": ctx.scenario_id, "mission_type": ctx.mission_type, "seed": ctx.seed,
        "configuration": ctx.cfg.model_dump(),
        "status": prog.status,
        "feasibility": ctx.evaluation["feasibility"],
        "outcome": mission_result["outcome"],
        "objectives": mission_result["objectives"],
        "score": score,
        "reference_without_anomalies": reference,
        "operational_availability": {
            "science_fraction": round(prog.science_done / periods, 4) if periods else None,
            "included_in_score": False,
            "note": "Reported for information. It is not a reliability factor in the score; adding it needs "
                    "team approval.",
        },
        "risk_assessment": risk,
        "anomalies": records,
        "anomaly_summaries": [history.sentence(r) for r in records],
        "events_not_applicable": prog.not_eligible,
        "decisions": prog.applied_decisions,
        "debrief": history.debrief_groups(records, risk),
        "mission_history": state.get("mission_history", prog.log),
        "mission": mission_result,
        "explanations": build_explanations(ctx.evaluation, ctx.performance, mission_result, score),
        "assumptions": list_assumptions(ctx.params, ctx.sel) + [
            {"id": f"mcas.{name}", "value": spec["value"], "value_kind": spec["value_kind"], "note": spec["meaning"]}
            for name, spec in anomaly_catalog.GAMEPLAY_PARAMETERS.items()],
        "limitations": LIMITATIONS + [
            "MCAS is a simplified educational model of anomalies and responses, not a reliability simulation.",
            "Battery state of charge and propellant are not tracked over time; those resources stay null.",
            "Response deadlines are not modelled: the mission waits for the player.",
        ],
        "provenance": provenance(ctx.sel, catalog),
    }
