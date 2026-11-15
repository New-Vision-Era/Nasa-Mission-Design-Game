"""FastAPI wrapper for the v4 engine. Copy to backend/app/api/simulation_v4.py.

NOT EXECUTED where it was written (FastAPI was not installed there). The logic it
calls, simulation.engine_v4.api, is fully tested without a web framework.

Register in backend/app/main.py:
    from .api import simulation_v4
    app.include_router(simulation_v4.router, prefix="/api/v1")
"""
from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from simulation.engine_v4 import api as engine_api

router = APIRouter(prefix="/simulation", tags=["simulation-v4"])


@router.post("/run")
def run(body: Any = Body(...)) -> JSONResponse:
    status, payload = engine_api.handle_run_request(body)
    return JSONResponse(status_code=status, content=payload)


@router.post("/recommend")
def recommend(body: Any = Body(...)) -> JSONResponse:
    status, payload = engine_api.handle_recommend_request(body)
    return JSONResponse(status_code=status, content=payload)


@router.get("/catalog")
def catalog() -> JSONResponse:
    status, payload = engine_api.handle_catalog_request()
    return JSONResponse(status_code=status, content=payload)
