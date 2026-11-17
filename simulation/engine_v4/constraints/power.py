"""Power budget with an explicit power_mode.

Mode A (platform_payload_budget, default): demand vs the platform's published
payload_average_power_w. Selected solar arrays are NOT added to the budget.

Mode B (player_built_power_system): orbit-average generation vs demand, eclipse
energy vs usable battery energy, EPS output limit, and the platform figure as a cap.

It is unknown whether GSAT platforms include their own power hardware
(includes_power_hardware is null). Neither mode decides that question; the mode
is an explicit modelling choice reported with the result. This is a simplified
average-power model, not a full electrical power system simulation.
"""
from __future__ import annotations

from typing import Optional

from ..configuration import MODE_A, ScenarioParams, Selection
from ..results import (FAIL, GAMEPLAY, HARD, MIXED, NOT_EVALUATED, PASS, SOFT, WARNING,
                       ConstraintResult, source_urls)
from .communications import SECONDS_PER_DAY, pass_seconds_per_day


def _averaged(cid: str, group: str, on_w: Optional[float], idle_w: Optional[float], duty: float) -> dict:
    """avg = duty*on + (1-duty)*idle. Unknown idle -> on-power used as an upper bound, never zero."""
    if on_w is None:
        return {"id": cid, "group": group, "avg_w": None, "peak_w": None, "upper_bound": False,
                "note": "operating power not published"}
    if idle_w is None:
        return {"id": cid, "group": group, "avg_w": float(on_w), "peak_w": float(on_w), "upper_bound": True,
                "note": "standby power not published: operating power used all the time as an upper bound"}
    return {"id": cid, "group": group, "avg_w": duty * on_w + (1.0 - duty) * idle_w, "peak_w": float(on_w),
            "upper_bound": False, "note": f"duty cycle {duty:g} (gameplay parameter)"}


def demand_items(sel: Selection, params: ScenarioParams) -> list[dict]:
    """Orbit-average power draw of each consumer."""
    items = []
    for inst in sel.instruments:
        duty = params.instrument_duty_cycle_overrides.get(inst["id"], params.instrument_duty_cycle)
        items.append(_averaged(inst["id"], "instrument", inst.get("power_operating_w"),
                               inst.get("power_standby_w"), duty))
    adcs = sel.adcs
    if adcs.get("power_w") is not None:
        items.append({"id": adcs["id"], "group": "adcs", "avg_w": float(adcs["power_w"]),
                      "peak_w": float(adcs["power_w"]), "upper_bound": False, "note": "published, continuous"})
    elif isinstance(adcs.get("power_range_w"), dict) and adcs["power_range_w"].get("max") is not None:
        top = float(adcs["power_range_w"]["max"])
        items.append({"id": adcs["id"], "group": "adcs", "avg_w": top, "peak_w": top, "upper_bound": True,
                      "note": "top of the published family range used as an upper bound "
                              "(not this exact configuration)"})
    else:
        items.append({"id": adcs["id"], "group": "adcs", "avg_w": None, "peak_w": None, "upper_bound": False,
                      "note": "power not published"})
    pass_s = pass_seconds_per_day(sel.orbit, params)
    tx_duty = 1.0 if pass_s is None else min(1.0, pass_s / SECONDS_PER_DAY)
    for radio in sel.comms:
        items.append(_averaged(radio["id"], "communications", radio.get("power_tx_w"),
                               radio.get("power_idle_w"), tx_duty))
    if sel.propulsion:
        p = sel.propulsion
        items.append(_averaged(p["id"], "propulsion", p.get("power_firing_w"), p.get("power_standby_w"),
                               params.propulsion_firing_duty_cycle))
    return items


def demand_summary(sel: Selection, params: ScenarioParams) -> dict:
    items = demand_items(sel, params)
    known = [i for i in items if i["avg_w"] is not None]
    return {
        "items": items,
        "known_avg_w": round(sum(i["avg_w"] for i in known), 6),
        "known_peak_w": round(sum(i["peak_w"] for i in known), 6),
        "unknown_ids": [i["id"] for i in items if i["avg_w"] is None],
        "upper_bound_ids": [i["id"] for i in known if i["upper_bound"]],
    }


def _demand_assumptions(summary: dict) -> list[str]:
    out = ["Instrument, radio and propulsion duty cycles are gameplay parameters.",
           "Selected subsystems are counted against the payload power figure; whether the GSAT bus powers "
           "them separately is unknown."]
    if summary["upper_bound_ids"]:
        out.append("Upper-bound draw used where standby/idle or exact power is not published: "
                   + ", ".join(summary["upper_bound_ids"]) + ".")
    return out


def _compare(result_id: str, title: str, demand: dict, limit: Optional[float], limit_label: str,
             base: dict) -> ConstraintResult:
    """known demand > limit -> FAIL; unknown consumers -> NOT_EVALUATED; else PASS."""
    known = demand["known_avg_w"]
    common = dict(id=result_id, title=title, actual_value=known, limit_value=limit, unit="W", **base)
    if limit is None:
        return ConstraintResult(status=NOT_EVALUATED, message=f"{limit_label} is unknown.", **common)
    if known > limit:
        top = sorted((i for i in demand["items"] if i["avg_w"] is not None), key=lambda i: -i["avg_w"])[:3]
        return ConstraintResult(
            status=FAIL, affected_component_ids=[i["id"] for i in top],
            message=f"Average demand {known:.1f} W exceeds {limit_label} of {limit:g} W. Largest consumers: "
                    + ", ".join(f"{i['id']} ({i['avg_w']:.1f} W)" for i in top) + ".", **common)
    if demand["unknown_ids"]:
        return ConstraintResult(
            status=NOT_EVALUATED, affected_component_ids=list(demand["unknown_ids"]),
            message=f"Known average demand is {known:.1f} W against {limit_label} of {limit:g} W, but the power "
                    f"draw of {', '.join(demand['unknown_ids'])} is not published. Unknown power is not treated "
                    "as zero, so this is a partial evaluation.", **common)
    return ConstraintResult(
        status=PASS, message=f"Average demand {known:.1f} W is within {limit_label} of {limit:g} W "
                             f"({(1 - known / limit) * 100:.0f}% margin)." if limit else "Within the limit.",
        **common)


def check_power_mode_a(sel: Selection, params: ScenarioParams, demand: dict) -> list[ConstraintResult]:
    assumptions = ["Power mode 'platform_payload_budget': the platform's published payload average power "
                   "is taken as the available budget. This is a simplified platform-supplied-power assumption."]
    assumptions += _demand_assumptions(demand)
    if sel.solar_arrays or sel.batteries or sel.eps:
        assumptions.append("Selected power components are not added to the budget in this mode (they still "
                           "count for mass). This does not mean they are required or redundant: whether the "
                           "platform includes power hardware is unknown.")
    base = dict(category="power", severity=HARD, value_kind=MIXED, assumptions=assumptions,
                source_urls=source_urls(sel.platform, *[r for _, r in sel.carried()]), related_step="power")
    return [_compare("power_budget", "Payload power budget (platform-supplied)", demand,
                     sel.platform.get("payload_average_power_w"), "the platform payload power", base)]


def generation_avg_w(sel: Selection, params: ScenarioParams, factor: float = 1.0) -> dict:
    """P_gen = sum(peak_power_w) * (1 - max_eclipse_fraction) * k * factor."""
    unknown = [a["id"] for a in sel.solar_arrays if a.get("peak_power_w") is None]
    eclipse = sel.orbit.get("max_eclipse_fraction")
    if unknown or eclipse is None:
        return {"value_w": None, "unknown_ids": unknown, "peak_w": None}
    peak = sum(a["peak_power_w"] for a in sel.solar_arrays)
    return {"value_w": round(peak * (1.0 - eclipse) * params.solar_k_factor * factor, 6),
            "unknown_ids": [], "peak_w": peak}


def usable_battery_wh(sel: Selection, params: ScenarioParams) -> dict:
    """Nominal energy of batteries plus an EPS's own pack (counted once), times depth of discharge."""
    stores = list(sel.batteries) + ([sel.eps] if sel.eps and sel.eps.get("energy_wh") is not None else [])
    unknown = [b["id"] for b in sel.batteries if b.get("energy_wh") is None]
    if unknown:
        return {"value_wh": None, "nominal_wh": None, "unknown_ids": unknown}
    nominal = sum(s["energy_wh"] for s in stores)
    return {"value_wh": round(nominal * params.battery_depth_of_discharge, 6), "nominal_wh": nominal,
            "unknown_ids": []}


def check_power_mode_b(sel: Selection, params: ScenarioParams, demand: dict) -> list[ConstraintResult]:
    power_recs = sel.solar_arrays + sel.batteries + ([sel.eps] if sel.eps else [])
    mode_note = ("Power mode 'player_built_power_system': the player's solar arrays and batteries supply the "
                 "spacecraft. If the GSAT bus already includes power hardware (unknown), this mode is "
                 "conservative. Generation is never added to the platform payload power figure.")
    base = dict(category="power", severity=HARD, value_kind=MIXED, related_step="power",
                source_urls=source_urls(sel.platform, sel.orbit, *power_recs))
    d_assume = _demand_assumptions(demand)
    results = []

    # 1. generation vs demand
    gen = generation_avg_w(sel, params)
    g_assume = [mode_note, f"Sun-angle and degradation factor k = {params.solar_k_factor:g} (gameplay "
                           "assumption).", "Worst-case eclipse fraction for the orbit (derived).",
                "Array peak power is beginning-of-life, best sun angle (upper bound)."] + d_assume
    g_base = dict(base, assumptions=g_assume)
    if gen["value_w"] is None:
        results.append(ConstraintResult(
            id="power_generation", title="Orbit-average generation vs demand", status=NOT_EVALUATED,
            affected_component_ids=gen["unknown_ids"], actual_value=demand["known_avg_w"], unit="W",
            message="Solar array peak power or orbit eclipse fraction is unknown, so generation is not "
                    "evaluated.", **g_base))
    else:
        results.append(_compare("power_generation", "Orbit-average generation vs demand", demand,
                                gen["value_w"], "orbit-average solar generation", g_base))

    # 2. eclipse energy vs usable battery energy
    eclipse_min = sel.orbit.get("max_eclipse_min")
    batt = usable_battery_wh(sel, params)
    b_assume = [mode_note, f"Battery depth of discharge = {params.battery_depth_of_discharge:g} (gameplay "
                           "assumption).", "Demand in eclipse is taken equal to orbit-average demand."] + d_assume
    b_base = dict(base, assumptions=b_assume, unit="Wh")
    need = None if eclipse_min is None else round(demand["known_avg_w"] * eclipse_min / 60.0, 6)
    if need is None or batt["value_wh"] is None:
        results.append(ConstraintResult(
            id="battery_eclipse", title="Battery energy for eclipse", status=NOT_EVALUATED,
            affected_component_ids=batt["unknown_ids"], actual_value=need,
            message="Battery energy or eclipse duration is unknown, so eclipse supply is not evaluated.",
            **b_base))
    elif need > batt["value_wh"]:
        results.append(ConstraintResult(
            id="battery_eclipse", title="Battery energy for eclipse", status=FAIL,
            actual_value=need, limit_value=batt["value_wh"],
            affected_component_ids=[b["id"] for b in sel.batteries],
            message=f"Eclipse needs {need:.1f} Wh ({eclipse_min:g} min at {demand['known_avg_w']:.1f} W) but only "
                    f"{batt['value_wh']:.1f} Wh is usable ({batt['nominal_wh']:g} Wh nominal at "
                    f"{params.battery_depth_of_discharge:g} depth of discharge)."
                    + (" No battery is selected." if not batt["nominal_wh"] else ""), **b_base))
    elif demand["unknown_ids"]:
        results.append(ConstraintResult(
            id="battery_eclipse", title="Battery energy for eclipse", status=NOT_EVALUATED,
            actual_value=need, limit_value=batt["value_wh"], affected_component_ids=demand["unknown_ids"],
            message=f"Known eclipse need is {need:.1f} Wh against {batt['value_wh']:.1f} Wh usable, but the "
                    f"power draw of {', '.join(demand['unknown_ids'])} is unknown.", **b_base))
    else:
        results.append(ConstraintResult(
            id="battery_eclipse", title="Battery energy for eclipse", status=PASS,
            actual_value=need, limit_value=batt["value_wh"],
            message=f"Eclipse needs {need:.1f} Wh; {batt['value_wh']:.1f} Wh is usable.", **b_base))

    # 3. EPS output limit against peak simultaneous demand
    e_base = dict(base, unit="W", assumptions=[mode_note, "Peak demand = all known consumers on at once "
                                                          "(worst case)."])
    if sel.eps is None:
        results.append(ConstraintResult(
            id="eps_output", title="Power conditioning output", status=WARNING,
            **dict(e_base, severity=SOFT),
            message="No power conditioning unit (EPS) is selected, so its output limit is not checked."))
    elif sel.eps.get("max_output_w") is None:
        results.append(ConstraintResult(
            id="eps_output", title="Power conditioning output", status=NOT_EVALUATED,
            affected_component_ids=[sel.eps["id"]], message="The EPS maximum output is not published.", **e_base))
    else:
        limit, peak = sel.eps["max_output_w"], demand["known_peak_w"]
        if peak > limit:
            status, msg = FAIL, f"Peak demand {peak:.1f} W exceeds the {sel.eps['id']} output limit of {limit:g} W."
        elif demand["unknown_ids"]:
            status, msg = NOT_EVALUATED, (f"Known peak demand {peak:.1f} W is within {limit:g} W, but the draw of "
                                          f"{', '.join(demand['unknown_ids'])} is unknown.")
        else:
            status, msg = PASS, f"Peak demand {peak:.1f} W is within the {sel.eps['id']} output limit of {limit:g} W."
        results.append(ConstraintResult(id="eps_output", title="Power conditioning output", status=status,
                                        actual_value=peak, limit_value=limit,
                                        affected_component_ids=[sel.eps["id"]], message=msg, **e_base))

    # 4. platform figure as a cap, never as extra generation
    c_base = dict(base, assumptions=[mode_note, "The platform payload power figure is used as a limit on "
                                                "demand, not as additional generated power."] + d_assume)
    results.append(_compare("platform_power_cap", "Platform payload power cap", demand,
                            sel.platform.get("payload_average_power_w"), "the platform payload power cap", c_base))
    return results


def check_power(sel: Selection, params: ScenarioParams) -> tuple[list[ConstraintResult], dict]:
    demand = demand_summary(sel, params)
    results = (check_power_mode_a(sel, params, demand) if sel.power_mode == MODE_A
               else check_power_mode_b(sel, params, demand))
    info = {"mode": sel.power_mode, "demand": demand}
    if sel.power_mode != MODE_A:
        info["generation"] = generation_avg_w(sel, params)
        info["battery"] = usable_battery_wh(sel, params)
    return results, info


def power_margin_fraction(sel: Selection, demand: dict, params: ScenarioParams) -> Optional[float]:
    """Margin against the binding supply figure. None when demand is only partly known."""
    if demand["unknown_ids"]:
        return None
    limit = sel.platform.get("payload_average_power_w")
    if sel.power_mode != MODE_A:
        gen = generation_avg_w(sel, params)["value_w"]
        if gen is None:
            return None
        limit = gen if limit is None else min(limit, gen)
    if not limit:
        return None
    return round((limit - demand["known_avg_w"]) / limit, 6)


__all__ = ["demand_items", "demand_summary", "check_power", "check_power_mode_a", "check_power_mode_b",
           "generation_avg_w", "usable_battery_wh", "power_margin_fraction", "GAMEPLAY"]
