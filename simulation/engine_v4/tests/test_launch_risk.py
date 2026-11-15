"""Risky launches (MCAS): only catastrophic designs are refused; smaller hard failures fly and cost."""
import copy

import pytest

from simulation.engine_v4 import interactive, run_simulation
from simulation.engine_v4.data_loader import load_catalog

BASE = {
    "scenario_id": "earth_observation_v4", "platform_id": "gsat_50", "instrument_ids": ["hyperscape100"],
    "power": {"mode": "platform_payload_budget", "solar_array_ids": [], "battery_ids": [], "eps_id": None},
    "communication_system_ids": ["endurosat_s_band_transceiver", "endurosat_x_band_transmitter"],
    "adcs_system_id": "cubespace_cubeadcs_3axis_small_star", "propulsion_system_id": None,
    "orbit_id": "sso_500", "launch_vehicle_id": "rocket_lab_electron",
}


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


def cfg(**changes):
    c = copy.deepcopy(BASE)
    c.update(changes)
    return c


def finish(state, catalog):
    while state["status"] == "AWAITING_DECISION":
        pd = state["pending_decision"]
        default = next(r["id"] for r in pd["responses"] if r["is_default"])
        state = interactive.apply_decision(state, pd["anomaly_id"], default, catalog=catalog)
    return state


def test_feasible_design_is_go_and_unchanged(catalog):
    ev = interactive.evaluate_design(cfg(), catalog=catalog)
    assert ev["launch_assessment"]["status"] == "GO" and ev["launchable"]
    state = finish(interactive.start_run(cfg(), seed=3, catalog=catalog), catalog)
    assert state["risky_launch"] is False and len(state["timeline"]) == 12


def test_unreachable_orbit_launches_and_is_lost(catalog):
    ev = interactive.evaluate_design(cfg(orbit_id="sso_700"), catalog=catalog)
    assert ev["feasibility"]["status"] == "INFEASIBLE"
    assert ev["launchable"] and ev["launch_assessment"]["status"] == "RISKY"
    state = interactive.start_run(cfg(orbit_id="sso_700"), seed=1, catalog=catalog)
    assert state["status"] == "COMPLETED" and state["timeline"] == []
    assert state["outcome"] == "FAILURE" and state["score_total"] == 0
    debrief = interactive.build_debrief(state, catalog=catalog)
    stages = {s["id"]: s["status"] for s in debrief["mission"]["stages"]}
    assert stages["deployment"] == "failed" and stages["commissioning"] == "not_reached"


def test_no_uplink_is_lost_at_commissioning(catalog):
    state = interactive.start_run(cfg(communication_system_ids=["endurosat_x_band_transmitter"]),
                                  seed=1, catalog=catalog)
    assert state["launch_assessment"]["total_loss"]["stage"] == "commissioning"
    assert state["outcome"] == "FAILURE"


def test_small_payload_overload_flies_damaged_and_scores_lower(catalog):
    design = cfg(platform_id="gsat_20", instrument_ids=["hyperscape100", "multiscape100_cis", "chameleon"])
    ev = interactive.evaluate_design(design, catalog=catalog)
    assert ev["launch_assessment"]["status"] == "RISKY"
    assert ev["launch_assessment"]["science_factor"] < 1.0
    state = finish(interactive.start_run(design, seed=3, catalog=catalog), catalog)
    good = finish(interactive.start_run(cfg(), seed=3, catalog=catalog), catalog)
    assert state["status"] == "COMPLETED" and state["score_total"] < good["score_total"]


def test_catastrophic_overload_is_refused(catalog):
    design = cfg(platform_id="gsat_20", instrument_ids=["raptor"])
    ev = interactive.evaluate_design(design, catalog=catalog)
    assert ev["launch_assessment"]["status"] == "NO_GO" and not ev["launchable"]
    state = interactive.start_run(design, seed=0, catalog=catalog)
    assert state["status"] == "NOT_LAUNCHED"
    assert "Launch refused" in interactive.build_debrief(state, catalog=catalog)["mission"]["explanation"]


def test_far_over_budget_is_refused(catalog):
    ev = interactive.evaluate_design(cfg(launch_vehicle_id="spacex_falcon9_dedicated"), catalog=catalog)
    assert ev["launch_assessment"]["status"] == "NO_GO"


def test_quick_mode_still_refuses_infeasible_designs(catalog):
    result = run_simulation(cfg(orbit_id="sso_700"), seed=1, catalog=catalog)
    assert result["mission"]["launched"] is False
