"""Real-data simulation engine (dataset equipment_v5). Additive: no existing route changes.

Thin wrapper only. All logic lives in simulation.engine_v4, which is tested
without a web framework. The backend never computes or adjusts a score here.
"""
from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import HTMLResponse

from simulation.engine_v4.devui import PAGE

from backend.app.deps import ContainerDep, CurrentUser, OptionalUser
from backend.app.schemas import SimulationRunCreate, SimulationRunSummary

router = APIRouter(prefix="/simulation", tags=["Simulation engine v4 (real data)"])


@router.get("/catalog")
def v4_catalog(container: ContainerDep) -> dict[str, Any]:
    """The real component catalog: every record with its original fields, sources and caveats."""
    return container.simulation_v4.catalog()


@router.get("/scenarios")
def v4_scenarios(container: ContainerDep) -> dict[str, Any]:
    """Scenario briefings and their default parameters (all gameplay assumptions)."""
    return container.simulation_v4.scenarios()


@router.post("/run")
def v4_run(container: ContainerDep, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Validate, evaluate, simulate, score and explain one configuration. Stateless: nothing is stored.

    Body: {"configuration": {...}, "scenario_parameters": {...}?, "seed": int?}. This is the sandbox:
    scenario_parameters may override gameplay values here, but never on stored runs.
    An infeasible design is a normal 200 result with failed constraints.
    """
    return container.simulation_v4.run(body)


@router.post("/recommend")
def v4_recommend(container: ContainerDep, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """A few non-dominated alternative designs for the same scenario."""
    return container.simulation_v4.recommend(body)


@router.post("/runs", status_code=201)
def v4_launch(body: SimulationRunCreate, user: OptionalUser, container: ContainerDep) -> dict[str, Any]:
    """Launch a design with the real-data engine and store the result.

    Body: {"configuration": {...}, "seed": int?, "name": str?}. The scenario's own parameters
    are always used; scenario_parameters is rejected (422).

    Logged in: the run is saved to the player's history. Guest: the run is stored
    without an owner and appears in no history. 409 not_launchable if a hard
    constraint fails (the error then carries the full result). A CONDITIONAL
    design launches and is flagged as such in the result.
    """
    return container.simulation_v4.launch(user, body)


@router.get("/runs", response_model=list[SimulationRunSummary])
def v4_history(user: CurrentUser, container: ContainerDep, limit: int = 50,
               offset: int = 0) -> list[SimulationRunSummary]:
    """The logged-in player's stored real-data runs, newest first."""
    return container.simulation_v4.history(user, limit=limit, offset=offset)


@router.get("/runs/{run_id}")
def v4_get_run(run_id: str, user: OptionalUser, container: ContainerDep) -> dict[str, Any]:
    """One stored run in full: configuration flown, constraints, score, mission and debrief."""
    return container.simulation_v4.get(user, run_id)


@router.get("/testbench", response_class=HTMLResponse, include_in_schema=False)
def v4_testbench() -> HTMLResponse:
    """Developer test page for the engine. Not the game UI."""
    return HTMLResponse(PAGE.read_text(encoding="utf-8"))


# -- MCAS: resumable, decision-driven mission runs -----------------------------

@router.post("/evaluate")
def mcas_evaluate(container: ContainerDep, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Evaluate feasibility and MCAS risk before launching; no mission is started."""
    return container.simulation_v4.evaluate_interactive(body)


@router.post("/missions", status_code=201)
def mcas_start(body: dict[str, Any] = Body(...), user: OptionalUser = None,
               container: ContainerDep = None) -> dict[str, Any]:
    """Start a step-by-step MCAS mission and persist its JSON state."""
    return container.simulation_v4.start_mcas(user, body)


@router.get("/missions")
def mcas_history(user: CurrentUser, container: ContainerDep, limit: int = 50,
                 offset: int = 0) -> list[dict[str, Any]]:
    """List the logged-in player's interactive mission history."""
    return container.simulation_v4.mcas_history(user, limit=limit, offset=offset)


@router.get("/missions/{mission_id}")
def mcas_get(mission_id: str, user: OptionalUser, container: ContainerDep) -> dict[str, Any]:
    """Retrieve the current state of an interactive mission."""
    return container.simulation_v4.get_mcas(user, mission_id)


@router.post("/missions/{mission_id}/decisions")
def mcas_decide(mission_id: str, body: dict[str, Any] = Body(...), user: OptionalUser = None,
                container: ContainerDep = None) -> dict[str, Any]:
    """Apply the player's response and advance to the next decision or mission completion."""
    return container.simulation_v4.decide_mcas(user, mission_id, body)


@router.get("/missions/{mission_id}/debrief")
def mcas_debrief(mission_id: str, user: OptionalUser, container: ContainerDep) -> dict[str, Any]:
    """Return the completed mission's explainable debrief and score."""
    return container.simulation_v4.mcas_debrief(user, mission_id)
