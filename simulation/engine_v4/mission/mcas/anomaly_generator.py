"""External (uncertain) events and deterministic candidates for each period.

External events reuse the existing seeded generator in mission/events.py unchanged, so the same
configuration, scenario parameters and seed always give the same events. Probabilities live in the
scenario (`parameters.events`) and are gameplay assumptions.
"""
from __future__ import annotations

from typing import Optional

from ..events import generate_events
from .models import DETERMINISTIC, AnomalyDefinition, RunContext


def external_events(ctx: RunContext) -> list[dict]:
    """Raw seeded events: [{"period", "type", "instrument_id"?}], exactly as the v4 engine drew them."""
    return generate_events(ctx.sel, ctx.params, ctx.seed)


def candidates(definitions: list[AnomalyDefinition], events: list[dict],
               period: int) -> list[tuple[AnomalyDefinition, Optional[dict]]]:
    """Anomalies to check in this period: engineering ones once (first period), then this period's events."""
    out: list[tuple[AnomalyDefinition, Optional[dict]]] = []
    if period == 1:
        out += [(d, None) for d in definitions if d.trigger["type"] == DETERMINISTIC]
    by_event = {d.trigger.get("source_event"): d for d in definitions if d.trigger["type"] != DETERMINISTIC}
    for event in events:
        if event["period"] == period and event["type"] in by_event:
            out.append((by_event[event["type"]], event))
    return out


def instance_id(definition: AnomalyDefinition, period: int, event: Optional[dict]) -> str:
    """Stable identifier of one occurrence. An occurrence is never triggered twice."""
    if event is None:
        return definition.id
    suffix = f"-{event['instrument_id']}" if event.get("instrument_id") else ""
    return f"{definition.id}-p{period:02d}{suffix}"
