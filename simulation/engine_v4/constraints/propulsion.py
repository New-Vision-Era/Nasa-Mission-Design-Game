"""Propulsion: approximate delta-v and burn time (soft unless the scenario sets a minimum)."""
from __future__ import annotations

from typing import Optional

from ..configuration import ScenarioParams, Selection
from ..results import (DERIVED, FAIL, GAMEPLAY, HARD, NOT_EVALUATED, PASS, SOFT, ConstraintResult,
                       source_urls)


def delta_v_m_s(total_impulse_ns: Optional[float], spacecraft_mass_kg: Optional[float]) -> Optional[float]:
    """delta_v = total_impulse / spacecraft_mass. Impulse approximation, NOT the rocket equation."""
    if total_impulse_ns is None or not spacecraft_mass_kg:
        return None
    return total_impulse_ns / spacecraft_mass_kg


def burn_time_s(total_impulse_ns: Optional[float], thrust_n: Optional[float]) -> Optional[float]:
    """burn_time = total_impulse / thrust."""
    if total_impulse_ns is None or not thrust_n:
        return None
    return total_impulse_ns / thrust_n


def check_propulsion(sel: Selection, params: ScenarioParams, total_mass: dict) -> tuple[list[ConstraintResult], dict]:
    need = params.min_delta_v_m_s
    prop = sel.propulsion
    info = {"delta_v_m_s": None, "burn_time_s": None, "burn_time_days": None}
    if prop is None:
        if need:
            return [ConstraintResult(
                id="delta_v", category="propulsion", title="Delta-v requirement", status=FAIL, severity=HARD,
                limit_value=need, unit="m/s", value_kind="published", related_step="propulsion",
                message=f"The scenario needs {need:g} m/s of delta-v but no propulsion system is selected.")], info
        return [], info

    burn = burn_time_s(prop.get("total_impulse_ns"), prop.get("thrust_n"))
    dv = delta_v_m_s(prop.get("total_impulse_ns"), total_mass.get("value_kg"))
    info.update(delta_v_m_s=None if dv is None else round(dv, 3),
                burn_time_s=None if burn is None else round(burn, 1),
                burn_time_days=None if burn is None else round(burn / 86400.0, 3))
    assumptions = ["Delta-v uses total impulse / spacecraft mass, valid when propellant is a small share of "
                   "the mass. It is not an exact rocket-equation result.",
                   prop.get("mass_rule") or "wet_mass_kg already includes propellant."]
    base = dict(id="delta_v", category="propulsion", title="Delta-v and burn time", unit="m/s",
                limit_value=need, affected_component_ids=[prop["id"]], source_urls=source_urls(prop),
                severity=HARD if need else SOFT, related_step="propulsion")
    burn_txt = "" if burn is None else f" Using all of it takes about {_duration(burn)} of thrusting."
    if dv is None:
        why = (total_mass.get("reason") if prop.get("total_impulse_ns") is not None
               else "Total impulse is not published.")
        return [ConstraintResult(status=NOT_EVALUATED, value_kind=DERIVED, assumptions=assumptions,
                                 message=f"Delta-v is not evaluated. {why}{burn_txt}", **base)], info
    assumptions.append(total_mass.get("reason"))
    mass_kind = total_mass.get("value_kind") or GAMEPLAY
    if need and dv < need:
        return [ConstraintResult(status=FAIL, actual_value=round(dv, 2), value_kind=mass_kind,
                                 assumptions=assumptions,
                                 message=f"About {dv:.1f} m/s available; the scenario needs {need:g} m/s.{burn_txt}",
                                 **base)], info
    return [ConstraintResult(status=PASS, actual_value=round(dv, 2), value_kind=mass_kind, assumptions=assumptions,
                             message=f"About {dv:.1f} m/s of delta-v available"
                                     + (f" (needs {need:g} m/s)." if need else ".") + burn_txt, **base)], info


def _duration(seconds: float) -> str:
    if seconds < 3600:
        return f"{seconds / 60:.0f} minutes"
    if seconds < 2 * 86400:
        return f"{seconds / 3600:.1f} hours"
    return f"{seconds / 86400:.0f} days"
