"""Launch vehicle compatibility, launch price and the budget check.

Capacity rule (v4): a capacity point applies only to its own orbit type AND
altitude. A LEO figure is never an SSO capacity; a 500 km point never covers 700 km.
No capacity is invented where the dataset has none.
"""
from __future__ import annotations

from typing import Optional

from ..configuration import ScenarioParams, Selection
from ..results import (FAIL, GAMEPLAY, HARD, MIXED, NOT_EVALUATED, PASS, PUBLISHED, ConstraintResult,
                       source_urls)


def orbit_type(orbit: dict) -> str:
    return "sso" if orbit.get("sun_synchronous") else "leo"


def matching_capacity_point(launcher: dict, orbit: dict) -> Optional[dict]:
    """The capacity point with the same orbit type and the same altitude, or None."""
    for point in launcher.get("capacity_points") or []:
        if (point.get("orbit") == orbit_type(orbit) and point.get("altitude_km") is not None
                and point.get("altitude_km") == orbit.get("altitude_km")):
            return point
    return None


def check_orbit_support(sel: Selection) -> ConstraintResult:
    lv, orbit = sel.launcher, sel.orbit
    supported = orbit["id"] in (lv.get("orbit_ids_supported") or [])
    basis = (lv.get("orbit_support_basis") or {}).get(orbit["id"])
    base = dict(id="launch_orbit_support", category="launch", title="Launcher reaches the selected orbit",
                severity=HARD, affected_component_ids=[lv["id"], orbit["id"]],
                source_urls=source_urls(lv), related_step="launch_vehicle")
    if not supported:
        return ConstraintResult(
            status=FAIL, value_kind=PUBLISHED,
            message=f"{lv['name']} is not listed for {orbit['name']}. Supported: "
                    f"{', '.join(lv.get('orbit_ids_supported') or []) or 'none'}.", **base)
    extra = ("" if lv.get("customer_chooses_orbit", True) else
             " Note: on this launcher the provider picks the injection orbit, not the customer.")
    if basis == "published_capacity_point":
        return ConstraintResult(status=PASS, value_kind=PUBLISHED,
                                message=f"{lv['name']} has a published capacity point for {orbit['name']}.{extra}",
                                **base)
    return ConstraintResult(
        status=PASS, value_kind=GAMEPLAY,
        assumptions=[f"Support of {orbit['id']} by {lv['id']} is a GAMEPLAY ASSUMPTION in the dataset "
                     "(orbit_support_basis), not a published capability."],
        message=f"{lv['name']} is listed for {orbit['name']} as a gameplay assumption, not from a published "
                f"capacity point.{extra}", **base)


def check_launch_mass(sel: Selection, params: ScenarioParams, total_mass: dict) -> ConstraintResult:
    lv, orbit = sel.launcher, sel.orbit
    base = dict(id="launch_mass", category="launch", title="Launch mass capacity", severity=HARD, unit="kg",
                affected_component_ids=[lv["id"]], source_urls=source_urls(lv, sel.platform),
                related_step="launch_vehicle", actual_value=total_mass.get("value_kg"))
    rule = lv.get("capacity_rule") or "A capacity point applies only to its own orbit type and altitude."
    point = matching_capacity_point(lv, orbit)
    limit, limit_kind, limit_note = None, None, None
    if point is not None:
        limit, limit_kind = point["mass_kg"], PUBLISHED
        limit_note = f"published capacity of {limit:g} kg to {orbit_type(orbit).upper()} {orbit['altitude_km']:g} km"
    elif lv.get("family") == "rideshare" and params.rideshare_mass_cap_kg_assumption is not None:
        limit, limit_kind = params.rideshare_mass_cap_kg_assumption, GAMEPLAY
        limit_note = f"rideshare mass cap of {limit:g} kg (GAMEPLAY ASSUMPTION; no cap is published)"
    if limit is None:
        points = "; ".join(
            f"{p.get('orbit')} {p.get('altitude_km') if p.get('altitude_km') is not None else 'altitude not given'}"
            f"{' km' if p.get('altitude_km') is not None else ''}: {p.get('mass_kg')} kg"
            for p in lv.get("capacity_points") or []) or "none"
        return ConstraintResult(
            status=NOT_EVALUATED, value_kind=PUBLISHED, assumptions=[rule],
            message=f"{lv['name']} has no capacity point for {orbit_type(orbit).upper()} at "
                    f"{orbit['altitude_km']:g} km (its points: {points}). A figure for another orbit type or "
                    "altitude is not used, and no capacity is invented.", **base)
    base["limit_value"] = limit
    if total_mass.get("value_kg") is None:
        return ConstraintResult(
            status=NOT_EVALUATED, value_kind=limit_kind, assumptions=[rule],
            message=f"The launcher has a {limit_note}, but total spacecraft launch mass is not known. "
                    f"{total_mass.get('reason')}", **base)
    mass = total_mass["value_kg"]
    assumptions = [rule, total_mass.get("reason")]
    kind = GAMEPLAY  # total mass rests on the bus-mass assumption
    if mass > limit:
        return ConstraintResult(status=FAIL, value_kind=kind, assumptions=assumptions,
                                message=f"Spacecraft mass {mass:.1f} kg exceeds the {limit_note}.", **base)
    return ConstraintResult(status=PASS, value_kind=kind, assumptions=assumptions,
                            message=f"Spacecraft mass {mass:.1f} kg is within the {limit_note}.", **base)


def launch_price(sel: Selection, total_mass: dict) -> dict:
    """Launch price in USD. Rideshare uses its published price model when mass is known."""
    lv = sel.launcher
    model = lv.get("price_model")
    if model:
        mass = total_mass.get("value_kg")
        if mass is None:
            return {"value_usd": None, "lower_bound_usd": model.get("base_usd"), "value_kind": None,
                    "reason": "Rideshare is priced by mass, and total spacecraft mass is unknown. "
                              f"The price is at least {model.get('base_usd'):,} USD."}
        price = model["base_usd"] + model["extra_usd_per_kg"] * max(0.0, mass - model["base_mass_kg"])
        return {"value_usd": round(price, 2), "lower_bound_usd": round(price, 2), "value_kind": GAMEPLAY,
                "reason": f"Published price model ({model['base_usd']:,} USD up to {model['base_mass_kg']:g} kg, "
                          f"+{model['extra_usd_per_kg']:,} USD/kg) applied to a mass that includes the bus-mass "
                          "gameplay assumption."}
    if lv.get("price_usd") is not None:
        kind = PUBLISHED if lv.get("price_type") == "published" else "estimate"
        return {"value_usd": lv["price_usd"], "lower_bound_usd": lv["price_usd"], "value_kind": kind,
                "reason": f"Launcher price_type: {lv.get('price_type')}."}
    return {"value_usd": None, "lower_bound_usd": None, "value_kind": None,
            "reason": f"No sale price is published for {lv['name']} (price_type: {lv.get('price_type')}). "
                      "Cost estimates in the dataset are not sale prices and are not used."}


def check_budget(sel: Selection, params: ScenarioParams, price: dict) -> tuple[ConstraintResult, dict]:
    """Budget against platform + launch only: the two cost items with published prices.

    Component prices are almost all unpublished; they are listed as unknown and are
    NOT counted as zero inside a 'total mission cost'.
    """
    unpriced = [r["id"] for _, r in sel.carried() if r.get("price_usd") is None]
    priced = [(r["id"], r["price_usd"]) for _, r in sel.carried() if r.get("price_usd") is not None]
    platform_price = sel.platform.get("price_usd")
    scope = ("Budget scope: platform price + launch price"
             + (" + the few components with a published USD price" if priced else "") + ". "
             f"{len(unpriced)} selected component(s) have no published USD price and are outside this check; "
             "they are not counted as free.")
    info = {"platform_usd": platform_price, "launch_usd": price["value_usd"],
            "priced_components_usd": dict(priced), "unpriced_component_ids": unpriced,
            "known_cost_usd": None, "budget_usd": params.budget_usd}
    base = dict(id="budget", category="budget", title="Mission budget (platform and launch)", severity=HARD,
                unit="USD", limit_value=params.budget_usd, value_kind=MIXED, assumptions=[scope, price["reason"]],
                source_urls=source_urls(sel.platform, sel.launcher), related_step="budget")
    if params.budget_usd is None:
        return ConstraintResult(status=NOT_EVALUATED, message="The scenario defines no budget.",
                                **dict(base, severity="soft")), info
    extras = sum(p for _, p in priced)
    if platform_price is None:
        return ConstraintResult(status=NOT_EVALUATED, message="The platform price is unknown.",
                                affected_component_ids=[sel.platform["id"]], **base), info
    if price["value_usd"] is None:
        floor = platform_price + extras + (price["lower_bound_usd"] or 0)
        if price["lower_bound_usd"] is not None and floor > params.budget_usd:
            return ConstraintResult(
                status=FAIL, actual_value=floor, affected_component_ids=[sel.platform["id"], sel.launcher["id"]],
                message=f"Even the minimum known cost of {floor:,.0f} USD exceeds the {params.budget_usd:,.0f} "
                        "USD budget.", **base), info
        return ConstraintResult(
            status=NOT_EVALUATED, affected_component_ids=[sel.launcher["id"]],
            actual_value=floor if price["lower_bound_usd"] is not None else None,
            message=f"The launch price cannot be determined, so the budget is not evaluated. {price['reason']}",
            **base), info
    cost = platform_price + extras + price["value_usd"]
    info["known_cost_usd"] = cost
    if cost > params.budget_usd:
        return ConstraintResult(
            status=FAIL, actual_value=cost, affected_component_ids=[sel.platform["id"], sel.launcher["id"]],
            message=f"Platform ({platform_price:,.0f} USD) plus launch ({price['value_usd']:,.0f} USD) cost "
                    f"{cost:,.0f} USD, above the {params.budget_usd:,.0f} USD budget.", **base), info
    return ConstraintResult(
        status=PASS, actual_value=cost,
        message=f"Platform plus launch cost {cost:,.0f} USD of the {params.budget_usd:,.0f} USD budget.",
        **base), info
