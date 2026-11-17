"""Service-level tests for stored real-data runs. No web framework needed."""

import pytest
from pydantic import ValidationError

from backend.app.errors import ApiError
from backend.app.schemas import SimulationRunCreate

CONFIG = {
    "scenario_id": "earth_observation_v4",
    "platform_id": "gsat_50",
    "instrument_ids": ["hyperscape100"],
    "power": {"mode": "platform_payload_budget"},
    "communication_system_ids": ["endurosat_s_band_transceiver", "endurosat_x_band_transmitter"],
    "adcs_system_id": "cubespace_cubeadcs_3axis_small_star",
    "propulsion_system_id": None,
    "orbit_id": "sso_500",
    "launch_vehicle_id": "rocket_lab_electron",
}


def create(**over) -> SimulationRunCreate:
    return SimulationRunCreate(**{"configuration": CONFIG, "seed": 5, **over})


def test_launch_stores_the_full_result_and_it_reads_back_identically(container):
    sim = container.simulation_v4
    ada = container.auth.register("ada", "correct horse").user
    run = sim.launch(ada, create(name="First try"))
    assert run["status"] == "completed" and run["name"] == "First try"
    assert run["result"]["feasibility"]["status"] == "FEASIBLE"
    assert run["result"]["configuration"]["platform_id"] == "gsat_50"
    assert run["result"]["resources"]["bus_mass_kg"]["basis"] == "estimate"
    assert sim.get(ada, run["run_id"]) == run
    # stored result equals a fresh stateless run with the same seed
    assert run["result"] == sim.run({"configuration": CONFIG, "seed": 5})


def test_infeasible_design_cannot_launch_and_nothing_is_stored(container):
    sim = container.simulation_v4
    ada = container.auth.register("ada", "correct horse").user
    with pytest.raises(ApiError) as exc:
        sim.launch(ada, create(configuration={**CONFIG, "instrument_ids": ["dragoneye"]}))
    assert exc.value.status == 409 and exc.value.code == "not_launchable"
    assert exc.value.extra["result"]["feasibility"]["hard_failed"] == ["payload_mass", "payload_volume"]
    assert sim.history(ada) == []


def test_invalid_configuration_is_rejected_with_the_engine_error(container):
    with pytest.raises(ApiError) as exc:
        container.simulation_v4.launch(None, create(configuration={**CONFIG, "platform_id": "nope"}))
    assert exc.value.status == 422 and exc.value.code == "unknown_component"
    assert exc.value.field == "platform_id"


def test_history_is_private_and_newest_first(container):
    sim = container.simulation_v4
    ada = container.auth.register("ada", "correct horse").user
    bob = container.auth.register("bob", "correct horse").user
    first = sim.launch(ada, create(name="SSO 500"))
    second = sim.launch(ada, create(name="SSO 600", configuration={**CONFIG, "orbit_id": "sso_600"}))
    sim.launch(bob, create())

    rows = sim.history(ada)
    assert [r.run_id for r in rows] == [second["run_id"], first["run_id"]]
    assert [r.feasibility for r in rows] == ["CONDITIONAL", "FEASIBLE"]  # no SSO 600 capacity for Electron
    assert [r.name for r in rows] == ["SSO 600", "SSO 500"]
    assert rows[1].outcome == "SUCCESS" and 0 <= rows[1].score_total <= 100
    assert rows[1].dataset_id == "equipment_v5"
    assert len(sim.history(bob)) == 1
    assert len(sim.history(ada, limit=1)) == 1

    with pytest.raises(ApiError) as exc:  # another player's run looks like it does not exist
        sim.get(bob, first["run_id"])
    assert exc.value.status == 404
    with pytest.raises(ApiError):
        sim.get(None, first["run_id"])


def test_stored_runs_refuse_scenario_overrides():
    with pytest.raises(ValidationError):
        SimulationRunCreate(configuration=CONFIG, scenario_parameters={"budget_usd": 10**9})
    with pytest.raises(ValidationError):
        SimulationRunCreate(configuration=CONFIG, seed=-1)


def test_guest_run_is_readable_by_id_and_in_no_history(container):
    sim = container.simulation_v4
    ada = container.auth.register("ada", "correct horse").user
    run = sim.launch(None, create())
    assert sim.get(None, run["run_id"])["run_id"] == run["run_id"]
    assert sim.get(ada, run["run_id"])["run_id"] == run["run_id"]
    assert sim.history(ada) == []


def test_missing_seed_gets_a_random_one_that_is_recorded(container):
    run = container.simulation_v4.launch(None, SimulationRunCreate(configuration=CONFIG))
    assert isinstance(run["result"]["seed"], int) and run["result"]["seed"] >= 0


def test_placeholder_runs_are_untouched(container, good_design):
    from backend.app.schemas import RunCreate
    ada = container.auth.register("ada", "correct horse").user
    container.simulation_v4.launch(ada, create())
    assert container.runs.history(ada) == []
    container.runs.start(ada, RunCreate(design=good_design, seed=1))
    assert len(container.runs.history(ada)) == 1 and len(container.simulation_v4.history(ada)) == 1
