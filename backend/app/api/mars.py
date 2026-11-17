"""Mars rover-specific API; the existing satellite API remains untouched."""
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from backend.app.services.mars_mission import EQUIPMENT, calculate, simulate

router = APIRouter(prefix="/mars", tags=["Mars rover mission"])

class MarsSelection(BaseModel):
    launch: str | None = None
    power: str | None = None
    comm: str | None = None
    landing: str | None = None
    instruments: list[str] = Field(default_factory=list)

class MarsSimulationResponse(BaseModel):
    outcome: str
    stages: list[dict[str, Any]]
    metrics: dict[str, Any]
    resources: dict[str, Any]
    selectionSnapshot: dict[str, Any]
    validation: dict[str, Any]

@router.get("/catalog")
def mars_catalog() -> dict[str, Any]:
    """Return Mars rover equipment and educational game limits."""
    return {"mission":{"name":"MARS ROVER EXPLORATION","budgetLimitM":100,
        "massLimitKg":2000,"baseLoadW":200,"durationYears":3,
        "disclaimer":"Illustrative educational game values, not official NASA specifications."},
        "categories":EQUIPMENT}

@router.post("/evaluate")
def evaluate_mars(body: MarsSelection) -> dict[str, Any]:
    """Validate a partial Mars rover design and return resource checks."""
    try: return calculate(body.model_dump())
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.post("/simulate", response_model=MarsSimulationResponse)
def simulate_mars(body: MarsSelection) -> dict[str, Any]:
    """Run the deterministic four-stage Mars rover simulation."""
    try: return simulate(body.model_dump())
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
