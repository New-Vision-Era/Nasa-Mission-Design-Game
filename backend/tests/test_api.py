"""HTTP-level tests. Skipped automatically if fastapi/httpx are not installed."""

import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.config import REPO_ROOT, Settings  # noqa: E402
from backend.app.main import create_app  # noqa: E402

API = "/api/v1"


@pytest.fixture()
def client():
    with TestClient(create_app(Settings(database_path=":memory:"))) as c:
        yield c


@pytest.fixture()
def design():
    return json.loads((REPO_ROOT / "data" / "fixtures" / "design_example.json").read_text())


def register(client, name):
    r = client.post(f"{API}/auth/register", json={"username": name, "password": "correct horse"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_health_scenarios_catalog(client):
    assert client.get(f"{API}/health").json()["status"] == "ok"
    assert client.get(f"{API}/scenarios").json()["scenarios"][0]["id"] == "earth_observation_01"
    cat = client.get(f"{API}/catalog", params={"scenario_id": "earth_observation_01"}).json()
    assert "instrument" in cat["categories"] and cat["data_status"] in ("mock", "reviewed")
    assert client.get(f"{API}/catalog", params={"scenario_id": "nope"}).status_code == 404


def test_error_shape(client, design):
    r = client.post(f"{API}/evaluate", json={})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request" and r.json()["error"]["field"] == "scenario_id"

    design["orbit_id"] = "no_such_orbit"
    r = client.post(f"{API}/evaluate", json=design)
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_component"

    r = client.post(f"{API}/auth/register", json={"username": "ada", "password": "short"})
    assert r.status_code == 422 and "short" not in r.text  # the password is never echoed


def test_auth_is_required_where_it_should_be(client, design):
    assert client.get(f"{API}/missions").status_code == 401
    assert client.get(f"{API}/runs").status_code == 401
    assert client.get(f"{API}/auth/me").status_code == 401
    bad = {"Authorization": "Bearer not-a-real-token"}
    assert client.get(f"{API}/auth/me", headers=bad).json()["error"]["code"] == "invalid_token"
    assert client.post(f"{API}/evaluate", json=design).status_code == 200  # public


def test_full_journey_over_http(client, design):
    ada = register(client, "ada")
    assert client.get(f"{API}/auth/me", headers=ada).json()["username"] == "ada"

    broken = json.loads(json.dumps(design))
    broken["spacecraft"]["instrument_ids"] = ["hyperspectral_imager"]
    r = client.post(f"{API}/runs", json={"design": broken}, headers=ada)
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_launchable"
    assert r.json()["error"]["evaluation"]["launchable"] is False

    mission = client.post(f"{API}/missions", json={"name": "Earth Watch A", "design": design}, headers=ada)
    assert mission.status_code == 201
    mission_id = mission.json()["mission_id"]

    r = client.post(f"{API}/runs", json={"design": design, "mission_id": mission_id, "seed": 7}, headers=ada)
    assert r.status_code == 201, r.text
    run = r.json()
    while run["status"] == "awaiting_decision":
        event = run["pending_event"]
        r = client.post(
            f"{API}/runs/{run['run_id']}/decisions",
            json={"event_id": event["event_id"], "option_id": event["options"][0]["option_id"]},
            headers=ada,
        )
        assert r.status_code == 200, r.text
        run = r.json()
    assert run["debrief"]["score"]["total"] >= 0

    history = client.get(f"{API}/runs", headers=ada).json()
    assert [h["run_id"] for h in history] == [run["run_id"]]
    assert client.get(f"{API}/missions/{mission_id}/runs", headers=ada).json()[0]["run_id"] == run["run_id"]

    bob = register(client, "bob")
    assert client.get(f"{API}/runs", headers=bob).json() == []
    assert client.get(f"{API}/runs/{run['run_id']}", headers=bob).status_code == 404
    assert client.get(f"{API}/runs/{run['run_id']}").status_code == 404
    assert client.get(f"{API}/missions/{mission_id}", headers=bob).status_code == 404

    assert client.post(f"{API}/auth/logout", headers=ada).status_code == 204
    assert client.get(f"{API}/auth/me", headers=ada).status_code == 401
