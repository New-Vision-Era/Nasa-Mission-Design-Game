"""ADCS pointing: ground offset and comparison with swath (soft for the MVP)."""
from __future__ import annotations

import math
from typing import Optional

from ..configuration import ScenarioParams, Selection
from ..results import (DERIVED, FAIL, HARD, NOT_EVALUATED, PASS, SOFT, WARNING, ConstraintResult,
                       source_urls)

COMPARABLE_METRICS = ("upper_bound", "per_axis_worst")


def pointing_offset_m(altitude_km: Optional[float], accuracy_deg: Optional[float]) -> Optional[float]:
    """pointing_offset_m = altitude_km * 1000 * tan(pointing_accuracy_deg)."""
    if altitude_km is None or accuracy_deg is None:
        return None
    return altitude_km * 1000.0 * math.tan(math.radians(accuracy_deg))


def check_pointing(sel: Selection, params: ScenarioParams, at_orbit: list[dict]) -> list[ConstraintResult]:
    adcs = sel.adcs
    accuracy, metric = adcs.get("pointing_accuracy_deg"), adcs.get("pointing_metric")
    offset = pointing_offset_m(sel.orbit.get("altitude_km"), accuracy)
    conditions = f"Pointing figure: {metric or 'unspecified'} ({adcs.get('pointing_conditions') or 'no conditions stated'})."
    base = dict(category="pointing", unit="m", value_kind=DERIVED, source_urls=source_urls(adcs, sel.orbit),
                affected_component_ids=[adcs["id"]], related_step="adcs")
    results = []

    # swath comparison (always soft)
    s_base = dict(base, id="pointing_vs_swath", title="Pointing error vs instrument swath", severity=SOFT,
                  assumptions=[conditions, f"Warning threshold: offset above {params.pointing_swath_warning_fraction:g} "
                                           "of the swath (gameplay parameter)."])
    if offset is None:
        results.append(ConstraintResult(status=NOT_EVALUATED, message="ADCS pointing accuracy or orbit altitude "
                                                                      "is unknown.", **s_base))
    else:
        swaths = [(r["id"], r["swath_km_at_orbit"]) for r in at_orbit if r.get("swath_km_at_orbit")]
        risky = [(i, s) for i, s in swaths if offset > params.pointing_swath_warning_fraction * s * 1000.0]
        caveat = ("" if metric in COMPARABLE_METRICS else
                  f" The figure is '{metric or 'unspecified'}', not a guaranteed bound, so the real error can be larger.")
        if not swaths:
            results.append(ConstraintResult(
                status=PASS, actual_value=round(offset, 1),
                message=f"Pointing error is about {offset:,.0f} m on the ground. No selected instrument has a "
                        f"known swath to compare with.{caveat}", **s_base))
        elif risky:
            worst = max(risky, key=lambda t: offset / (t[1] * 1000.0))
            results.append(ConstraintResult(
                status=WARNING, actual_value=round(offset, 1), limit_value=round(worst[1] * 1000.0, 1),
                message=f"Pointing error of about {offset / 1000:.1f} km is {offset / (worst[1] * 10):.0f}% of the "
                        f"{worst[1]:g} km swath of {worst[0]}: targets may be missed.{caveat}",
                **dict(s_base, affected_component_ids=[adcs["id"]] + [i for i, _ in risky])))
        else:
            narrow = min(swaths, key=lambda t: t[1])
            results.append(ConstraintResult(
                status=PASS, actual_value=round(offset, 1), limit_value=round(narrow[1] * 1000.0, 1),
                message=f"Pointing error of about {offset:,.0f} m is small against the narrowest swath "
                        f"({narrow[1]:g} km, {narrow[0]}).{caveat}", **s_base))

    # scenario-defined hard pointing requirement
    req = params.hard_pointing_requirement_deg
    if req is not None:
        r_base = dict(base, id="pointing_requirement", title="Scenario pointing requirement", severity=HARD,
                      unit="deg", value_kind="published", actual_value=accuracy, limit_value=req,
                      assumptions=[conditions, "The requirement is a scenario parameter."])
        if accuracy is None or metric not in COMPARABLE_METRICS:
            results.append(ConstraintResult(
                status=NOT_EVALUATED,
                message=f"The pointing figure of {adcs['id']} is '{metric or 'unspecified'}', which cannot be "
                        f"compared directly with a hard requirement of {req:g} deg. Only upper-bound or "
                        "worst-axis figures can.", **r_base))
        elif accuracy <= req:
            results.append(ConstraintResult(status=PASS, message=f"{accuracy:g} deg ({metric}) meets the "
                                                                 f"{req:g} deg requirement.", **r_base))
        else:
            results.append(ConstraintResult(status=FAIL, message=f"{accuracy:g} deg ({metric}) does not meet the "
                                                                 f"{req:g} deg requirement.", **r_base))
    return results
