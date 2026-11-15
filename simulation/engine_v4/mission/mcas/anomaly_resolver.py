"""Turn a chosen response into modifiers, and compute what a period actually produced.

No fixed penalties: every consequence comes from the trigger facts (which come from the engineering
evaluation) and from the current backlog. The period arithmetic is the v4 mission model, generalised
from on/off flags to fractions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .decision_manager import fill
from .models import AnomalyDefinition, Modifiers, Response, RunContext


def _number(value: Any, facts: dict[str, Any]) -> float:
    """A literal number, or the name of a trigger fact."""
    if isinstance(value, str):
        return float(facts[value])
    return float(value)


def resolve(definition: AnomalyDefinition, response: Response, facts: dict[str, Any]) -> tuple[Modifiers, str]:
    """Modifiers for one response plus a plain-language account of what it did."""
    fx, mods = response.effects, Modifiers()
    if "science" in fx:
        mods.science_factor = _number(fx["science"], facts)
    if "data" in fx:
        mods.data_factor = _number(fx["data"], facts)
    if "downlink_factor" in fx:
        mods.downlink_factor = _number(fx["downlink_factor"], facts)
    if fx.get("primary_downlink") == "lost":
        mods.primary_downlink_lost = True
    if fx.get("backup_downlink") == "backup":
        mods.backup_capacity_bits_per_day = facts["backup_bits_per_day"]
    if "instrument" in fx:
        mods.instrument_fraction[facts["instrument_id"]] = _number(fx["instrument"], facts)
    if fx.get("instruments_off") == "secondary":
        for iid in facts["secondary_ids"]:
            mods.instrument_fraction[iid] = 0.0
    return mods, fill(response.outcome, facts)


@dataclass
class PeriodOutcome:
    science_credit: float
    produced_bits: Optional[float]
    sent_bits: Optional[float]
    backlog_bits: float
    instrument_fraction: dict[str, float] = field(default_factory=dict)


def period_outcome(ctx: RunContext, mods_list: list[Modifiers], backlog: float) -> PeriodOutcome:
    """One operation period under the given modifiers. Pure: the caller keeps the state."""
    inst = {i["id"]: 1.0 for i in ctx.sel.instruments}
    science = data = downlink = 1.0
    primary_lost, backup = False, None
    for m in mods_list:
        for iid, fraction in m.instrument_fraction.items():
            if iid in inst:
                inst[iid] = min(inst[iid], fraction)
        science *= m.science_factor
        data *= m.data_factor
        downlink *= m.downlink_factor
        primary_lost = primary_lost or m.primary_downlink_lost
        if m.backup_capacity_bits_per_day is not None:
            backup = max(backup or 0.0, m.backup_capacity_bits_per_day)

    relevant_on = max((inst[i] for i in ctx.relevant_ids if i in inst), default=0.0)
    credit = relevant_on * science

    produced = sent = None
    if ctx.generated_day is not None:
        share = sum(inst.values()) / len(inst) if inst else 0.0
        produced = ctx.generated_day * ctx.days_per_period * share * data
        backlog += produced
        if ctx.capacity_day is not None:
            capacity = (backup or 0.0) if primary_lost else ctx.capacity_day
            sent = min(backlog, capacity * ctx.days_per_period * downlink)
            backlog -= sent
    return PeriodOutcome(credit, produced, sent, backlog, inst)


def impact(ctx: RunContext, standing: list[Modifiers], mods: Modifiers, backlog: float) -> dict[str, Any]:
    """What this one anomaly cost in its period, against the same period without it."""
    base = period_outcome(ctx, standing, backlog)
    with_it = period_outcome(ctx, standing + [mods], backlog)

    def diff(a: Optional[float], b: Optional[float]) -> Optional[float]:
        return None if a is None or b is None else a - b

    return {"science_credit_lost": round(base.science_credit - with_it.science_credit, 6),
            "data_not_generated_bits": diff(base.produced_bits, with_it.produced_bits),
            "data_not_downlinked_bits": diff(base.sent_bits, with_it.sent_bits),
            "note": "Compared with the same period without this anomaly. Unknown data values stay unknown."}
