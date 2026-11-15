"""Orbit summary and instrument performance at the selected orbit.

Orbit values are read from equipment_v4.json (all derived there: circular orbit,
spherical Earth). Orbital mechanics is not recomputed. Orbital lifetime is
unknown in the dataset and is not calculated.
"""
from __future__ import annotations

from ..configuration import Selection
from ..results import DERIVED

# Families for which the small-angle nadir scaling with altitude is applied.
SCALED_FAMILIES = ("optical_rgb", "optical_multispectral", "optical_hyperspectral", "infrared")

ORBIT_FIELDS = ("altitude_km", "inclination_deg", "sun_synchronous", "period_min", "orbits_per_day",
                "ground_track_speed_km_s", "max_eclipse_fraction", "max_eclipse_min",
                "max_pass_duration_min_10deg", "resolution_scale_vs_500km", "orbital_lifetime_years")


def orbit_summary(orbit: dict) -> dict:
    out = {"id": orbit["id"], "name": orbit.get("name"), "value_kind": DERIVED}
    out.update({f: orbit.get(f) for f in ORBIT_FIELDS})
    out["notes"] = ["All orbit values are derived (circular orbit, spherical Earth), not published.",
                    "Orbital lifetime is not modelled: it is unknown in the dataset."]
    return out


def instrument_at_orbit(inst: dict, orbit: dict) -> dict:
    """gsd_at_orbit = gsd_m * scale; swath_at_orbit = swath_km * scale (optical / infrared imagers only)."""
    scale = orbit.get("resolution_scale_vs_500km")
    gsd, swath = inst.get("gsd_m"), inst.get("swath_km")
    scaled = inst.get("family") in SCALED_FAMILIES and scale is not None
    out = {
        "id": inst["id"], "family": inst.get("family"),
        "gsd_m_reference": gsd, "swath_km_reference": swath,
        "gsd_m_at_orbit": None if gsd is None else (round(gsd * scale, 4) if scaled else gsd),
        "swath_km_at_orbit": None if swath is None else (round(swath * scale, 4) if scaled else swath),
        "scaled_with_altitude": bool(scaled and (gsd is not None or swath is not None)),
        "value_kind": DERIVED if scaled else "published",
        "value_notes": inst.get("value_notes"),
    }
    if not scaled:
        out["note"] = ("Not scaled with altitude: the linear nadir approximation is applied to optical and "
                       "infrared imagers only. Reference values are shown; see value_notes for their altitude.")
    else:
        out["note"] = "Small-angle nadir approximation; ignores Earth curvature."
    return out


def coverage_rate_km2_s(inst_at_orbit: dict, orbit: dict):
    """Area imaged per second while operating = swath * ground-track speed."""
    swath, speed = inst_at_orbit.get("swath_km_at_orbit"), orbit.get("ground_track_speed_km_s")
    if swath is None or speed is None:
        return None
    return round(swath * speed, 4)


def instruments_at_orbit(sel: Selection) -> list[dict]:
    out = []
    for inst in sel.instruments:
        row = instrument_at_orbit(inst, sel.orbit)
        row["coverage_rate_km2_s"] = coverage_rate_km2_s(row, sel.orbit)
        out.append(row)
    return out
