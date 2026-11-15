"""API-only request and response bodies (accounts, saved missions, run views).

Game models (Design, Evaluation, RunState, Debrief...) live in simulation/models.py.
"""

from typing import Optional

from pydantic import BaseModel, Field

from simulation.models import Component, Debrief, Design, RunState, Scenario, Source


# --- accounts --------------------------------------------------------------


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)


class User(BaseModel):
    id: str
    username: str
    created_at: str


class AuthResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_at: str
    user: User


# --- catalog ---------------------------------------------------------------


class Health(BaseModel):
    status: str = "ok"
    catalog_version: str
    data_status: str


class ScenarioList(BaseModel):
    catalog_version: str
    data_status: str
    scenarios: list[Scenario]


class CatalogView(BaseModel):
    catalog_version: str
    data_status: str
    categories: dict[str, list[Component]]
    sources: list[Source]


# --- saved missions --------------------------------------------------------


class MissionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    design: Design


class MissionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    design: Optional[Design] = None


class MissionView(BaseModel):
    mission_id: str
    name: str
    scenario_id: str
    design: Design
    created_at: str
    updated_at: str
    run_count: int = 0
    best_score: Optional[float] = None


# --- runs ------------------------------------------------------------------


class RunCreate(BaseModel):
    design: Design
    mission_id: Optional[str] = None  # attach the run to a saved mission
    seed: Optional[int] = Field(default=None, ge=0)  # fix it to replay a run exactly


class RunView(RunState):
    run_id: str
    mission_id: Optional[str] = None
    scenario_id: str
    catalog_version: str
    created_at: str
    completed_at: Optional[str] = None
    debrief: Optional[Debrief] = None


class RunSummary(BaseModel):
    """One row of a player's mission history."""

    run_id: str
    mission_id: Optional[str] = None
    mission_name: Optional[str] = None
    scenario_id: str
    status: str
    outcome: Optional[str] = None
    score_total: Optional[float] = None
    created_at: str
    completed_at: Optional[str] = None
