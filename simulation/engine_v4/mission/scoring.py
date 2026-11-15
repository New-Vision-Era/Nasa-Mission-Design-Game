"""Transparent score out of 100, kept separate from feasibility.

Weights and every sub-rule are provisional GAMEPLAY choices, not NASA formulas.
A category that cannot be evaluated is excluded and the total is normalised over
the evaluable weight; `completeness` reports how much of the weight was evaluable.
Unknown values are never scored as zero or as free resources.
"""
from __future__ import annotations

from typing import Optional

from ..configuration import ScenarioParams, Selection
from ..results import INFEASIBLE


def _category(cat_id: str, title: str, weight: float, score: Optional[float], reasons: list[str]) -> dict:
    evaluable = score is not None
    s = None if score is None else max(0.0, min(1.0, score))
    return {"id": cat_id, "title": title, "weight": weight, "evaluable": evaluable,
            "score_fraction": None if s is None else round(s, 4),
            "points": None if s is None else round(s * weight, 2), "reasons": reasons}


def science_category(performance: dict, weight: float) -> dict:
    reasons = [f"{r['title']}: " + ("not evaluated. " if not r["evaluable"] else f"{r['score'] * 100:.0f}%. ")
               + r["reason"] for r in performance["rules"]]
    if not performance["rules"]:
        reasons = ["The scenario defines no science rules."]
    return _category("science", "Scientific mission performance", weight, performance["score"], reasons)


def objectives_category(mission: dict, weight: float) -> dict:
    reasons = [f"{o['title']}: " + ("not evaluated. " if o["achieved_fraction"] is None
                                    else f"{o['achieved_fraction'] * 100:.0f}%. ") + o["message"]
               for o in mission["objectives"]]
    return _category("objectives", "Objective completion", weight, mission["objective_fraction"], reasons)


def reliability_category(sel: Selection, evaluation: dict, params: ScenarioParams, weight: float) -> dict:
    """Mean of the evaluable factors (TRL, launcher record, margins) minus a deployable-array penalty."""
    factors, reasons = [], []

    carried = [r for _, r in sel.carried()]
    trls = [(r["id"], r["trl"]) for r in carried if r.get("trl") is not None]
    no_trl = [r["id"] for r in carried if r.get("trl") is None]
    if trls:
        weakest = min(trls, key=lambda t: t[1])
        factors.append(min(weakest[1], 9) / 9.0)
        reasons.append(f"Lowest technology readiness level is TRL {weakest[1]} ({weakest[0]}): "
                       f"{min(weakest[1], 9) / 9 * 100:.0f}%. TRL is a maturity level used as a gameplay "
                       "factor, not a failure probability."
                       + (f" No TRL published for {', '.join(no_trl)}; they are left out, not assumed mature."
                          if no_trl else ""))
    else:
        reasons.append("No selected component has a published TRL: maturity not evaluated.")

    flights, successes = sel.launcher.get("flights"), sel.launcher.get("successes")
    if flights and successes is not None:
        factors.append(successes / flights)
        reasons.append(f"{sel.launcher['name']} flight record: {successes} of {flights} successful"
                       f" (as of {sel.launcher.get('reliability_as_of') or 'unknown date'}): "
                       f"{successes / flights * 100:.0f}%.")
    else:
        reasons.append(f"No flight record in the dataset for {sel.launcher['name']}: launcher reliability "
                       "not evaluated.")

    for key, label in (("mass_margin_fraction", "Payload mass"), ("power_margin_fraction", "Power")):
        margin = evaluation["margins"][key]
        if margin is None:
            reasons.append(f"{label} margin not evaluated (some values are unknown).")
            continue
        f = max(0.0, min(1.0, margin / params.margin_target_fraction))
        factors.append(f)
        reasons.append(f"{label} margin {margin * 100:.0f}% against a {params.margin_target_fraction * 100:.0f}% "
                       f"target (gameplay): {f * 100:.0f}%.")

    if not factors:
        return _category("reliability", "Engineering reliability", weight, None, reasons)
    score = sum(factors) / len(factors)
    deployables = [a["id"] for a in sel.solar_arrays if str(a.get("type", "")).startswith("deployable")]
    if deployables:
        penalty = params.deployable_array_penalty * len(deployables)
        score -= penalty
        reasons.append(f"{len(deployables)} deployable solar array(s) add deployment risk: "
                       f"-{penalty * 100:.0f} points of 100 (gameplay penalty).")
    return _category("reliability", "Engineering reliability", weight, score, reasons)


def efficiency_category(evaluation: dict, mission: dict, params: ScenarioParams, weight: float) -> dict:
    """Resource efficiency, multiplied by objective completion so cheap failures are not rewarded."""
    factors, reasons = [], []
    cost, budget = evaluation["cost"]["known_cost_usd"], params.budget_usd
    if cost is not None and budget:
        f = 0.0 if cost > budget else 0.5 + 0.5 * (1.0 - cost / budget)
        factors.append(f)
        reasons.append(f"Known cost {cost:,.0f} USD of a {budget:,.0f} USD budget (platform and launch scope): "
                       f"{f * 100:.0f}%.")
    else:
        reasons.append("Cost efficiency not evaluated: the launch price or the budget is unknown. "
                       "Unknown cost is not treated as zero.")
    margin = evaluation["margins"]["mass_margin_fraction"]
    if margin is not None:
        used = 1.0 - margin
        f = max(0.0, min(1.0, used / 0.8))
        factors.append(f)
        reasons.append(f"Platform sizing: {used * 100:.0f}% of the payload mass capacity is used "
                       f"(full marks at 80% or more, gameplay rule): {f * 100:.0f}%.")
    else:
        reasons.append("Platform sizing not evaluated: payload mass is only partly known.")
    if not factors:
        return _category("efficiency", "Resource efficiency", weight, None, reasons)
    raw = sum(factors) / len(factors)
    gate = mission["objective_fraction"]
    if gate is None:
        reasons.append("Objective completion is not evaluable, so efficiency cannot be credited.")
        return _category("efficiency", "Resource efficiency", weight, None, reasons)
    reasons.append(f"Multiplied by objective completion ({gate * 100:.0f}%): saving resources earns nothing "
                   "if the mission does not meet its objective.")
    return _category("efficiency", "Resource efficiency", weight, raw * gate, reasons)


def compute_score(sel: Selection, params: ScenarioParams, evaluation: dict, performance: dict,
                  mission: dict) -> dict:
    w = params.scoring_weights
    categories = [
        science_category(performance, w.science),
        objectives_category(mission, w.objectives),
        reliability_category(sel, evaluation, params, w.reliability),
        efficiency_category(evaluation, mission, params, w.efficiency),
    ]
    total_weight = sum(c["weight"] for c in categories)
    evaluable_weight = sum(c["weight"] for c in categories if c["evaluable"])
    points = sum(c["points"] for c in categories if c["evaluable"])
    total = round(100.0 * points / evaluable_weight, 2) if evaluable_weight > 0 else None
    infeasible = evaluation["feasibility"]["status"] == INFEASIBLE
    notes = ["Weights are provisional gameplay choices, not official NASA formulas.",
             "The score is separate from feasibility; read it together with the feasibility status."]
    if infeasible:
        notes.append("THIS DESIGN IS INFEASIBLE: it fails hard constraint(s) "
                     + ", ".join(evaluation["feasibility"]["hard_failed"])
                     + ". The score describes the paper design only; the mission cannot fly.")
    if evaluable_weight < total_weight:
        notes.append("Some categories could not be evaluated; the total is normalised over the evaluable ones.")
    return {
        "total": total,
        "max": 100,
        "completeness": round(evaluable_weight / total_weight, 4) if total_weight > 0 else 0.0,
        "feasibility_status": evaluation["feasibility"]["status"],
        "valid_for_ranking": not infeasible,
        "categories": categories,
        "notes": notes,
    }
