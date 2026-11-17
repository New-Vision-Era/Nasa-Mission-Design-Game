"""Payload mass budget (hard) and total spacecraft mass.

Payload mass is NOT total spacecraft launch mass. Total mass = platform bus mass
+ payload. Since equipment_v5, bus_mass_kg is filled for every platform, but it is
an estimate or a derived value (bus_mass_basis), not a manufacturer figure, and it
is dry. It carries a range (bus_mass_range_kg) that is reported with every result.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..configuration import ScenarioParams, Selection
from ..results import (DERIVED, ESTIMATE, FAIL, GAMEPLAY, HARD, NOT_EVALUATED, PASS, PUBLISHED,
                       ConstraintResult, source_urls)

_BASIS_KIND = {"published": PUBLISHED, "derived": DERIVED, "estimate": ESTIMATE}
_BASIS_TEXT = {"published": "a published value",
               "derived": "derived from published figures with an inference, not a manufacturer value",
               "estimate": "an estimate, not a manufacturer value"}
DRY_BUS_NOTE = ("Bus mass is dry: propellant in the bus's own propulsion, if any, is not published and is not "
                "counted, so total mass may be somewhat low.")


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
    assumptions = ["Payload mass only. This is not total spacecraft launch mass, which adds the platform bus "
                   "mass (see the launch mass check)."]
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


def bus_mass(platform: dict, params: ScenarioParams) -> dict:
    """Bus mass to use: a scenario override (gameplay) if set, else the dataset value and its basis.

    value_kg None = unknown. range_kg is [low, high] when the dataset gives a valid range.
    """
    override = params.bus_mass_kg_assumption
    if override is not None:
        return {"value_kg": float(override), "value_kind": GAMEPLAY, "basis": "gameplay_assumption",
                "range_kg": None, "source_urls": [],
                "text": f"Bus mass {override:g} kg is set by the scenario (GAMEPLAY ASSUMPTION, overriding the "
                        "dataset value)."}
    value = platform.get("bus_mass_kg")
    if value is None:
        return {"value_kg": None, "value_kind": None, "basis": None, "range_kg": None, "source_urls": [],
                "text": f"The bus mass of {platform.get('name', platform['id'])} is unknown in the dataset."}
    basis = platform.get("bus_mass_basis") or "published"
    rng = platform.get("bus_mass_range_kg")
    valid = (isinstance(rng, (list, tuple)) and len(rng) == 2
             and all(isinstance(x, (int, float)) and not isinstance(x, bool) and x >= 0 for x in rng)
             and rng[0] <= rng[1])
    range_kg = [float(rng[0]), float(rng[1])] if valid else None
    range_txt = f", range {range_kg[0]:g}-{range_kg[1]:g} kg" if range_kg else ""
    return {"value_kg": float(value), "value_kind": _BASIS_KIND.get(basis, ESTIMATE), "basis": basis,
            "range_kg": range_kg,
            "source_urls": list(platform.get("bus_mass_sources") or platform.get("source_urls") or []),
            "text": f"{platform.get('name', platform['id'])} bus mass {value:g} kg{range_txt} is "
                    f"{_BASIS_TEXT.get(basis, basis)}."}


def total_spacecraft_mass(budget: MassBudget, params: ScenarioParams, platform: dict) -> dict:
    """Total launch mass = bus mass + payload mass. None when either part is unknown."""
    bus = bus_mass(platform, params)
    out = {"value_kg": None, "value_kind": None, "range_kg": None, "bus_mass_kg": bus["value_kg"],
           "bus_mass_basis": bus["basis"], "bus_mass_range_kg": bus["range_kg"],
           "payload_mass_kg": budget.known_kg, "source_urls": bus["source_urls"]}
    if bus["value_kg"] is None:
        out["reason"] = bus["text"] + " Total spacecraft mass cannot be computed."
        return out
    if not budget.complete:
        out["reason"] = (f"Mass of {', '.join(budget.unknown_ids)} is unknown, so total spacecraft mass "
                         "cannot be computed.")
        return out
    out["value_kg"] = round(bus["value_kg"] + budget.known_kg, 6)
    out["value_kind"] = bus["value_kind"]
    if bus["range_kg"]:
        out["range_kg"] = [round(x + budget.known_kg, 6) for x in bus["range_kg"]]
    out["reason"] = (f"Total = bus {bus['value_kg']:g} kg + payload {budget.known_kg:.2f} kg. {bus['text']} "
                     + ("" if bus["basis"] == "gameplay_assumption" else DRY_BUS_NOTE))
    return out


def mass_margin_fraction(budget: MassBudget, sel: Selection) -> Optional[float]:
    limit = sel.platform.get("payload_mass_capacity_kg")
    if not limit or not budget.complete:
        return None
    return round((limit - budget.known_kg) / limit, 6)


__all__ = ["component_mass_kg", "MassBudget", "payload_mass", "check_payload_mass",
           "total_spacecraft_mass", "bus_mass", "mass_margin_fraction", "DRY_BUS_NOTE"]
