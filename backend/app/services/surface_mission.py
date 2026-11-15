"""Surface missions (Mars rover, lunar lander): one small engine, two mission specifications.

Educational game model. Every number in MISSIONS is an ILLUSTRATIVE GAME VALUE, not a NASA or
manufacturer specification:
  - Mars reuses the team's existing rover prototype values (backend/app/services/mars_mission.py).
  - Moon values were written for the game on 2026-11-15 in the same style. They have NOT been
    researched: Person 1 should replace them with sourced values (structure stays the same).

The flight follows the same rules as the Earth-observation engine:
  - only catastrophic designs are refused (missing system, budget > 1.5x, mass > 2x, power < half);
  - smaller hard failures fly as a "risky launch" and become consequences;
  - one player decision during the approach to landing (primary site or safer backup site);
  - score out of 100 with the same four categories and weights (35 / 25 / 20 / 20).
Output uses the same shape as the engine v4 MCAS debrief so the UI shows it with the same screens.
"""
from __future__ import annotations

import itertools
from typing import Any, Optional

from backend.app.services import mars_mission

CATEGORIES = ("launch", "power", "comm", "landing")
WEIGHTS = {"science": 35.0, "objectives": 25.0, "reliability": 20.0, "efficiency": 20.0}
SUCCESS_AT, PARTIAL_AT = 0.8, 0.4
CATASTROPHIC = {"budget": 1.5, "mass": 2.0, "payload": 2.0, "power": 2.0}
BACKUP_SITE_SCIENCE = 0.75  # science kept when diverting to the safer backup landing site (game rule)

MISSIONS: dict[str, dict[str, Any]] = {
    "mars": {
        "id": "mars", "name": "Mars rover exploration", "short": "MARS ROVER",
        "briefing": "Land a rover on Mars, survive the surface and send its science home.",
        "goals": ["Land safely", "Collect surface science", "Return data to Earth"],
        "budget_m": mars_mission.BUDGET_LIMIT_M, "mass_cap_kg": mars_mission.MASS_LIMIT_KG,
        "base_load_w": mars_mission.BASE_LOAD_W, "science_max": mars_mission.SCIENCE_MAX,
        "duration": "3 years", "cruise": {"title": "Interplanetary cruise", "days": 260},
        "landing_hazard": "Dust storm over the primary landing site",
        "site_names": ("Jezero delta (primary)", "Smooth plain (backup)"),
        "equipment": mars_mission.EQUIPMENT,
        "value_note": "Team prototype values for the game, not official NASA specifications.",
    },
    "moon": {
        "id": "moon", "name": "Lunar south pole lander", "short": "LUNAR LANDER",
        "briefing": "Land near the lunar south pole, prospect for water ice and send the data home.",
        "goals": ["Land safely", "Prospect for ice", "Return data to Earth"],
        "budget_m": 80, "mass_cap_kg": 1500, "base_load_w": 150, "science_max": 100,
        "duration": "1 year", "cruise": {"title": "Translunar cruise", "days": 5},
        "landing_hazard": "Boulder field detected at the primary landing site",
        "site_names": ("Shackleton rim (primary)", "Flat crater floor (backup)"),
        "equipment": {
            "launch": {
                "lv-medium": {"name": "Medium Launch Vehicle", "cost": 20, "mass": 0, "payloadKg": 1000},
                "lv-heavy": {"name": "Heavy Launch Vehicle", "cost": 35, "mass": 0, "payloadKg": 2500}},
            "power": {
                "pw-solar": {"name": "Solar Array + Battery", "cost": 8, "mass": 100, "powerW": 400,
                             "surfaceDuty": 0.5},
                "pw-rtg": {"name": "Radioisotope Power System", "cost": 18, "mass": 200, "powerW": 700,
                           "surfaceDuty": 1.0}},
            "comm": {
                "cm-direct": {"name": "Direct-to-Earth Antenna", "cost": 4, "mass": 25, "efficiency": 0.85},
                "cm-relay": {"name": "High-Gain + Relay Link", "cost": 9, "mass": 45, "efficiency": 0.98}},
            "instruments": {
                "ins-camera": {"name": "Panoramic Camera", "cost": 4, "mass": 30, "scienceValue": 20, "powerW": 40},
                "ins-xrf": {"name": "X-ray Spectrometer", "cost": 7, "mass": 60, "scienceValue": 30, "powerW": 80},
                "ins-drill": {"name": "Ice Prospecting Drill", "cost": 12, "mass": 150, "scienceValue": 50,
                              "powerW": 180}},
            "landing": {
                "ld-standard": {"name": "Standard Descent Stage", "cost": 10, "mass": 300, "reliability": 0.75},
                "ld-precision": {"name": "Precision Landing System", "cost": 18, "mass": 380, "reliability": 0.95}},
        },
        "value_note": "Illustrative game values written for this game; not researched. Replace with sourced data.",
    },
}

ASSUMPTIONS = [
    "All equipment values are illustrative game values (see value_note).",
    "Landing outcome from landing-system reliability: >= 90% lands cleanly, >= 70% lands with damage "
    "(science x 0.8), lower fails.",
    "Diverting to the backup site lowers the landing risk by one level and keeps 75% of the science.",
    "A solar-powered lunar lander works only through the lunar day (science x 0.5).",
    "Over the launch payload: lost during ascent. Over the mission mass cap: landing worsens one level.",
    "Power shortfall: instruments run only the share of time the power supports.",
]


class SurfaceError(ValueError):
    pass


def spec(mission_id: str) -> dict[str, Any]:
    if mission_id not in MISSIONS:
        raise SurfaceError(f"Unknown surface mission '{mission_id}'.")
    return MISSIONS[mission_id]


def catalog(mission_id: str) -> dict[str, Any]:
    m = spec(mission_id)
    return {"mission": {k: m[k] for k in ("id", "name", "short", "briefing", "goals", "budget_m", "mass_cap_kg",
                                           "base_load_w", "science_max", "duration", "cruise", "value_note")},
            "categories": m["equipment"], "assumptions": ASSUMPTIONS}


def _normalise(m: dict, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SurfaceError("Body must contain a 'selection' object.")
    eq = m["equipment"]
    sel = {k: raw.get(k) for k in CATEGORIES}
    inst = raw.get("instruments") or []
    if not isinstance(inst, list):
        raise SurfaceError("instruments must be a list")
    if len(inst) != len(set(inst)):
        raise SurfaceError("An instrument can only be selected once")
    for k in CATEGORIES:
        if sel[k] is not None and sel[k] not in eq[k]:
            raise SurfaceError(f"Unknown {k} option: {sel[k]}")
    for i in inst:
        if i not in eq["instruments"]:
            raise SurfaceError(f"Unknown instrument option: {i}")
    sel["instruments"] = inst
    return sel


def _check(cid: str, title: str, category: str, step: str, actual, limit, unit: str, ok: bool,
           message: str, hard: bool = True) -> dict[str, Any]:
    return {"id": cid, "title": title, "category": category, "related_step": step,
            "status": "PASS" if ok else ("FAIL" if hard else "WARNING"), "severity": "hard" if hard else "soft",
            "actual_value": actual, "limit_value": limit, "unit": unit, "message": message}


def evaluate(mission_id: str, raw: Any) -> dict[str, Any]:
    """Resources, checks and the launch verdict (GO / RISKY / NO_GO). Partial designs are fine."""
    m = spec(mission_id)
    eq = m["equipment"]
    s = _normalise(m, raw)
    pick = {k: (eq[k][s[k]] if s[k] else None) for k in CATEGORIES}
    inst = [eq["instruments"][i] for i in s["instruments"]]
    parts = [p for p in pick.values() if p] + inst
    cost = sum(p["cost"] for p in parts)
    mass = sum(p["mass"] for p in parts)
    payload = pick["launch"]["payloadKg"] if pick["launch"] else None
    available = pick["power"]["powerW"] if pick["power"] else None
    required = m["base_load_w"] + sum(i["powerW"] for i in inst)
    missing = [label for key, label in (("launch", "Launcher"), ("power", "Power"), ("comm", "Comms"),
                                        ("landing", "Landing"), ("instruments", "Science")) if not s[key]]
    checks = [
        _check("budget", "Mission budget", "budget", "launch", cost, m["budget_m"], "M$",
               cost <= m["budget_m"], f"${cost}M of the ${m['budget_m']}M budget."),
        _check("mass", "Mission mass cap", "mass", "landing", mass, m["mass_cap_kg"], "kg",
               mass <= m["mass_cap_kg"], f"{mass} kg against the {m['mass_cap_kg']} kg mission cap."),
    ]
    if payload is not None:
        checks.append(_check("payload", "Launch payload capacity", "launch", "launch", mass, payload, "kg",
                             mass <= payload, f"{mass} kg against {payload} kg launcher capacity."))
    if available is not None:
        checks.append(_check("power", "Power covers the load", "power", "power", required, available, "W",
                             required <= available, f"{required} W needed, {available} W available."))
    if pick["landing"]:
        rel = pick["landing"]["reliability"]
        checks.append(_check("landing", "Landing reliability", "landing", "landing", rel * 100, 90, "%",
                             rel >= 0.9, f"{rel * 100:.0f}% landing reliability (90% for a clean landing).",
                             hard=False))
    if pick["comm"]:
        eff = pick["comm"]["efficiency"]
        checks.append(_check("link", "Data link efficiency", "communications", "comm", eff * 100, 90, "%",
                             eff >= 0.9, f"{eff * 100:.0f}% of collected data reaches Earth.", hard=False))
    if pick["power"] and pick["power"].get("surfaceDuty", 1.0) < 1.0:
        checks.append(_check("night", "Survives the night", "power", "power", None, None, None, False,
                             "Solar power stops during the lunar night: instruments work half the time.",
                             hard=False))

    blocking = [{"constraint_id": "missing", "title": "Missing systems", "related_step": "launch",
                 "reason": "Still needed: " + ", ".join(missing) + "."}] if missing else []
    risks = []
    for c in checks:
        if c["status"] != "FAIL" or c["severity"] != "hard":
            continue
        a, lim = c["actual_value"], c["limit_value"]
        ratio = a / lim if lim else None
        if ratio is not None and ratio > CATASTROPHIC[c["id"]]:
            blocking.append({"constraint_id": c["id"], "title": c["title"], "related_step": c["related_step"],
                             "reason": f"{c['title']}: {ratio:.1f}x over. No launch review would accept it."})
            continue
        consequence = {
            "budget": "Over budget: efficiency scores zero.",
            "mass": "Heavier than the descent system is rated for: landing gets one level worse.",
            "payload": "The launcher cannot lift it: lost during ascent.",
            "power": f"Power shortfall: instruments run {min(1.0, lim / a) * 100:.0f}% of the time.",
        }[c["id"]]
        risks.append({"constraint_id": c["id"], "title": c["title"], "related_step": c["related_step"],
                      "consequence": consequence, "ratio": round(ratio, 3) if ratio else None})
    status = "NO_GO" if blocking else ("RISKY" if risks else "GO")
    return {
        "mission_id": mission_id, "selection": s, "complete": not missing, "missing": missing,
        "resources": {"cost_m": cost, "budget_m": m["budget_m"], "mass_kg": mass, "mass_cap_kg": m["mass_cap_kg"],
                      "payload_kg": payload, "power_required_w": required, "power_available_w": available,
                      "science_planned": sum(i["scienceValue"] for i in inst), "science_max": m["science_max"]},
        "constraints": checks,
        "feasibility": {"status": "INFEASIBLE" if any(c["status"] == "FAIL" and c["severity"] == "hard"
                                                      for c in checks) or missing else "FEASIBLE"},
        "launch_assessment": {"status": status, "blocking": blocking, "risks": risks,
                              "total_loss": None, "assumptions": ASSUMPTIONS},
        "launchable": status != "NO_GO",
    }


LEVELS = ["failure", "warning", "success"]


def _landing_level(rel: float) -> str:
    return "success" if rel >= 0.9 else "warning" if rel >= 0.7 else "failure"


def fly(mission_id: str, raw: Any, decisions: Optional[dict] = None) -> dict[str, Any]:
    """Fly a design. Stops at the landing decision (AWAITING_DECISION) or ends (COMPLETED / NOT_LAUNCHED)."""
    m = spec(mission_id)
    eq = m["equipment"]
    ev = evaluate(mission_id, raw)
    s = ev["selection"]
    la = ev["launch_assessment"]
    decisions = decisions or {}
    if la["status"] == "NO_GO":
        return {"status": "NOT_LAUNCHED", "mission_type": mission_id, "evaluation": ev,
                "mission_history": [{"phase": "launch", "message": "Launch refused: "
                                     + " ".join(b["reason"] for b in la["blocking"])}]}
    r = ev["resources"]
    failed = {c["id"] for c in ev["constraints"] if c["status"] == "FAIL" and c["severity"] == "hard"}
    power, comm, landing = (eq[k][s[k]] for k in ("power", "comm", "landing"))
    instruments = [eq["instruments"][i] for i in s["instruments"]]
    log: list[dict] = []
    stages: list[dict] = []
    total_loss = None

    # launch
    if "payload" in failed:
        total_loss = {"stage": "launch", "reason": f"The vehicle is {r['mass_kg'] - r['payload_kg']} kg over its "
                                                   "payload capacity and cannot reach the transfer orbit."}
        stages.append({"id": "launch", "title": "Launch", "status": "failed", "message": total_loss["reason"]})
        log.append({"phase": "launch", "kind": "accident", "message": "FAILURE during ascent. " + total_loss["reason"]})
    else:
        use = r["mass_kg"] / r["payload_kg"]
        stages.append({"id": "launch", "title": "Launch", "status": "completed" if use < 0.9 else "degraded",
                       "message": f"Delivered to the transfer trajectory ({use * 100:.0f}% of launcher capacity)."})
        log.append({"phase": "launch", "message": "Liftoff. " + stages[-1]["message"]})
        cr = m["cruise"]
        stages.append({"id": "cruise", "title": cr["title"], "status": "completed",
                       "message": f"{cr['days']} days of cruise. Power {r['power_available_w']} W for a "
                                  f"{r['power_required_w']} W load; link {comm['efficiency'] * 100:.0f}%."})
        log.append({"phase": "cruise", "message": stages[-1]["message"]})

    pending = None
    level = None
    site = None
    if total_loss is None:
        level = _landing_level(landing["reliability"])
        if "mass" in failed:
            level = LEVELS[max(0, LEVELS.index(level) - 1)]
            log.append({"phase": "landing", "kind": "accident",
                        "message": "The descent stage is overloaded: landing margin is worse than rated."})
        primary, backup = m["site_names"]
        backup_level = LEVELS[min(2, LEVELS.index(level) + 1)]
        choice = decisions.get("landing_site")
        if choice is None:
            pending = {
                "anomaly_id": "landing_site", "definition_id": "landing_site", "name": m["landing_hazard"],
                "category": "external", "affected_system": "landing", "severity": "medium", "period": 1,
                "elapsed_days": m["cruise"]["days"],
                "what_happened": f"Final approach. {m['landing_hazard']}. Choose where to land.",
                "symptom": f"Predicted landing at the primary site: {level.upper()}.",
                "contributing_design_decision": f"{landing['name']}: {landing['reliability'] * 100:.0f}% reliability.",
                "recovery": "The choice is final: there is no second attempt.",
                "responses": [
                    {"id": "primary", "label": f"Land at {primary}", "available": True, "is_default": True,
                     "trade_off": f"Full science value. Predicted landing: {level}.", "unavailable_reason": None},
                    {"id": "backup", "label": f"Divert to {backup}", "available": True, "is_default": False,
                     "trade_off": f"Safer ({backup_level}), but only {BACKUP_SITE_SCIENCE * 100:.0f}% of the science.",
                     "unavailable_reason": None},
                ],
            }
        else:
            if choice not in ("primary", "backup"):
                raise SurfaceError("landing_site must be 'primary' or 'backup'.")
            site = choice
            if choice == "backup":
                level = backup_level
            name = primary if choice == "primary" else backup
            msg = {"success": f"Touchdown confirmed at {name}.",
                   "warning": f"Hard landing at {name}: the vehicle is damaged.",
                   "failure": f"Landing failed at {name}: contact lost on touchdown."}[level]
            stages.append({"id": "landing", "title": "Landing",
                           "status": {"success": "completed", "warning": "degraded", "failure": "failed"}[level],
                           "message": msg})
            log.append({"phase": "landing", "kind": "accident" if level != "success" else None, "message": msg})
            if level == "failure":
                total_loss = {"stage": "landing", "reason": msg}

    if pending is not None:
        return {"status": "AWAITING_DECISION", "mission_type": mission_id, "evaluation": ev, "stages": stages,
                "mission_history": log, "pending_decision": pending, "launch_assessment": {**la}}

    # surface operations
    landing_factor = 0.0 if total_loss else (1.0 if level == "success" else 0.8)
    power_factor = min(1.0, r["power_available_w"] / r["power_required_w"]) if r["power_required_w"] else 1.0
    duty = power.get("surfaceDuty", 1.0)
    site_factor = BACKUP_SITE_SCIENCE if site == "backup" else 1.0
    returns = []
    for iid, inst in zip(s["instruments"], instruments):
        got = inst["scienceValue"] * power_factor * duty * landing_factor * site_factor
        returns.append({"id": iid, "name": inst["name"], "planned": inst["scienceValue"], "collected": round(got, 1)})
    collected = round(sum(x["collected"] for x in returns), 1)
    transmitted = round(collected * comm["efficiency"], 1)
    planned = r["science_planned"]
    if total_loss is None:
        msg = (f"{collected} of {planned} science points collected"
               + (f" (power {power_factor * 100:.0f}%" if power_factor < 1 else "")
               + (", lunar night" if duty < 1 else "") + (")" if power_factor < 1 or duty < 1 else "")
               + f"; {transmitted} reached Earth.")
        stages.append({"id": "surface", "title": "Surface operations",
                       "status": "completed" if transmitted >= 0.8 * planned else "degraded", "message": msg})
        log.append({"phase": "surface", "message": msg})

    # objectives and score
    landed = landing_factor
    returned = transmitted / planned if planned else 0.0
    objectives = [
        {"id": "land", "title": "Land safely", "achieved_fraction": round(landed, 4),
         "message": {1.0: "Clean touchdown.", 0.8: "Landed, with damage.", 0.0: "Did not land."}[landed]},
        {"id": "return_data", "title": "Return the science to Earth", "achieved_fraction": round(min(1.0, returned), 4),
         "message": f"{transmitted} of {planned} planned science points reached Earth."},
    ]
    objective_fraction = round(sum(o["achieved_fraction"] for o in objectives) / 2, 4)
    outcome = ("FAILURE" if total_loss else "SUCCESS" if objective_fraction >= SUCCESS_AT
               else "PARTIAL_SUCCESS" if objective_fraction >= PARTIAL_AT else "FAILURE")
    sci = transmitted / m["science_max"]
    rel_parts = [landing["reliability"], comm["efficiency"], min(1.0, power_factor)]
    reliability = sum(rel_parts) / len(rel_parts) * (0.0 if total_loss else 1.0)
    cost_f = 0.0 if r["cost_m"] > r["budget_m"] else 0.5 + 0.5 * (1 - r["cost_m"] / r["budget_m"])
    efficiency = cost_f * objective_fraction

    def cat(cid, title, frac, reasons):
        frac = max(0.0, min(1.0, frac))
        return {"id": cid, "title": title, "weight": WEIGHTS[cid], "evaluable": True,
                "score_fraction": round(frac, 4), "points": round(frac * WEIGHTS[cid], 2), "reasons": reasons}
    categories = [
        cat("science", "Science returned", sci, [f"{transmitted} of {m['science_max']} possible science points reached Earth."]),
        cat("objectives", "Objective completion", objective_fraction, [o["message"] for o in objectives]),
        cat("reliability", "Engineering reliability", reliability,
            [f"Landing {landing['reliability'] * 100:.0f}%, link {comm['efficiency'] * 100:.0f}%, "
             f"power {power_factor * 100:.0f}%" + (" — the spacecraft was lost." if total_loss else ".")]),
        cat("efficiency", "Resource efficiency", efficiency,
            [f"${r['cost_m']}M of ${r['budget_m']}M, multiplied by objective completion "
             f"({objective_fraction * 100:.0f}%)."]),
    ]
    total = round(sum(c["points"] for c in categories), 2)

    explanations = []
    for c in ev["constraints"]:
        if c["status"] != "PASS":
            explanations.append({"kind": "problem" if c["severity"] == "hard" else "weakness",
                                 "constraint_id": c["id"], "related_step": c["related_step"],
                                 "message": f"{c['title']}: {c['message']}"})
    if not explanations:
        explanations.append({"kind": "strength", "constraint_id": None, "related_step": None,
                             "message": "Every check passed before launch."})
    decisions_list = [{"anomaly_id": "landing_site", "response_id": site, "period": 1, "decided_by": "player"}] if site else []
    final_la = {**la, "total_loss": total_loss} if la["status"] == "RISKY" or total_loss else None
    debrief = {
        "mission_id": None, "mission_type": mission_id, "configuration": s, "status": "COMPLETED",
        "outcome": outcome, "objectives": objectives,
        "score": {"total": total, "max": 100, "completeness": 1.0, "categories": categories,
                  "notes": ["Game score from illustrative values (see assumptions)."]},
        "reference_without_anomalies": None, "launch_assessment": final_la,
        "anomalies": [], "decisions": decisions_list,
        "debrief": {"engineering_weaknesses": [], "player_decisions":
                    ([f"Landing site: {m['site_names'][0] if site == 'primary' else m['site_names'][1]}."] if site else []),
                    "mission_consequences": ([f"Landing: {next(x['message'] for x in stages if x['id'] == 'landing')}"]
                                             if site else [])},
        "mission": {"launched": True, "outcome": outcome, "objective_fraction": objective_fraction,
                    "stages": stages, "returns": returns},
        "explanations": explanations, "assumptions": ASSUMPTIONS, "value_note": m["value_note"],
        "mission_history": log,
    }
    return {"status": "COMPLETED", "mission_type": mission_id, "evaluation": ev, "stages": stages,
            "mission_history": log, "pending_decision": None, "outcome": outcome, "score_total": total,
            "debrief": debrief, "launch_assessment": final_la}


def recommend(mission_id: str, raw: Any) -> dict[str, Any]:
    """Best GO designs by score (every combination is tried: the catalogue is small)."""
    m = spec(mission_id)
    eq = m["equipment"]
    current = _normalise(m, raw)
    inst_ids = list(eq["instruments"])
    best = []
    for combo in itertools.product(*(list(eq[k]) for k in CATEGORIES)):
        for n in range(1, len(inst_ids) + 1):
            for inst in itertools.combinations(inst_ids, n):
                sel = dict(zip(CATEGORIES, combo), instruments=list(inst))
                if evaluate(mission_id, sel)["launch_assessment"]["status"] != "GO":
                    continue
                result = fly(mission_id, sel, {"landing_site": "primary"})
                best.append((result["score_total"], sel))
    best.sort(key=lambda t: -t[0])
    others = [(score, sel) for score, sel in best if sel != current][:5]
    alts = [{"configuration": sel, "label": "Best score" if i == 0 else "Alternative", "score": score}
            for i, (score, sel) in enumerate(others)]
    return {"method": "exhaustive search over the catalogue, primary landing site", "alternatives": alts}
