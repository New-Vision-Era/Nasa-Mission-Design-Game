"""Surface missions (Mars rover, lunar lander): launch verdicts, landing decision, consequences."""
import pytest

from backend.app.services import mars_mission
from backend.app.services import surface_mission as engine

MARS = {"launch": "lv-standard", "power": "pw-nuclear", "comm": "cm-advanced", "landing": "ld-advanced",
        "instruments": ["ins-camera", "ins-spectro", "ins-drill"]}
MOON = {"launch": "lv-medium", "power": "pw-rtg", "comm": "cm-direct", "landing": "ld-precision",
        "instruments": ["ins-xrf", "ins-drill"]}


def test_mars_reuses_the_prototype_values():
    ev = engine.evaluate("mars", MARS)
    proto = mars_mission.calculate(MARS)["resources"]
    assert ev["resources"]["cost_m"] == proto["cost"] and ev["resources"]["mass_kg"] == proto["mass"]
    done = engine.fly("mars", MARS, {"landing_site": "primary"})
    assert done["debrief"]["mission"]["returns"] and done["outcome"] == "SUCCESS"
    assert sum(r["collected"] for r in done["debrief"]["mission"]["returns"]) * 0.95 == pytest.approx(
        mars_mission.simulate(MARS)["metrics"]["transmitted"])


@pytest.mark.parametrize("mission,design", [("mars", MARS), ("moon", MOON)])
def test_flight_stops_for_the_landing_decision(mission, design):
    state = engine.fly(mission, design)
    assert state["status"] == "AWAITING_DECISION"
    assert {r["id"] for r in state["pending_decision"]["responses"]} == {"primary", "backup"}


def test_backup_site_is_safer_but_keeps_less_science():
    risky = {**MOON, "landing": "ld-standard"}
    primary = engine.fly("moon", risky, {"landing_site": "primary"})
    backup = engine.fly("moon", risky, {"landing_site": "backup"})
    assert primary["debrief"]["objectives"][0]["achieved_fraction"] < backup["debrief"]["objectives"][0]["achieved_fraction"]
    assert backup["debrief"]["mission"]["returns"][0]["collected"] < primary["debrief"]["mission"]["returns"][0]["collected"] / 0.8


def test_missing_system_is_no_go():
    ev = engine.evaluate("moon", {"instruments": []})
    assert ev["launch_assessment"]["status"] == "NO_GO" and not ev["launchable"]
    assert engine.fly("moon", {"instruments": []})["status"] == "NOT_LAUNCHED"


def test_budget_overrun_flies_risky_with_zero_efficiency():
    over = {"launch": "lv-medium", "power": "pw-rtg", "comm": "cm-relay", "landing": "ld-precision",
            "instruments": ["ins-camera", "ins-xrf", "ins-drill"]}  # 88 M$ of 80: 1.1x
    assert engine.evaluate("moon", over)["launch_assessment"]["status"] == "RISKY"
    done = engine.fly("moon", over, {"landing_site": "primary"})
    assert done["debrief"]["score"]["categories"][3]["points"] == 0


def test_over_launcher_payload_is_lost_during_ascent(monkeypatch):
    spec = engine.MISSIONS["moon"]["equipment"]["launch"]
    monkeypatch.setitem(spec, "lv-tiny", {"name": "Tiny", "cost": 5, "mass": 0, "payloadKg": 600})
    state = engine.fly("moon", {**MOON, "launch": "lv-tiny"})  # 200+25+380+210 = 815 kg on a 600 kg launcher
    assert state["status"] == "COMPLETED" and state["launch_assessment"]["total_loss"]["stage"] == "launch"
    assert state["outcome"] == "FAILURE" and state["score_total"] < 20


def test_far_over_budget_is_no_go(monkeypatch):
    spec = engine.MISSIONS["mars"]["equipment"]["launch"]
    monkeypatch.setitem(spec, "lv-gold", {"name": "Gold", "cost": 120, "mass": 0, "payloadKg": 3000})
    assert engine.evaluate("mars", {**MARS, "launch": "lv-gold"})["launch_assessment"]["status"] == "NO_GO"


def test_recommend_returns_launchable_designs():
    alts = engine.recommend("moon", MOON)["alternatives"]
    assert alts and all(engine.evaluate("moon", a["configuration"])["launch_assessment"]["status"] == "GO" for a in alts)


def test_unknown_mission_and_component():
    with pytest.raises(engine.SurfaceError):
        engine.catalog("venus")
    with pytest.raises(engine.SurfaceError):
        engine.evaluate("moon", {"launch": "nope"})
