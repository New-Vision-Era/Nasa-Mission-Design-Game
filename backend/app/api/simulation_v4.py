"""Real-data simulation engine (equipment_v4). Additive: no existing route changes.

Thin wrapper only. All logic lives in simulation.engine_v4, which is tested
without a web framework. The backend never computes or adjusts a score here.
"""
from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import HTMLResponse

from simulation.engine_v4 import api as engine_api
from simulation.engine_v4.devui import PAGE

from backend.app.deps import ContainerDep
from backend.app.errors import ApiError

router = APIRouter(prefix="/simulation", tags=["Simulation engine v4 (real data)"])


def _paths(container) -> dict[str, Any]:
    data_dir = container.settings.data_dir
    return {"catalog_path": data_dir / "equipment_v4.json", "scenario_dir": data_dir / "scenarios_v4"}


def _respond(result: tuple[int, dict]) -> dict:
    """Engine (status, body) -> JSON, or the backend's standard ApiError."""
    status, payload = result
    if status == 200:
        return payload
    err = payload["error"]
    raise ApiError(status, err["code"], err["message"], err.get("field"), {"details": err.get("details", [])})


@router.get("/catalog")
def v4_catalog(container: ContainerDep) -> dict[str, Any]:
    """The real component catalog: every record with its original fields, sources and caveats."""
    return _respond(engine_api.handle_catalog_request(catalog_path=_paths(container)["catalog_path"]))


@router.get("/scenarios")
def v4_scenarios(container: ContainerDep) -> dict[str, Any]:
    """Scenario briefings and their default parameters (all gameplay assumptions)."""
    return _respond(engine_api.handle_scenarios_request(_paths(container)["scenario_dir"]))


@router.post("/run")
def v4_run(container: ContainerDep, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Validate, evaluate, simulate, score and explain one mission configuration.

    Body: {"configuration": {...}, "scenario_parameters": {...}?, "seed": int?}.
    An infeasible design is a normal 200 result with failed constraints.
    """
    return _respond(engine_api.handle_run_request(body, **_paths(container)))


@router.post("/recommend")
def v4_recommend(container: ContainerDep, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """A few non-dominated alternative designs for the same scenario."""
    return _respond(engine_api.handle_recommend_request(body, **_paths(container)))


@router.get("/testbench", response_class=HTMLResponse, include_in_schema=False)
def v4_testbench() -> HTMLResponse:
    """Developer test page for the engine. Not the game UI."""
    return HTMLResponse(PAGE.read_text(encoding="utf-8"))
