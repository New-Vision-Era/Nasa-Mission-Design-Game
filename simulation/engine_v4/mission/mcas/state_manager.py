"""Mission state: advance period by period until a player decision is needed or the mission ends.

A run is a pure function of (configuration, scenario parameters, seed, decisions so far). Nothing
else is remembered, so the same inputs always replay to the same state, and the state that is stored
is small and JSON-serialisable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ...results import INFEASIBLE
from . import anomaly_catalog, anomaly_generator, anomaly_resolver, decision_manager, history, launch_risk, trigger_engine
from .models import (AWAITING_DECISION, COMPLETED, NOT_LAUNCHED, DecisionError, Modifiers, RunContext)


@dataclass
class Progress:
    status: str
    period: int = 0                                   # last period started
    timeline: list[dict] = field(default_factory=list)
    records: list[dict] = field(default_factory=list)       # anomalies and absorbed events
    not_eligible: list[dict] = field(default_factory=list)  # events this design cannot be affected by
    events: list[dict] = field(default_factory=list)        # raw seeded events
    pending: Optional[dict] = None
    log: list[dict] = field(default_factory=list)
    backlog: float = 0.0
    science_done: float = 0.0
    generated_total: float = 0.0
    downlinked_total: float = 0.0
    applied_decisions: list[dict] = field(default_factory=list)
    launch: Optional[dict] = None                     # launch_risk.assess() for a risky launch


def advance(ctx: RunContext, decisions: Optional[dict[str, str]] = None,
            scope: tuple[str, ...] = anomaly_catalog.SCOPE_MVP, interactive: bool = True,
            risky_launch: bool = False) -> Progress:
    """Run from launch with the given decisions ({anomaly_id: response_id}).

    interactive=True stops at the first anomaly that offers the player a real choice and has no decision
    yet. interactive=False applies each anomaly's default response and runs to the end.
    risky_launch=True lets an INFEASIBLE design fly unless launch_risk finds it catastrophic; its failed
    hard checks then become launch consequences. Without it, as before, INFEASIBLE means NOT_LAUNCHED.
    Raises DecisionError for a decision that names an unavailable or unknown response.
    """
    decisions = decisions or {}
    launch = None
    if ctx.evaluation["feasibility"]["status"] == INFEASIBLE:
        if not risky_launch:
            return Progress(status=NOT_LAUNCHED)
        launch = launch_risk.assess(ctx.evaluation, ctx.sel, ctx.params, (ctx.radio or {}).get("id"))
        if launch["status"] == launch_risk.NO_GO:
            return Progress(status=NOT_LAUNCHED, launch=launch)

    definitions = anomaly_catalog.definitions_for(ctx.mission_type, scope)
    prog = Progress(status=COMPLETED, events=anomaly_generator.external_events(ctx), launch=launch)
    standing: list[Modifiers] = []
    operating = ctx.periods
    if launch is None:
        for phase in ("launch", "deployment", "commissioning"):
            prog.log.append({"phase": phase, "period": None, "message": f"{phase.capitalize()} completed."})
    else:
        prog.log.extend(launch_risk.launch_log(launch, ctx.sel, ctx.params))
        if launch["total_loss"]:
            return prog
        operating = launch["operating_periods"]
        if launch["science_factor"] < 1.0 or launch["downlink_factor"] < 1.0:
            standing.append(Modifiers(science_factor=launch["science_factor"], data_factor=launch["science_factor"],
                                      downlink_factor=launch["downlink_factor"]))

    for period in range(1, operating + 1):
        prog.period = period
        period_mods: list[tuple[Modifiers, dict]] = []
        for definition, event in anomaly_generator.candidates(definitions, prog.events, period):
            anomaly_id = anomaly_generator.instance_id(definition, period, event)
            trigger = trigger_engine.check(definition, ctx, event)
            if not trigger.eligible:
                prog.not_eligible.append({"anomaly_id": anomaly_id, "definition_id": definition.id,
                                          "name": definition.name, "period": period, "reason": trigger.reason})
                continue
            if not trigger.triggered:
                if event is not None:  # an external event the design tolerated
                    prog.records.append(history.absorbed_record(definition, anomaly_id, period, ctx, trigger))
                    prog.log.append({"phase": "science_operations", "period": period,
                                     "message": f"{definition.name} avoided: {trigger.reason}"})
                continue

            responses = decision_manager.available_responses(definition, trigger.facts)
            choices = [r for r in responses if r["available"]]
            if anomaly_id in decisions:
                response = decision_manager.validate(definition, trigger.facts, decisions[anomaly_id])
                decided_by = "player"
            elif interactive and len(choices) > 1:
                prog.status = AWAITING_DECISION
                prog.pending = history.pending_record(definition, anomaly_id, period, ctx, trigger, responses)
                prog.log.append({"phase": "science_operations", "period": period,
                                 "message": f"{definition.name}: waiting for a decision."})
                return prog
            else:
                response = definition.default_response()
                decided_by = "automatic"

            mods, outcome = anomaly_resolver.resolve(definition, response, trigger.facts)
            effect = None
            if response.standing:
                standing.append(mods)
            else:
                effect = anomaly_resolver.impact(ctx, standing, mods, prog.backlog)
            record = history.resolved_record(definition, anomaly_id, period, ctx, trigger, responses,
                                             response.id, response.label, decided_by, response.standing,
                                             outcome, effect)
            if response.standing:
                record["impact"] = {"science_credit_per_period": mods.science_factor,
                                    "data_volume_factor": mods.data_factor,
                                    "instruments_off": sorted(i for i, f in mods.instrument_fraction.items()
                                                              if f == 0.0),
                                    "note": "Applies to every operation period from this one on."}
            else:
                period_mods.append((mods, record))
            prog.records.append(record)
            prog.applied_decisions.append({"anomaly_id": anomaly_id, "response_id": response.id,
                                           "period": period, "decided_by": decided_by})
            prog.log.append({"phase": "science_operations", "period": period,
                             "message": f"{definition.name}: {response.label}. {outcome}"})

        out = anomaly_resolver.period_outcome(ctx, standing + [m for m, _ in period_mods], prog.backlog)
        prog.backlog = out.backlog_bits
        prog.science_done += out.science_credit
        prog.generated_total += out.produced_bits or 0.0
        prog.downlinked_total += out.sent_bits or 0.0
        prog.timeline.append({
            "period": period,
            "elapsed_days": round(period * ctx.days_per_period, 2),
            "science_observed": out.science_credit > 0,
            "science_credit": round(out.science_credit, 6),
            "data_generated_bits": out.produced_bits,
            "data_downlinked_bits": out.sent_bits,
            "backlog_bits": prog.backlog if out.produced_bits is not None else None,
            "event_types": [e["type"] for e in prog.events if e["period"] == period],
            "anomaly_ids": [r["anomaly_id"] for r in prog.records if r["period"] == period],
        })

    if operating < ctx.periods:
        prog.log.append({"phase": "science_operations", "period": operating, "kind": "accident",
                         "message": f"Orbit decayed: the spacecraft re-entered after {operating} of "
                                    f"{ctx.periods} operation periods."})
    unused = [a for a in decisions if a not in {d["anomaly_id"] for d in prog.applied_decisions}]
    if unused:
        raise DecisionError("unknown_anomaly", f"No anomaly '{unused[0]}' occurs in this run.")
    return prog


def resources_view(ctx: RunContext, prog: Progress) -> dict[str, Any]:
    """Tracked resources. A resource without a known start value and update rule stays null."""
    return {
        "data_backlog_bits": prog.backlog if ctx.generated_day is not None else None,
        "data_generated_bits": prog.generated_total if ctx.generated_day is not None else None,
        "data_downlinked_bits": (prog.downlinked_total
                                 if ctx.generated_day is not None and ctx.capacity_day is not None else None),
        "battery_energy_wh": None,        # battery state of charge is not modelled over time
        "propellant_remaining_kg": None,  # no manoeuvre plan or propellant budget in the model
    }
