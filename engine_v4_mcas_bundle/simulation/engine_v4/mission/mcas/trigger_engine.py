"""Eligibility and trigger checks.

Each check reads the engineering evaluation and returns facts for the resolver and the debrief.
Engineering triggers are deterministic. External events arrive from the seeded generator and are
only turned into an anomaly when the configuration is actually exposed to them.
Unknown values stay unknown: a check that needs a missing value reports NOT eligible, with the reason.
"""
from __future__ import annotations

from typing import Callable, Optional

from ...configuration import MODE_B
from ...constraints import communications, power
from ...results import WARNING
from .anomaly_catalog import GAMEPLAY_PARAMETERS
from .models import AnomalyDefinition, RunContext, TriggerResult

GB = 8e9


def _backup_radio(ctx: RunContext, rf_only: bool) -> Optional[dict]:
    """Best compatible radio other than the main downlink radio, with a known capacity.

    rf_only: any non-optical radio (cloud). Otherwise: a different ground-station type (network outage).
    """
    main = ctx.radio
    if main is None:
        return None
    pass_s = ctx.evaluation["downlink"]["pass_seconds_per_day"]
    best = None
    for radio in ctx.sel.comms:
        if radio["id"] == main["id"] or not communications.radio_is_compatible(radio, ctx.params):
            continue
        station = radio.get("ground_station_type")
        if rf_only and station == "optical":
            continue
        if not rf_only and station == main.get("ground_station_type"):
            continue
        cap = communications.daily_capacity_bits(radio, pass_s, ctx.params)
        if cap is not None and (best is None or cap > best["bits_per_day"]):
            best = {"radio_id": radio["id"], "bits_per_day": cap, "ground_station_type": station}
    return best


def _link_facts(ctx: RunContext, backup: Optional[dict]) -> dict:
    main = ctx.radio
    return {
        "primary_radio_id": main["id"] if main else None,
        "primary_station_type": main.get("ground_station_type") if main else None,
        "primary_bits_per_day": ctx.capacity_day,
        "primary_gb_per_day": None if ctx.capacity_day is None else ctx.capacity_day / GB,
        "backup_radio_id": backup["radio_id"] if backup else None,
        "backup_bits_per_day": backup["bits_per_day"] if backup else None,
        "backup_gb_per_day": backup["bits_per_day"] / GB if backup else None,
    }


def communication_outage(ctx: RunContext, event: Optional[dict]) -> TriggerResult:
    if not ctx.sel.comms:
        return TriggerResult(False, False, "No communication system is selected.")
    backup = _backup_radio(ctx, rf_only=False)
    main = ctx.radio
    if main is None:
        link = "No compatible radio has a known downlink rate, so the amount of data affected is unknown."
    elif backup:
        link = (f"{backup['radio_id']} uses a different ground-station type than the main downlink radio "
                f"{main['id']}, which gives a second path to the ground.")
    else:
        link = (f"All downlink goes through one ground-station type ({main.get('ground_station_type')}, radio "
                f"{main['id']}); no selected radio can use another network.")
    return TriggerResult(True, True, "Ground contact on the main downlink band is unavailable this period.",
                         _link_facts(ctx, backup), link)


def optical_downlink_cloud(ctx: RunContext, event: Optional[dict]) -> TriggerResult:
    main = ctx.radio
    if main is None or main.get("ground_station_type") != "optical":
        return TriggerResult(False, False, "This design does not downlink optically, so cloud over an optical "
                                           "ground station cannot affect it.")
    backup = _backup_radio(ctx, rf_only=True)
    link = (f"The main downlink radio {main['id']} needs a cloud-free optical ground station"
            + (f"; {backup['radio_id']} is a radio-frequency fallback." if backup else
               " and no radio-frequency downlink is on board."))
    return TriggerResult(True, True, "Cloud over the optical ground station blocks the laser downlink.",
                         _link_facts(ctx, backup), link)


def _demand_at_duty_scale(ctx: RunContext, scale: float):
    """Demand summary with every instrument duty cycle multiplied by `scale` (existing power model)."""
    p = ctx.params
    scaled = p.model_copy(update={
        "instrument_duty_cycle": p.instrument_duty_cycle * scale,
        "instrument_duty_cycle_overrides": {k: v * scale for k, v in p.instrument_duty_cycle_overrides.items()},
    })
    return scaled, power.demand_summary(ctx.sel, scaled)


def power_shortage(ctx: RunContext, event: Optional[dict]) -> TriggerResult:
    if ctx.sel.power_mode != MODE_B:
        return TriggerResult(False, False, "Not modelled in the platform-supplied power mode: the platform's "
                                           "own generation is not part of this model.")
    if ctx.generation_w is None:
        return TriggerResult(False, False, "Solar generation is unknown for this design, so the effect of "
                                           "reduced generation cannot be evaluated.")
    factor = ctx.params.events.reduced_solar_factor
    reduced, demand = ctx.generation_w * factor, ctx.demand_w
    margin = (ctx.generation_w - demand) / ctx.generation_w if ctx.generation_w else None
    link = (f"Solar generation is {ctx.generation_w:.1f} W against {demand:.1f} W of average demand"
            + (f" ({margin * 100:.0f}% margin)." if margin is not None else "."))
    facts = {"generation_w": ctx.generation_w, "reduced_w": reduced, "demand_w": demand,
             "reduced_solar_factor": factor, "deficit_w": max(0.0, demand - reduced)}
    if reduced >= demand:
        return TriggerResult(True, False, f"Solar generation fell to {reduced:.1f} W but stayed above the "
                                          f"{demand:.1f} W demand: the power margin absorbed it.", facts, link)
    # largest instrument operating share whose demand fits the reduced generation (demand is linear in duty)
    standby = _demand_at_duty_scale(ctx, 0.0)[1]["known_avg_w"]
    duty = None
    if demand > standby and reduced > standby:
        duty = min(1.0, (reduced - standby) / (demand - standby))
    facts.update(standby_demand_w=standby, power_limited_duty=duty,
                 power_limited_duty_pct=None if duty is None else duty * 100.0)
    return TriggerResult(True, True, f"Solar generation fell to {reduced:.1f} W, below the {demand:.1f} W "
                                     "demand.", facts, link)


def instrument_unavailable(ctx: RunContext, event: Optional[dict]) -> TriggerResult:
    iid = (event or {}).get("instrument_id")
    if iid is None or iid not in {i["id"] for i in ctx.sel.instruments}:
        return TriggerResult(False, False, "No instrument on board is affected.")
    relevant = ctx.relevant_ids
    others = [r for r in relevant if r != iid]
    if iid not in relevant:
        note = "It does not serve the mission objective, so observations of the objective continued."
        link = f"{iid} is a secondary instrument for this mission."
    elif others:
        note = f"{', '.join(others)} kept observing for the mission objective."
        link = f"{len(relevant)} instruments serve the mission objective, so one can cover for another."
    else:
        note = "It is the only instrument that serves the mission objective, so the period produced no observations."
        link = f"{iid} is the only instrument that serves the mission objective: there is no redundancy."
    fraction = GAMEPLAY_PARAMETERS["recovery_period_fraction"]["value"]
    return TriggerResult(True, True, f"{iid} stopped responding.",
                         {"instrument_id": iid, "is_relevant": iid in relevant, "redundancy_note": note,
                          "recovery_period_fraction": fraction, "recovery_pct": fraction * 100.0}, link)


def data_backlog(ctx: RunContext, event: Optional[dict]) -> TriggerResult:
    generated, capacity = ctx.generated_day, ctx.capacity_day
    if generated is None or capacity is None:
        return TriggerResult(False, False, "Instrument data rates or downlink capacity are unknown, so the data "
                                           "balance is not evaluated. No rate is invented.")
    if generated <= capacity:
        return TriggerResult(True, False, "Daily downlink capacity covers the data generated each day.")
    fraction = capacity / generated
    secondary = [i["id"] for i in ctx.sel.instruments if i["id"] not in ctx.relevant_ids]
    if not ctx.relevant_ids:
        secondary = []
    link = (f"Instruments generate {generated / GB:.2f} GB per day; the best downlink radio "
            f"{ctx.evaluation['downlink']['radio_id']} returns {capacity / GB:.2f} GB per day.")
    return TriggerResult(True, True, "Data generation exceeds downlink capacity.",
                         {"generated_bits_per_day": generated, "capacity_bits_per_day": capacity,
                          "downlink_fraction": fraction, "downlink_pct": fraction * 100.0,
                          "lost_pct": (1.0 - fraction) * 100.0, "secondary_ids": secondary,
                          "secondary_list": ", ".join(secondary)}, link)


def pointing_instability(ctx: RunContext, event: Optional[dict]) -> TriggerResult:
    result = ctx.constraint("pointing_vs_swath")
    if result is None or result.actual_value is None:
        return TriggerResult(False, False, "ADCS pointing accuracy or orbit altitude is unknown, so pointing "
                                           "error is not evaluated.")
    offset_m = result.actual_value
    swaths = {r["id"]: r["swath_km_at_orbit"] for r in ctx.evaluation["instruments_at_orbit"]
              if r.get("swath_km_at_orbit")}
    relevant = [(i, swaths[i]) for i in ctx.relevant_ids if i in swaths]
    if not relevant:
        return TriggerResult(False, False, "No instrument serving the objective has a known swath to compare "
                                           "the pointing error with.")
    at_risk = [(i, s) for i, s in relevant if i in result.affected_component_ids]
    if result.status != WARNING or not at_risk:
        return TriggerResult(True, False, "Pointing error is small against the swath of the instruments that "
                                          "serve the objective.")
    iid, swath_km = max(at_risk, key=lambda t: offset_m / (t[1] * 1000.0))
    miss = min(1.0, offset_m / (swath_km * 1000.0))
    repeat = 1.0 + miss
    ok, why = _repeat_power(ctx, repeat)
    link = (f"{ctx.sel.adcs['id']} gives about {offset_m / 1000:.1f} km of pointing error on the ground at "
            f"this altitude, against the {swath_km:g} km swath of {iid}.")
    return TriggerResult(True, True, "Pointing error is a large share of the instrument swath.",
                         {"offset_m": offset_m, "offset_km": offset_m / 1000.0, "instrument_id": iid,
                          "swath_km": swath_km, "miss_fraction": miss, "miss_pct": miss * 100.0,
                          "hit_fraction": 1.0 - miss, "repeat_factor": repeat,
                          "repeat_power_ok": ok, "repeat_power_reason": why}, link)


def _repeat_power(ctx: RunContext, repeat: float) -> tuple[bool, str]:
    """Can the power system carry instrument operating time multiplied by `repeat`? Existing power model."""
    p = ctx.params
    duties = [p.instrument_duty_cycle_overrides.get(i["id"], p.instrument_duty_cycle) for i in ctx.sel.instruments]
    if any(d * repeat > 1.0 for d in duties):
        return False, "Instruments would have to operate more than 100% of the time."
    scaled, demand = _demand_at_duty_scale(ctx, repeat)
    margin = power.power_margin_fraction(ctx.sel, demand, scaled)
    if margin is None:
        return False, "The power margin is unknown, so the extra operating time cannot be confirmed."
    if margin < 0:
        return False, (f"The extra operating time needs {demand['known_avg_w']:.1f} W on average, more than the "
                       "power system supplies.")
    return True, f"Power margin with the extra operating time: {margin * 100:.0f}%."


CHECKS: dict[str, Callable[[RunContext, Optional[dict]], TriggerResult]] = {
    "communication_outage": communication_outage,
    "optical_downlink_cloud": optical_downlink_cloud,
    "power_shortage": power_shortage,
    "instrument_unavailable": instrument_unavailable,
    "data_backlog": data_backlog,
    "pointing_instability": pointing_instability,
}


def check(definition: AnomalyDefinition, ctx: RunContext, event: Optional[dict] = None) -> TriggerResult:
    return CHECKS[definition.trigger["check"]](ctx, event)
