"""Service tests for persisted MCAS missions on the existing equipment_v5 backend."""

import pytest

from backend.app.errors import ApiError
from backend.app.services.simulation_v4_service import SimulationV4Service

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


def test_interactive_mission_state_is_persisted_and_resumable(container):
    user = container.auth.register("mcas_player", "correct horse").user
    service = container.simulation_v4
    mission = service.start_mcas(user, {
        "configuration": CONFIG,
        "seed": 19,
        "scenario_parameters": {
            "data_generation_kbps": {"hyperscape100": 20000},
            "events": {"enabled": False},
        },
    })

    assert mission["mission_id"]
    assert mission["state"]["configuration"]["platform_id"] == "gsat_50"
    assert mission["status"] in {"AWAITING_DECISION", "COMPLETED", "NOT_LAUNCHED"}

    # A fresh service instance proves the mission is not relying on process memory.
    restarted = SimulationV4Service(container.db, container.settings.data_dir)
    loaded = restarted.get_mcas(user, mission["mission_id"])
    assert loaded["state"] == mission["state"]
    assert loaded["status"] == mission["status"]

    if mission["status"] == "AWAITING_DECISION":
        pending = mission["state"]["pending_decision"]
        default = next(r for r in pending["responses"] if r["is_default"])
        updated = restarted.decide_mcas(user, mission["mission_id"], {
            "anomaly_id": pending["anomaly_id"],
            "response_id": default["id"],
        })
        assert updated["state"]["decisions"][pending["anomaly_id"]] == default["id"]
        assert updated["status"] in {"AWAITING_DECISION", "COMPLETED"}

        # The updated decision and state must also survive a service restart.
        again = SimulationV4Service(container.db, container.settings.data_dir)
        persisted = again.get_mcas(user, mission["mission_id"])
        assert persisted["state"] == updated["state"]


def test_interactive_mission_ownership_is_private(container):
    ada = container.auth.register("mcas_ada", "correct horse").user
    bob = container.auth.register("mcas_bob", "correct horse").user
    mission = container.simulation_v4.start_mcas(None, {
        "configuration": CONFIG, "seed": 2,
        "scenario_parameters": {"events": {"enabled": False}},
    })

    # Guest missions are readable by id, but never appear in player history.
    assert container.simulation_v4.get_mcas(ada, mission["mission_id"])["mission_id"] == mission["mission_id"]
    assert container.simulation_v4.mcas_history(ada) == []

    owned = container.simulation_v4.start_mcas(ada, {
        "configuration": CONFIG, "seed": 3,
        "scenario_parameters": {"events": {"enabled": False}},
    })
    with pytest.raises(ApiError) as exc:
        container.simulation_v4.get_mcas(bob, owned["mission_id"])
    assert exc.value.status == 404
    assert [r["mission_id"] for r in container.simulation_v4.mcas_history(ada)] == [owned["mission_id"]]


def test_interactive_mission_rejects_malformed_decision(container):
    user = container.auth.register("mcas_invalid", "correct horse").user
    mission = container.simulation_v4.start_mcas(user, {
        "configuration": CONFIG, "seed": 4,
        "scenario_parameters": {"data_generation_kbps": {"hyperscape100": 20000},
                                "events": {"enabled": False}},
    })
    if mission["status"] != "AWAITING_DECISION":
        pytest.skip("This configuration did not produce a decision point with the current dataset.")
    with pytest.raises(ApiError) as exc:
        container.simulation_v4.decide_mcas(user, mission["mission_id"], {
            "anomaly_id": mission["state"]["pending_decision"]["anomaly_id"],
            "response_id": "not-a-real-response",
        })
    assert exc.value.status == 422
