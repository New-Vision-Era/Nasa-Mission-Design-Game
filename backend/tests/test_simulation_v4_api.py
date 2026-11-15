"""HTTP tests for the additive real-data simulation API. Skipped if fastapi/httpx are missing."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.config import Settings  # noqa: E402
from backend.app.main import create_app  # noqa: E402

API = "/api/v1/simulation"

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


@pytest.fixture()
def client():
    with TestClient(create_app(Settings(database_path=":memory:"))) as c:
        yield c


def test_v4_catalog_and_scenarios(client):
    cat = client.get(f"{API}/catalog")
    assert cat.status_code == 200
    body = cat.json()
    assert body["dataset_id"] == "equipment_v4"
    assert {k: len(v) for k, v in body["categories"].items()} == {
        "platforms": 3, "instruments": 21, "power_systems": 17, "communication_systems": 8,
        "propulsion_systems": 9, "adcs_systems": 7, "orbits": 5, "launch_vehicles": 7}
    assert body["categories"]["platforms"][0]["bus_mass_kg"] is None  # null stays null over HTTP
    scenarios = client.get(f"{API}/scenarios").json()["scenarios"]
    assert scenarios[0]["id"] == "earth_observation_v4"


def test_v4_run_real_data_is_conditional(client):
    r = client.post(f"{API}/run", json={"configuration": CONFIG, "seed": 42})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["feasibility"]["status"] == "CONDITIONAL"
    assert body["feasibility"]["hard_not_evaluated"] == ["launch_mass"]
    assert body["mission"]["outcome"] == "SUCCESS"
    assert 0 <= body["score"]["total"] <= 100
    for key in ("constraints", "resources", "performance", "explanations", "assumptions", "provenance"):
        assert key in body


def test_v4_run_with_gameplay_assumptions_is_feasible(client):
    r = client.post(f"{API}/run", json={"configuration": CONFIG,
                                        "scenario_parameters": {"bus_mass_kg_assumption": 40}})
    assert r.status_code == 200
    assert r.json()["feasibility"]["status"] == "FEASIBLE"


def test_v4_infeasible_design_is_a_normal_200(client):
    r = client.post(f"{API}/run", json={"configuration": {**CONFIG, "instrument_ids": ["dragoneye"]}})
    assert r.status_code == 200
    body = r.json()
    assert body["feasibility"]["status"] == "INFEASIBLE" and body["mission"]["launched"] is False


def test_v4_same_seed_same_result(client):
    payload = {"configuration": CONFIG, "seed": 7}
    assert client.post(f"{API}/run", json=payload).json() == client.post(f"{API}/run", json=payload).json()


@pytest.mark.parametrize("payload,status,code", [
    ({"configuration": {**CONFIG, "platform_id": "gsat_999"}}, 422, "unknown_component"),
    ({"configuration": {**CONFIG, "scenario_id": "nope"}}, 404, "not_found"),
    ({"configuration": {"scenario_id": "earth_observation_v4"}}, 422, "invalid_request"),
    ({"configuration": CONFIG, "scenario_parameters": {"passes_per_day": -1}}, 422, "invalid_request"),
    ({"seed": 1}, 422, "invalid_request"),
])
def test_v4_errors_use_the_backend_error_shape(client, payload, status, code):
    r = client.post(f"{API}/run", json=payload)
    assert r.status_code == status, r.text
    error = r.json()["error"]
    assert error["code"] == code and error["message"]


def test_v4_recommend(client):
    r = client.post(f"{API}/recommend", json={"configuration": CONFIG,
                                              "scenario_parameters": {"bus_mass_kg_assumption": 40}})
    assert r.status_code == 200
    alternatives = r.json()["alternatives"]
    assert 1 <= len(alternatives) <= 5
    assert all(a["feasibility"] != "INFEASIBLE" for a in alternatives)


def test_v4_testbench_page_is_served(client):
    r = client.get(f"{API}/testbench")
    assert r.status_code == 200 and "Engine v4 test bench" in r.text


def test_existing_routes_still_work(client):
    assert client.get("/api/v1/health").json()["status"] == "ok"
    assert client.get("/api/v1/mars/catalog").status_code == 200
