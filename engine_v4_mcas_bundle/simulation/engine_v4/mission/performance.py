"""Objective-specific science rules.

These are transparent gameplay rules checked against published instrument
capabilities. They are NOT a scientific information-gain or mutual-information
calculation: the dataset has no measurement or noise model.
"""
from __future__ import annotations

from typing import Optional

from ..configuration import ScenarioParams, Selection


def relevant_instruments(sel: Selection, params: ScenarioParams) -> list[dict]:
    families = params.science.required_instrument_families_any
    if not families:
        return list(sel.instruments)
    return [i for i in sel.instruments if i.get("family") in families]


def _text(inst: dict) -> str:
    return " ".join(str(inst.get(k) or "") for k in ("spectral_bands", "instrument_type", "family")).lower()


def _rule(rule_id: str, title: str, score: Optional[float], reason: str) -> dict:
    return {"id": rule_id, "title": title, "score": None if score is None else round(score, 4),
            "evaluable": score is not None, "reason": reason}


def science_performance(sel: Selection, params: ScenarioParams, at_orbit: list[dict]) -> dict:
    req = params.science
    relevant = relevant_instruments(sel, params)
    by_id = {r["id"]: r for r in at_orbit}
    rules = []

    if req.required_instrument_families_any:
        ok = bool(relevant)
        rules.append(_rule("instrument_family", "Required instrument family on board", 1.0 if ok else 0.0,
                           (f"{', '.join(i['id'] for i in relevant)} belong(s) to a required family."
                            if ok else "No selected instrument is in a required family ("
                            + ", ".join(req.required_instrument_families_any) + ").")))

    if req.required_spectral_keywords_any:
        hits = [i["id"] for i in sel.instruments
                if any(k.lower() in _text(i) for k in req.required_spectral_keywords_any)]
        rules.append(_rule("spectral_capability", "Required spectral capability", 1.0 if hits else 0.0,
                           (f"{', '.join(hits)} provide(s) the required spectral capability."
                            if hits else "No selected instrument lists the required spectral capability ("
                            + ", ".join(req.required_spectral_keywords_any) + ").")))

    # resolution and swath are judged on the single best relevant instrument
    best_id, best_pair, best_mean = None, (None, None), -1.0
    for inst in relevant:
        row = by_id.get(inst["id"], {})
        g = _ratio_score(req.max_gsd_m, row.get("gsd_m_at_orbit"), lower_is_better=True)
        s = _ratio_score(req.min_swath_km, row.get("swath_km_at_orbit"), lower_is_better=False)
        parts = [v for v in (g, s) if v is not None]
        if parts and sum(parts) / len(parts) > best_mean:
            best_id, best_pair, best_mean = inst["id"], (g, s), sum(parts) / len(parts)
    if req.max_gsd_m is not None:
        g = best_pair[0]
        row = by_id.get(best_id, {})
        rules.append(_rule(
            "ground_resolution", "Ground resolution at the selected orbit", g,
            ("No relevant instrument has a published GSD, so resolution is not evaluated." if g is None else
             f"{best_id}: {row.get('gsd_m_at_orbit'):g} m at this orbit against a requirement of "
             f"{req.max_gsd_m:g} m or better.")))
    if req.min_swath_km is not None:
        s = best_pair[1]
        row = by_id.get(best_id, {})
        rules.append(_rule(
            "swath", "Swath at the selected orbit", s,
            ("No relevant instrument has a published swath, so coverage is not evaluated." if s is None else
             f"{best_id}: {row.get('swath_km_at_orbit'):g} km at this orbit against a requirement of "
             f"{req.min_swath_km:g} km or wider.")))

    if req.prefer_sun_synchronous is not None:
        match = bool(sel.orbit.get("sun_synchronous")) == req.prefer_sun_synchronous
        want = "sun-synchronous" if req.prefer_sun_synchronous else "non-sun-synchronous"
        rules.append(_rule("orbit_choice", "Appropriate orbit", 1.0 if match else 0.0,
                           f"The objective calls for a {want} orbit; {sel.orbit['name']} "
                           f"{'matches' if match else 'does not match'}."))

    evaluable = [r["score"] for r in rules if r["evaluable"]]
    return {
        "model": "gameplay_rules",
        "model_note": "Rule-based science score from published capabilities. Not an information-gain model.",
        "rules": rules,
        "score": round(sum(evaluable) / len(evaluable), 4) if evaluable else None,
        "has_required_instrument": bool(relevant),
        "primary_instrument_id": best_id,
        "relevant_instrument_ids": [i["id"] for i in relevant],
    }


def _ratio_score(requirement: Optional[float], value: Optional[float], lower_is_better: bool) -> Optional[float]:
    """1.0 when the requirement is met, otherwise the shortfall ratio in (0, 1). None if unknown."""
    if requirement is None or value is None or value <= 0 or requirement <= 0:
        return None
    ratio = requirement / value if lower_is_better else value / requirement
    return max(0.0, min(1.0, ratio))
