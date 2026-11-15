"""Pre-launch risk assessment: what the design is vulnerable to, and why.

Reads the engineering evaluation only. Levels describe vulnerability, not probability:
  LOW      adequate margin; the modelled disturbance is tolerated
  MEDIUM   works, with limited margin
  HIGH     highly vulnerable, or a requirement is already violated
  UNKNOWN  a needed value is missing; it is not assumed to be fine or to be zero

A hard constraint failure stays a hard failure (`blocks_launch`), CONDITIONAL stays CONDITIONAL,
and TRL is not used here: it is a maturity factor in the score, not a failure probability.
"""
from __future__ import annotations

from typing import Any, Optional

from ...results import FAIL, GAMEPLAY, HARD, INFEASIBLE, NOT_EVALUATED, WARNING
from . import anomaly_catalog, trigger_engine
from .models import HIGH, LOW, MEDIUM, UNKNOWN, RunContext

# engineering result -> the anomaly it can lead to in flight
CONSTRAINT_ANOMALY = {"data_balance": "data_backlog", "pointing_vs_swath": "pointing_instability",
                      "power_generation": "power_shortage"}
_ORDER = {HIGH: 3, MEDIUM: 2, LOW: 1, UNKNOWN: 0}


def _risk(risk_id: str, system: str, level: str, title: str, reason: str, source: str,
          related_step: Optional[str], blocks_launch: bool = False,
          anomaly_ids: Optional[list[str]] = None, value_kind: str = "derived") -> dict[str, Any]:
    return {"id": risk_id, "system": system, "level": level, "title": title, "reason": reason,
            "source": source, "related_step": related_step, "blocks_launch": blocks_launch,
            "linked_anomaly_ids": anomaly_ids or [], "value_kind": value_kind}


def _from_constraints(ctx: RunContext) -> list[dict]:
    out = []
    for r in ctx.evaluation["constraints"]:
        if r.status == FAIL:
            level = HIGH
        elif r.status == WARNING:
            level = MEDIUM
        elif r.status == NOT_EVALUATED:
            level = UNKNOWN
        else:
            continue
        linked = [CONSTRAINT_ANOMALY[r.id]] if r.id in CONSTRAINT_ANOMALY and r.status != NOT_EVALUATED else []
        out.append(_risk(f"constraint.{r.id}", r.category, level, r.title, r.message, f"constraints.{r.id}",
                         r.related_step, blocks_launch=(r.status == FAIL and r.severity == HARD),
                         anomaly_ids=linked, value_kind=r.value_kind))
    return out


def _from_margins(ctx: RunContext) -> list[dict]:
    target = ctx.params.margin_target_fraction
    out = []
    for key, system, label, step, consequence in (
            ("mass_margin_fraction", "mass", "Payload mass margin", "instruments",
             "limited tolerance for additional mass"),
            ("power_margin_fraction", "power", "Power margin", "power",
             "vulnerable to reduced power generation or higher demand")):
        margin = ctx.evaluation["margins"][key]
        if margin is None:
            out.append(_risk(f"margin.{key}", system, UNKNOWN, label,
                             "Not evaluated: some component values are unknown. Unknown is not treated as zero.",
                             f"margins.{key}", step))
        elif margin < 0:
            continue  # already reported as a failed constraint
        elif margin < target:
            out.append(_risk(f"margin.{key}", system, MEDIUM, label,
                             f"{margin * 100:.0f}% margin, below the {target * 100:.0f}% target: {consequence}.",
                             f"margins.{key}", step, value_kind=GAMEPLAY))
        else:
            out.append(_risk(f"margin.{key}", system, LOW, label,
                             f"{margin * 100:.0f}% margin, at or above the {target * 100:.0f}% target.",
                             f"margins.{key}", step, value_kind=GAMEPLAY))
    return out


def _from_exposure(ctx: RunContext) -> list[dict]:
    """How the design would take each external event if it happened (no probability involved)."""
    out = []
    cat = anomaly_catalog.CATALOG

    t = trigger_engine.communication_outage(ctx, None)
    if t.eligible:
        level = UNKNOWN if ctx.radio is None else (LOW if t.facts.get("backup_bits_per_day") is not None else MEDIUM)
        out.append(_risk("exposure.communication_outage", "communications", level,
                         "Ground-station outage", t.design_link or t.reason, "mcas.communication_outage",
                         cat["communication_outage"].related_step, anomaly_ids=["communication_outage"]))

    t = trigger_engine.optical_downlink_cloud(ctx, None)
    if t.eligible:
        level = LOW if t.facts.get("backup_bits_per_day") is not None else MEDIUM
        out.append(_risk("exposure.optical_downlink_cloud", "communications", level,
                         "Cloud over the optical ground station", t.design_link or t.reason,
                         "mcas.optical_downlink_cloud", "communications",
                         anomaly_ids=["optical_downlink_cloud"]))

    t = trigger_engine.power_shortage(ctx, None)
    if not t.eligible:
        out.append(_risk("exposure.power_shortage", "power", UNKNOWN, "Reduced solar generation", t.reason,
                         "mcas.power_shortage", "power"))
    else:
        text = (f"{t.design_link} If generation drops to {t.facts['reduced_solar_factor'] * 100:.0f}% "
                f"({t.facts['reduced_w']:.1f} W), " + ("demand is no longer covered." if t.triggered
                                                       else "demand is still covered."))
        out.append(_risk("exposure.power_shortage", "power", MEDIUM if t.triggered else LOW,
                         "Reduced solar generation", text, "mcas.power_shortage", "power",
                         anomaly_ids=["power_shortage"], value_kind=GAMEPLAY))

    relevant = ctx.relevant_ids
    if not relevant:
        out.append(_risk("exposure.instrument_unavailable", "payload", HIGH, "Instrument availability",
                         "No selected instrument serves the mission objective.", "performance.rules", "instruments"))
    elif len(relevant) == 1:
        out.append(_risk("exposure.instrument_unavailable", "payload", MEDIUM, "Instrument availability",
                         f"{relevant[0]} is the only instrument that serves the mission objective: if it is "
                         "unavailable, observation stops.", "mcas.instrument_unavailable", "instruments",
                         anomaly_ids=["instrument_unavailable"]))
    else:
        out.append(_risk("exposure.instrument_unavailable", "payload", LOW, "Instrument availability",
                         f"{len(relevant)} instruments serve the mission objective, so one can cover for another.",
                         "mcas.instrument_unavailable", "instruments", anomaly_ids=["instrument_unavailable"]))
    return out


def assess_risk(ctx: RunContext) -> dict[str, Any]:
    feas = ctx.evaluation["feasibility"]
    risks = _from_constraints(ctx) + _from_margins(ctx) + _from_exposure(ctx)
    risks.sort(key=lambda r: -_ORDER[r["level"]])
    known = [r["level"] for r in risks if r["level"] != UNKNOWN]
    return {
        "feasibility_status": feas["status"],
        "launchable": feas["status"] != INFEASIBLE,
        "overall_level": max(known, key=lambda lv: _ORDER[lv]) if known else UNKNOWN,
        "counts": {lv: sum(1 for r in risks if r["level"] == lv) for lv in (HIGH, MEDIUM, LOW, UNKNOWN)},
        "risks": risks,
        "notes": [
            "Levels describe vulnerability, not a calculated probability of failure.",
            "UNKNOWN means a needed value is missing from the dataset; it is not counted as safe or as zero.",
            f"Margins are compared with the scenario's margin target "
            f"({ctx.params.margin_target_fraction * 100:.0f}%, gameplay assumption).",
            "A risk with blocks_launch = true is a hard constraint failure: the design cannot launch, and it "
            "is never turned into an in-flight anomaly.",
        ],
    }
