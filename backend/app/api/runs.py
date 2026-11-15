from fastapi import APIRouter

from simulation.models import Decision

from backend.app.deps import ContainerDep, CurrentUser, OptionalUser
from backend.app.schemas import RunCreate, RunSummary, RunView

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunView, status_code=201)
def launch(body: RunCreate, user: OptionalUser, container: ContainerDep) -> RunView:
    """Launch a complete design.

    Logged in: the run is saved to the player's history. Guest: the run works
    but appears in no history. 409 not_launchable if the design is incomplete
    or fails a hard constraint (the body then includes the evaluation).
    """
    return container.runs.start(user, body)


@router.get("", response_model=list[RunSummary])
def history(user: CurrentUser, container: ContainerDep, limit: int = 50, offset: int = 0) -> list[RunSummary]:
    """The logged-in player's mission history, newest first."""
    return container.runs.history(user, limit=limit, offset=offset)


@router.get("/{run_id}", response_model=RunView)
def get_run(run_id: str, user: OptionalUser, container: ContainerDep) -> RunView:
    """Full detail of one run: design flown, log, and the debrief once complete."""
    return container.runs.get(user, run_id)


@router.post("/{run_id}/decisions", response_model=RunView)
def decide(run_id: str, body: Decision, user: OptionalUser, container: ContainerDep) -> RunView:
    """Answer the pending event; returns the next run state."""
    return container.runs.decide(user, run_id, body)
