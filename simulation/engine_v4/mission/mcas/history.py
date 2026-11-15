"""Records of what happened and why, for the mission log and the final debrief."""
from __future__ import annotations

from typing import Any, Optional

from .models import (AWAITING_PLAYER_DECISION, DETECTED, ELIGIBLE, ENGINEERING, IGNORED, MISSION_STATE_UPDATED,
                     PERSISTING, RECOVERED, RESOLVED, TRIGGERED, AnomalyDefinition, RunContext, TriggerResult)

_NUMERIC = (int, float, str, bool, list, type(None))


def _public_facts(facts: dict[str, Any]) -> dict[str, Any]:
    return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in facts.items() if isinstance(v, _NUMERIC)}


def base_record(definition: AnomalyDefinition, anomaly_id: str, period: int, ctx: RunContext,
                trigger: TriggerResult) -> dict[str, Any]:
    return {
        "anomaly_id": anomaly_id,
        "definition_id": definition.id,
        "name": definition.name,
        "category": definition.category,
        "affected_system": definition.affected_system,
        "severity": definition.severity,
        "phase": "science_operations",
        "period": period,
        "elapsed_days": round((period - 1) * ctx.days_per_period, 2),
        "what_happened": definition.description,
        "symptom": definition.symptom,
        "cause": definition.cause,
        "trigger_type": definition.trigger["type"],
        "trigger_reason": trigger.reason,
        "contributing_design_decision": trigger.design_link,
        "related_step": definition.related_step,
        "facts": _public_facts(trigger.facts),
        "recovery": definition.recovery,
        "value_kind": definition.value_kind,
        "assumptions": list(definition.assumptions),
        "source_urls": list(definition.source_urls),
    }


def absorbed_record(definition: AnomalyDefinition, anomaly_id: str, period: int, ctx: RunContext,
                    trigger: TriggerResult) -> dict[str, Any]:
    """An external event the design tolerated: no anomaly, no decision, no consequence."""
    rec = base_record(definition, anomaly_id, period, ctx, trigger)
    rec.update(status=RECOVERED, lifecycle=[ELIGIBLE, RECOVERED], responses=[], response_id=None,
               response_label=None, decided_by=None, outcome=trigger.reason, recovered=True, persisting=False,
               impact={"science_credit_lost": 0.0, "data_not_generated_bits": 0.0 if ctx.generated_day is not None
                       else None, "data_not_downlinked_bits": 0.0 if ctx.capacity_day is not None else None,
                       "note": "The design margin absorbed the event."})
    return rec


def pending_record(definition: AnomalyDefinition, anomaly_id: str, period: int, ctx: RunContext,
                   trigger: TriggerResult, responses: list[dict]) -> dict[str, Any]:
    rec = base_record(definition, anomaly_id, period, ctx, trigger)
    rec.update(status=AWAITING_PLAYER_DECISION, lifecycle=[ELIGIBLE, TRIGGERED, DETECTED, AWAITING_PLAYER_DECISION],
               responses=responses)
    return rec


def resolved_record(definition: AnomalyDefinition, anomaly_id: str, period: int, ctx: RunContext,
                    trigger: TriggerResult, responses: list[dict], response_id: str, response_label: str,
                    decided_by: str, standing: bool, outcome: str, impact: Optional[dict]) -> dict[str, Any]:
    rec = base_record(definition, anomaly_id, period, ctx, trigger)
    lifecycle = [ELIGIBLE, TRIGGERED, DETECTED]
    if decided_by == "player":
        lifecycle += [AWAITING_PLAYER_DECISION, RESOLVED]
        final = PERSISTING if standing else RESOLVED
    else:
        final = PERSISTING if standing else IGNORED
        lifecycle.append(final)
    lifecycle.append(MISSION_STATE_UPDATED)
    rec.update(status=final, lifecycle=lifecycle, responses=responses, response_id=response_id,
               response_label=response_label, decided_by=decided_by, outcome=outcome,
               recovered=not standing, persisting=standing, impact=impact)
    return rec


def sentence(rec: dict[str, Any]) -> str:
    """One debrief paragraph: what, when, why, which design choice, which response, what it cost."""
    parts = [f"{rec['name']} in operation period {rec['period']} ({rec['affected_system']})."]
    parts.append(f"Cause: {rec['cause']}")
    if rec.get("contributing_design_decision"):
        parts.append(f"Design: {rec['contributing_design_decision']}")
    if rec["status"] == RECOVERED and not rec.get("response_id"):
        parts.append(rec["outcome"])
    else:
        who = {"player": "You chose", "automatic": "Applied automatically"}[rec["decided_by"]]
        parts.append(f"{who}: {rec['response_label']}. {rec['outcome']}")
        if rec["persisting"]:
            parts.append("This stayed in effect for the rest of the mission.")
    return " ".join(parts)


def debrief_groups(records: list[dict[str, Any]], risk: dict[str, Any]) -> dict[str, list[str]]:
    """The five things the debrief must keep apart."""
    weaknesses = [f"{r['title']}: {r['reason']}" for r in risk["risks"] if r["level"] in ("HIGH", "MEDIUM")]
    weaknesses += [f"{rec['name']}: {rec['contributing_design_decision']}" for rec in records
                   if rec["category"] == ENGINEERING and rec["status"] != RECOVERED
                   and rec.get("contributing_design_decision")]
    external = [f"Period {rec['period']}: {rec['name']}. {rec['trigger_reason']}" for rec in records
                if rec["category"] != ENGINEERING]
    decisions = [f"Period {rec['period']}, {rec['name']}: {rec['response_label']}." for rec in records
                 if rec.get("decided_by") == "player"]
    consequences = [f"Period {rec['period']}, {rec['name']}: {rec['outcome']}" for rec in records
                    if rec.get("response_id")]
    assumptions: list[str] = []
    for rec in records:
        for text in rec["assumptions"]:
            if text not in assumptions:
                assumptions.append(text)
    return {"engineering_weaknesses": weaknesses, "external_events": external, "player_decisions": decisions,
            "mission_consequences": consequences, "gameplay_assumptions": assumptions}
