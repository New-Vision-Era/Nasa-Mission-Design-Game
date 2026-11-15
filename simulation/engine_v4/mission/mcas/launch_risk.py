"""Risky launches: a design that fails a hard constraint may still fly, and pays for it.

Team decision (2026-11-15): pre-launch validation blocks only CATASTROPHIC designs. A design with a
smaller hard failure launches, and the failure becomes a launch accident or lasting damage that the
mission result and the score then show. Every rule below is a GAMEPLAY ASSUMPTION for a teaching game,
not a reliability model: it is deterministic and explainable from the failed constraint alone.

Catastrophic (the launch is refused, as before):
  - no instrument or no radio on board (there is nothing to fly);
  - a numeric hard check over its limit by more than CATASTROPHIC_RATIO (budget: BUDGET_CATASTROPHIC_RATIO).

Risky (the launch goes ahead) — consequence of each failed hard check, r = actual / limit:
  launch_orbit_support          the launcher cannot reach the orbit: spacecraft lost at orbit insertion
  launch_mass   (1 < r <= 2)    launcher under-performs: orbit too low, operating life cut by 2 x (r - 1);
                                a cut of the whole life is a loss during ascent
  payload_mass  (1 < r <= 2)    launch loads damage the payload: science capacity x (2 - r)
  payload_volume(1 < r <= 2)    payload mounted outside a proper bay: science capacity x (2 - r)
  power checks  (1 < r <= 2)    instruments run only the share of time the power supports: x 1 / r
  command_link                  no radio can receive commands: lost at commissioning
  ground_station_compatibility  if the main downlink radio has no ground station: no data reaches Earth
  budget        (1 < r <= 1.5)  no physical effect; the efficiency score already falls to zero
  any other hard check          science capacity x 0.5 (unverified failure, flagged as such)

Feasible and CONDITIONAL designs are never touched by this module.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from ...results import FAIL, HARD, INFEASIBLE

GO, RISKY, NO_GO = "GO", "RISKY", "NO_GO"
CATASTROPHIC_RATIO = 2.0
BUDGET_CATASTROPHIC_RATIO = 1.5
UNKNOWN_FAILURE_FACTOR = 0.5

STAGE_LABEL = {"launch": "ascent", "orbit_insertion": "orbit insertion", "commissioning": "commissioning"}

ASSUMPTIONS = [
    "Risky-launch consequences are gameplay rules for teaching, not failure probabilities.",
    f"A hard check over its limit by more than {CATASTROPHIC_RATIO:g}x (budget {BUDGET_CATASTROPHIC_RATIO:g}x) "
    "blocks the launch.",
    "Launch overload shortens operating life by twice the overload fraction (orbit too low, early re-entry).",
    "Payload overload or poor fit reduces science capacity by the overload fraction (launch damage).",
    "Power shortfall: instruments operate only the share of time the power supports.",
]


def _ratio(c) -> Optional[float]:
    a, lim = c.actual_value, c.limit_value
    if not isinstance(a, (int, float)) or not isinstance(lim, (int, float)) or lim <= 0 or a <= 0:
        return None
    return a / lim if a >= lim else lim / a


def _entry(c, consequence: str, **effect) -> dict[str, Any]:
    return {"constraint_id": c.id, "title": c.title, "category": c.category,
            "related_step": c.related_step, "ratio": None if _ratio(c) is None else round(_ratio(c), 3),
            "consequence": consequence, "effect": effect, "value_kind": "gameplay_assumption"}


def assess(evaluation: dict, sel, params, radio_id: Optional[str]) -> dict[str, Any]:
    """Classify a design for launch. Pure: reads the engineering evaluation only."""
    feas = evaluation["feasibility"]
    base = {"status": GO, "blocking": [], "risks": [], "total_loss": None, "science_factor": 1.0,
            "downlink_factor": 1.0, "life_fraction": 1.0, "operating_periods": params.science_periods,
            "assumptions": ASSUMPTIONS}
    if feas["status"] != INFEASIBLE:
        return base

    blocking: list[dict] = []
    if not sel.instruments:
        blocking.append({"constraint_id": "no_instrument", "title": "No instrument",
                         "reason": "There is no instrument on board: the mission has nothing to do.",
                         "related_step": "instruments"})
    if not sel.comms:
        blocking.append({"constraint_id": "no_radio", "title": "No radio",
                         "reason": "There is no radio on board: the spacecraft could never be contacted.",
                         "related_step": "communications"})

    risks: list[dict] = []
    total_loss: Optional[dict] = None
    science, downlink, life = 1.0, 1.0, 1.0
    failed = [c for c in evaluation["constraints"] if c.status == FAIL and c.severity == HARD]
    for c in failed:
        r = _ratio(c)
        limit = BUDGET_CATASTROPHIC_RATIO if c.id == "budget" else CATASTROPHIC_RATIO
        if r is not None and r > limit:
            blocking.append({"constraint_id": c.id, "title": c.title, "related_step": c.related_step,
                             "reason": f"{c.title}: {r:.1f}x over the limit. Far beyond what any launch "
                                       "review would accept."})
            continue
        if c.id == "launch_orbit_support":
            total_loss = total_loss or {"stage": "orbit_insertion",
                                        "reason": f"{sel.launcher['name']} cannot reach {sel.orbit['name']}: the "
                                                  "upper stage runs out of performance and the spacecraft is left "
                                                  "in a useless orbit."}
            risks.append(_entry(c, "Spacecraft lost at orbit insertion.", total_loss=True))
        elif c.id == "launch_mass" and r is not None:
            cut = min(1.0, 2.0 * (r - 1.0))
            if cut >= 1.0:
                total_loss = total_loss or {"stage": "launch",
                                            "reason": f"The vehicle is {(r - 1) * 100:.0f}% over its payload "
                                                      "capacity and cannot reach orbit: the mission is lost "
                                                      "during ascent."}
                risks.append(_entry(c, "Lost during ascent.", total_loss=True))
            else:
                life = min(life, 1.0 - cut)
                risks.append(_entry(c, f"Orbit too low: operating life cut by {cut * 100:.0f}%.",
                                    life_fraction=round(1.0 - cut, 4)))
        elif c.id in ("payload_mass", "payload_volume"):
            f = max(0.0, 2.0 - r) if r is not None else UNKNOWN_FAILURE_FACTOR
            science *= f
            what = "Launch loads damage the payload" if c.id == "payload_mass" else "Payload mounted outside the bay"
            risks.append(_entry(c, f"{what}: science capacity {f * 100:.0f}%.", science_factor=round(f, 4)))
        elif c.category == "power" and r is not None:
            f = 1.0 / r
            science *= f
            risks.append(_entry(c, f"Power shortfall: instruments run {f * 100:.0f}% of the time.",
                                science_factor=round(f, 4)))
        elif c.id == "command_link":
            total_loss = total_loss or {"stage": "commissioning",
                                        "reason": "No radio can receive commands: the spacecraft never answers "
                                                  "and cannot be commissioned."}
            risks.append(_entry(c, "Lost at commissioning (no command uplink).", total_loss=True))
        elif c.id == "ground_station_compatibility":
            if radio_id is None or radio_id in (c.affected_component_ids or []):
                downlink = 0.0
                science = 0.0
                risks.append(_entry(c, "No ground station can hear the main radio: no data reaches Earth.",
                                    science_factor=0.0, downlink_factor=0.0))
            else:
                risks.append(_entry(c, "A secondary radio has no ground station: it is dead weight."))
        elif c.id == "budget":
            risks.append(_entry(c, "Over budget: efficiency scores zero."))
        else:
            science *= UNKNOWN_FAILURE_FACTOR
            risks.append(_entry(c, f"Unverified failure: science capacity {UNKNOWN_FAILURE_FACTOR * 100:.0f}%.",
                                science_factor=UNKNOWN_FAILURE_FACTOR))

    periods = params.science_periods
    operating = 0 if total_loss else max(0, math.floor(periods * life + 1e-9))
    if not total_loss and operating == 0:
        total_loss = {"stage": "launch", "reason": "The orbit is so low that the spacecraft re-enters "
                                                   "before its first operation period."}
    return {**base,
            "status": NO_GO if blocking else RISKY,
            "blocking": blocking, "risks": risks, "total_loss": total_loss,
            "science_factor": round(science, 6), "downlink_factor": downlink,
            "life_fraction": round(life, 4), "operating_periods": operating}


def launch_log(assessment: dict, sel, params) -> list[dict]:
    """Mission-log lines for launch, deployment and commissioning under a risky launch."""
    log: list[dict] = []
    loss = assessment["total_loss"]
    stages = ("launch", "deployment", "commissioning")
    lost_at = {"launch": 0, "orbit_insertion": 1, "commissioning": 2}.get(loss["stage"]) if loss else None
    for i, phase in enumerate(stages):
        if lost_at is not None and i == lost_at:
            log.append({"phase": phase, "period": None, "kind": "accident",
                        "message": f"FAILURE during {STAGE_LABEL[loss['stage']]}. {loss['reason']}"})
            return log
        log.append({"phase": phase, "period": None, "message": f"{phase.capitalize()} completed."})
    for r in assessment["risks"]:
        if not r["effect"].get("total_loss"):
            log.append({"phase": "commissioning", "period": None, "kind": "accident",
                        "message": f"{r['title']} failed at launch review. {r['consequence']}"})
    return log


def adjust_score(score: dict, mission: dict) -> dict:
    """A risky launch cannot keep paper-design points it never earned in flight.

    Science is multiplied by the observation objective actually achieved; reliability by the share of
    planned operations the damaged spacecraft could deliver. Weights are unchanged.
    """
    launch = mission.get("launch") or {}
    if launch.get("status") != RISKY:
        return score
    observe = next((o["achieved_fraction"] for o in mission["objectives"] if o["id"] == "observe_target"), 0.0) or 0.0
    delivered = 0.0 if launch.get("total_loss") else launch["science_factor"] * launch["life_fraction"]
    gates = {"science": (observe, f"Multiplied by the observation actually achieved ({observe * 100:.0f}%): "
                                  "capability that never observed earns nothing (risky launch)."),
             "reliability": (delivered, f"Multiplied by the operations the launch left possible "
                                        f"({delivered * 100:.0f}%): the design flew with failed hard checks.")}
    for cat in score["categories"]:
        if cat["evaluable"] and cat["id"] in gates:
            g, why = gates[cat["id"]]
            cat["score_fraction"] = round(cat["score_fraction"] * g, 4)
            cat["points"] = round(cat["score_fraction"] * cat["weight"], 2)
            cat["reasons"] = cat["reasons"] + [why]
    ev = [c for c in score["categories"] if c["evaluable"]]
    weight = sum(c["weight"] for c in ev)
    score["total"] = round(100.0 * sum(c["points"] for c in ev) / weight, 2) if weight else None
    score["notes"] = [n for n in score["notes"] if "cannot fly" not in n] + [
        "RISKY LAUNCH: the design flew despite failed hard checks; their consequences are in the mission "
        "result and in the science and reliability scores."]
    return score
