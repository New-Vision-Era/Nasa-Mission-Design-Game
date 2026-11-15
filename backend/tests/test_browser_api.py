"""The in-browser backend (GitHub Pages) answers like the FastAPI routes the game uses."""
import json

import pytest

from backend.app.browser_api import BrowserApi
from backend.app.services import auth_service

CONF = {
    "scenario_id": "earth_observation_v4", "platform_id": "gsat_50", "instrument_ids": ["hyperscape100"],
    "power": {"mode": "platform_payload_budget", "solar_array_ids": [], "battery_ids": [], "eps_id": None},
    "communication_system_ids": ["endurosat_s_band_transceiver", "endurosat_x_band_transmitter"],
    "adcs_system_id": "cubespace_cubeadcs_3axis_small_star", "propulsion_system_id": None,
    "orbit_id": "sso_500", "launch_vehicle_id": "rocket_lab_electron",
}


@pytest.fixture()
def call():
    api = BrowserApi(":memory:")

    def _call(method, path, body=None, token=None):
        out = json.loads(api.handle(method, "/api/v1" + path, json.dumps(body) if body is not None else None, token))
        return out["status"], out["body"]
    return _call


def test_full_earth_mission_with_account(call):
    status, auth = call("POST", "/auth/register", {"username": "pilot", "password": "password123"})
    assert status == 201
    token = auth["token"]
    assert call("GET", "/auth/me", token=token)[1]["username"] == "pilot"
    assert call("POST", "/simulation/evaluate", {"configuration": CONF})[1]["launch_assessment"]["status"] == "GO"
    status, view = call("POST", "/simulation/missions", {"configuration": CONF, "seed": 3}, token)
    assert status == 201
    while view["status"] == "AWAITING_DECISION":
        pd = view["state"]["pending_decision"]
        default = next(r["id"] for r in pd["responses"] if r["is_default"])
        status, view = call("POST", f"/simulation/missions/{view['mission_id']}/decisions",
                            {"anomaly_id": pd["anomaly_id"], "response_id": default}, token)
        assert status == 200
    assert view["status"] == "COMPLETED" and view["debrief"]["score"]["total"] > 0
    assert len(call("GET", "/simulation/missions", token=token)[1]) == 1


def test_surface_missions_and_errors(call):
    assert call("GET", "/surface/moon/catalog")[0] == 200
    assert call("POST", "/surface/mars/fly", {"selection": {"instruments": []}})[1]["status"] == "NOT_LAUNCHED"
    assert call("GET", "/surface/venus/catalog")[0] == 404
    assert call("GET", "/simulation/missions")[0] == 401
    assert call("POST", "/auth/register", {"username": "x", "password": "short"})[0] == 422
    assert call("GET", "/nope")[0] == 404


def test_pbkdf2_fallback_matches_the_standard(monkeypatch):
    import hashlib
    assert auth_service._pbkdf2_sha256(b"pw", b"salt", 500) == hashlib.pbkdf2_hmac("sha256", b"pw", b"salt", 500)
    monkeypatch.delattr(hashlib, "scrypt")  # as in the browser
    api = BrowserApi(":memory:")
    reg = json.loads(api.handle("POST", "/api/v1/auth/register", json.dumps({"username": "web", "password": "password123"}), None))
    assert reg["status"] == 201
    login = json.loads(api.handle("POST", "/api/v1/auth/login", json.dumps({"username": "web", "password": "password123"}), None))
    assert login["status"] == 200
