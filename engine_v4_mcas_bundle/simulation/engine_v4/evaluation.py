"""Run every engineering check for one resolved selection."""
from __future__ import annotations

from typing import Any

from .configuration import ScenarioParams, Selection
from .constraints import communications, launch, mass, orbit, pointing, power, propulsion, volume
from .results import ConstraintResult, overall_feasibility


def evaluate_engineering(sel: Selection, params: ScenarioParams) -> dict[str, Any]:
    """Return constraints, feasibility and the resource figures other modules need.

    Pure and deterministic: no randomness, no I/O.
    """
    results: list[ConstraintResult] = []

    mass_result, budget = mass.check_payload_mass(sel, params)
    results.append(mass_result)
    total_mass = mass.total_spacecraft_mass(budget, params)

    results.append(volume.check_volume(sel, params))

    power_results, power_info = power.check_power(sel, params)
    results += power_results

    results.append(communications.check_command_link(sel, params))
    results.append(communications.check_ground_station(sel, params))
    downlink_result, best = communications.check_downlink_capacity(sel, params)
    results.append(downlink_result)
    balance_result, data_info = communications.check_data_balance(sel, params, best)
    results.append(balance_result)

    at_orbit = orbit.instruments_at_orbit(sel)
    results += pointing.check_pointing(sel, params, at_orbit)

    prop_results, prop_info = propulsion.check_propulsion(sel, params, total_mass)
    results += prop_results

    results.append(launch.check_orbit_support(sel))
    results.append(launch.check_launch_mass(sel, params, total_mass))
    price = launch.launch_price(sel, total_mass)
    budget_result, cost_info = launch.check_budget(sel, params, price)
    results.append(budget_result)

    demand = power_info["demand"]
    resources = {
        "payload_mass_known_kg": {"value": budget.known_kg, "unit": "kg", "complete": budget.complete,
                                  "unknown_component_ids": budget.unknown_ids,
                                  "note": "Payload mass only, not total spacecraft mass."},
        "payload_mass_capacity_kg": {"value": sel.platform.get("payload_mass_capacity_kg"), "unit": "kg",
                                     "value_kind": "published"},
        "total_spacecraft_mass_kg": {"value": total_mass["value_kg"], "unit": "kg",
                                     "value_kind": total_mass["value_kind"], "note": total_mass["reason"]},
        "power_demand_avg_w": {"value": demand["known_avg_w"], "unit": "W",
                               "complete": not demand["unknown_ids"],
                               "unknown_component_ids": demand["unknown_ids"],
                               "upper_bound_component_ids": demand["upper_bound_ids"]},
        "payload_power_available_w": {"value": sel.platform.get("payload_average_power_w"), "unit": "W",
                                      "value_kind": "published"},
        "downlink_bits_per_day": {"value": best["bits_per_day"], "unit": "bits/day", "radio_id": best["radio_id"],
                                  "pass_seconds_per_day": best["pass_seconds_per_day"], "value_kind": "mixed"},
        "data_generated_bits_per_day": {"value": data_info["generated_bits_per_day"], "unit": "bits/day"},
        "launch_price_usd": {"value": price["value_usd"], "unit": "USD", "value_kind": price["value_kind"],
                             "note": price["reason"]},
        "known_cost_usd": {"value": cost_info["known_cost_usd"], "unit": "USD",
                           "note": "Platform + launch (+ components with a published USD price). "
                                   "Unpriced components are not included and not counted as zero.",
                           "unpriced_component_ids": cost_info["unpriced_component_ids"]},
        "budget_usd": {"value": params.budget_usd, "unit": "USD", "value_kind": "gameplay_assumption"},
    }
    if "generation" in power_info:
        resources["power_generation_avg_w"] = {"value": power_info["generation"]["value_w"], "unit": "W",
                                               "value_kind": "mixed"}
        resources["battery_usable_wh"] = {"value": power_info["battery"]["value_wh"], "unit": "Wh",
                                          "value_kind": "mixed"}

    return {
        "constraints": results,
        "feasibility": overall_feasibility(results),
        "resources": resources,
        "orbit": orbit.orbit_summary(sel.orbit),
        "instruments_at_orbit": at_orbit,
        "power": power_info,
        "propulsion": prop_info,
        "data": data_info,
        "downlink": best,
        "cost": cost_info,
        "total_mass": total_mass,
        "margins": {
            "mass_margin_fraction": mass.mass_margin_fraction(budget, sel),
            "power_margin_fraction": power.power_margin_fraction(sel, demand, params),
        },
    }
