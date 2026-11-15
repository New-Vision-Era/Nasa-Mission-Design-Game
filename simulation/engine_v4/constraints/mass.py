"""Payload mass budget (hard) and total spacecraft mass.

Payload mass is NOT total spacecraft launch mass: platform bus_mass_kg is
unknown in equipment_v4, so total mass needs an explicit gameplay assumption.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..configuration import ScenarioParams, Selection
from ..results import (DERIVED, FAIL, GAMEPLAY, HARD, NOT_EVALUATED, PASS, PUBLISHED,
                       ConstraintResult, source_urls)


def component_mass_kg(category: str, rec: dict) -> Optional[float]:
    """Mass a component adds to the payload. None = unknown (never zero).

    Propulsion uses wet_mass_kg, which already includes propellant (v4 mass_rule);
    propellant mass is never added on top. Dry mass alone is not used as a substitute.
    """
    if category == "propulsion_systems":
        return rec.get("wet_mass_kg")
    return rec.get("mass_kg")


@dataclass
class MassBudget:
    known_kg: float
    unknown_ids: list[str] = field(default_factory=list)
    items: list[dict] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.unknown_ids


def payload_mass(sel: Selection, params: ScenarioParams) -> MassBudget:
    budget = MassBudget(known_kg=0.0)
    for category, rec in sel.carried(params.count_subsystems_in_payload_mass):
        mass = component_mass_kg(category, rec)
        budget.items.append({"id": rec["id"], "category": category, "mass_kg": mass})
        if mass is None:
            budget.unknown_ids.append(rec["id"])
        else:
            budget.known_kg += mass
    budget.known_kg = round(budget.known_kg, 6)
    return budget


def check_payload_mass(sel: Selection, params: ScenarioParams) -> tuple[ConstraintResult, MassBudget]:
    budget = payload_mass(sel, params)
    limit = sel.platform.get("payload_mass_capacity_kg")
    assumptions = ["Payload mass only. This is not total spacecraft launch mass (bus mass is unknown)."]
    if params.count_subsystems_in_payload_mass:
        assumptions.append("Selected subsystems (ADCS, radios, propulsion, power parts) are counted against the "
                           "platform payload capacity. Whether the GSAT bus already includes such hardware is unknown.")
    recs = [r for _, r in sel.carried(params.count_subsystems_in_payload_mass)]
    base = dict(id="payload_mass", category="mass", title="Payload mass budget", severity=HARD,
                actual_value=budget.known_kg, limit_value=limit, unit="kg", value_kind=PUBLISHED,
                source_urls=source_urls(sel.platform, *recs), assumptions=assumptions,
                related_step="instruments")
    if limit is None:
        return ConstraintResult(status=NOT_EVALUATED, affected_component_ids=[sel.platform["id"]],
                                message="The platform's payload mass capacity is unknown.", **base), budget
    if budget.known_kg > limit:
        heavy = sorted((i for i in budget.items if i["mass_kg"] is not None),
                       key=lambda i: -i["mass_kg"])[:3]
        extra = (f" Components with unknown mass ({', '.join(budget.unknown_ids)}) would add more."
                 if budget.unknown_ids else "")
        return ConstraintResult(
            status=FAIL, affected_component_ids=[i["id"] for i in heavy],
            message=(f"Known payload mass {budget.known_kg:.2f} kg exceeds the {sel.platform['name']} capacity "
                     f"of {limit:g} kg. Heaviest items: "
                     + ", ".join(f"{i['id']} ({i['mass_kg']:g} kg)" for i in heavy) + "." + extra),
            **base), budget
    if budget.unknown_ids:
        return ConstraintResult(
            status=NOT_EVALUATED, affected_component_ids=list(budget.unknown_ids),
            message=(f"Known payload mass is {budget.known_kg:.2f} kg of {limit:g} kg, but the mass of "
                     f"{', '.join(budget.unknown_ids)} is not published. Unknown mass is not treated as zero, "
                     "so the budget cannot be confirmed."),
            **base), budget
    return ConstraintResult(
        status=PASS, affected_component_ids=[],
        message=f"Payload mass {budget.known_kg:.2f} kg is within the {limit:g} kg capacity "
                f"({(1 - budget.known_kg / limit) * 100:.0f}% margin)." if limit else "Payload mass is within capacity.",
        **base), budget


def total_spacecraft_mass(budget: MassBudget, params: ScenarioParams) -> dict:
    """Total launch mass = bus + payload. Only available with a labelled bus-mass assumption."""
    if params.bus_mass_kg_assumption is None:
        return {"value_kg": None, "value_kind": None,
                "reason": "Platform bus_mass_kg is unknown in the dataset and the scenario gives no "
                          "bus-mass assumption, so total spacecraft mass cannot be computed."}
    if not budget.complete:
        return {"value_kg": None, "value_kind": None,
                "reason": f"Mass of {', '.join(budget.unknown_ids)} is unknown, so total spacecraft mass "
                          "cannot be computed."}
    return {"value_kg": round(params.bus_mass_kg_assumption + budget.known_kg, 6), "value_kind": GAMEPLAY,
            "reason": f"Bus mass {params.bus_mass_kg_assumption:g} kg is a GAMEPLAY ASSUMPTION from the scenario "
                      "(not a published GSAT value), plus published payload masses."}


def mass_margin_fraction(budget: MassBudget, sel: Selection) -> Optional[float]:
    limit = sel.platform.get("payload_mass_capacity_kg")
    if not limit or not budget.complete:
        return None
    return round((limit - budget.known_kg) / limit, 6)


__all__ = ["component_mass_kg", "MassBudget", "payload_mass", "check_payload_mass",
           "total_spacecraft_mass", "mass_margin_fraction", "DERIVED"]
