"""Operational events. All probabilities and effects are GAMEPLAY ASSUMPTIONS.

Generation (which events occur in which period) is separate from resolution
(what they do to the mission state). Generation is deterministic for a given seed.
"""
from __future__ import annotations

import random

from ..configuration import MODE_B, ScenarioParams, Selection

EVENT_TITLES = {
    "comm_outage": "Temporary communication outage",
    "reduced_solar": "Reduced solar generation",
    "optical_cloud": "Optical link unavailable due to cloud",
    "instrument_unavailable": "Instrument unavailable for one period",
}


def generate_events(sel: Selection, params: ScenarioParams, seed: int) -> list[dict]:
    """Draw events per science period. Same selection + params + seed -> same list."""
    if not params.events.enabled:
        return []
    rng = random.Random(seed)
    ev = params.events
    instrument_ids = sorted(i["id"] for i in sel.instruments)
    events = []
    for period in range(1, params.science_periods + 1):
        # the same four draws are made every period so the sequence does not depend on the design
        draws = [rng.random() for _ in range(4)]
        pick = rng.random()
        if draws[0] < ev.comm_outage_probability:
            events.append({"period": period, "type": "comm_outage"})
        if draws[1] < ev.reduced_solar_probability:
            events.append({"period": period, "type": "reduced_solar"})
        if draws[2] < ev.optical_cloud_probability:
            events.append({"period": period, "type": "optical_cloud"})
        if draws[3] < ev.instrument_unavailable_probability and instrument_ids:
            target = instrument_ids[min(int(pick * len(instrument_ids)), len(instrument_ids) - 1)]
            events.append({"period": period, "type": "instrument_unavailable", "instrument_id": target})
    return events


def resolve_event(event: dict, sel: Selection, params: ScenarioParams, downlink_radio: dict | None,
                  generation_w: float | None, demand_w: float) -> dict:
    """Effect of one event on its period. Returns flags plus a plain-language explanation."""
    kind = event["type"]
    effect = {"downlink_lost": False, "science_lost": False, "instrument_off": None, "applies": True}
    if kind == "comm_outage":
        effect["downlink_lost"] = True
        text = "No ground contact this period: no data was downlinked. Stored data waits for the next period."
    elif kind == "optical_cloud":
        if downlink_radio is not None and downlink_radio.get("ground_station_type") == "optical":
            effect["downlink_lost"] = True
            text = "Cloud over the optical ground station blocked the laser downlink this period."
        else:
            effect["applies"] = False
            text = "Cloud over the optical site had no effect: this design does not downlink optically."
    elif kind == "reduced_solar":
        if sel.power_mode == MODE_B and generation_w is not None:
            reduced = generation_w * params.events.reduced_solar_factor
            if reduced < demand_w:
                effect["science_lost"] = True
                text = (f"Solar generation fell to {reduced:.1f} W, below the {demand_w:.1f} W demand: "
                        "instruments were switched off this period.")
            else:
                text = (f"Solar generation fell to {reduced:.1f} W but stayed above the {demand_w:.1f} W "
                        "demand: the power margin absorbed it.")
        else:
            effect["applies"] = False
            text = ("Not modelled in the platform-supplied power mode: the platform's own generation is not "
                    "part of this model.")
    elif kind == "instrument_unavailable":
        effect["instrument_off"] = event.get("instrument_id")
        text = f"{event.get('instrument_id')} was unavailable for this period."
    else:  # unknown event types are ignored, never guessed
        effect["applies"] = False
        text = "Unknown event type ignored."
    return {**event, "title": EVENT_TITLES.get(kind, kind), "effect": effect, "explanation": text,
            "value_kind": "gameplay_assumption"}
