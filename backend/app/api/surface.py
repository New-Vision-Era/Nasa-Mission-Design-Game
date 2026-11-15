"""Surface missions (Mars rover, lunar lander) for the game UI. Additive: /mars routes are unchanged.

Thin wrapper only: the rules live in backend/app/services/surface_mission.py.
"""
from typing import Any

from fastapi import APIRouter, Body

from backend.app.errors import ApiError
from backend.app.services import surface_mission as engine

router = APIRouter(prefix="/surface", tags=["Surface missions (Mars, Moon)"])


def _call(fn, *args):
    try:
        return fn(*args)
    except engine.SurfaceError as exc:
        status = 404 if str(exc).startswith("Unknown surface mission") else 422
        raise ApiError(status, "not_found" if status == 404 else "invalid_request", str(exc)) from None


@router.get("/{mission_id}/catalog")
def surface_catalog(mission_id: str) -> dict[str, Any]:
    """Equipment, limits and briefing. Values are illustrative game values (see value_note)."""
    return _call(engine.catalog, mission_id)


@router.post("/{mission_id}/evaluate")
def surface_evaluate(mission_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Body {selection}. Resources, checks and the launch verdict GO / RISKY / NO_GO."""
    return _call(engine.evaluate, mission_id, body.get("selection"))


@router.post("/{mission_id}/fly")
def surface_fly(mission_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Body {selection, decisions?}. Stops at the landing decision, or returns the finished mission."""
    return _call(engine.fly, mission_id, body.get("selection"), body.get("decisions"))


@router.post("/{mission_id}/recommend")
def surface_recommend(mission_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Body {selection}. The best launchable designs by score."""
    return _call(engine.recommend, mission_id, body.get("selection"))
