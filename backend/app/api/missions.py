from fastapi import APIRouter

from backend.app.deps import ContainerDep, CurrentUser
from backend.app.schemas import MissionCreate, MissionUpdate, MissionView, RunSummary

router = APIRouter(prefix="/missions", tags=["missions"])


@router.post("", response_model=MissionView, status_code=201)
def create_mission(body: MissionCreate, user: CurrentUser, container: ContainerDep) -> MissionView:
    return container.missions.create(user, body)


@router.get("", response_model=list[MissionView])
def list_missions(user: CurrentUser, container: ContainerDep) -> list[MissionView]:
    """The logged-in player's saved missions, most recently edited first."""
    return container.missions.list(user)


@router.get("/{mission_id}", response_model=MissionView)
def get_mission(mission_id: str, user: CurrentUser, container: ContainerDep) -> MissionView:
    return container.missions.get(user, mission_id)


@router.put("/{mission_id}", response_model=MissionView)
def update_mission(
    mission_id: str, body: MissionUpdate, user: CurrentUser, container: ContainerDep
) -> MissionView:
    return container.missions.update(user, mission_id, body)


@router.delete("/{mission_id}", status_code=204)
def delete_mission(mission_id: str, user: CurrentUser, container: ContainerDep) -> None:
    container.missions.delete(user, mission_id)


@router.get("/{mission_id}/runs", response_model=list[RunSummary])
def mission_runs(mission_id: str, user: CurrentUser, container: ContainerDep) -> list[RunSummary]:
    """Every past run of one saved mission, for comparing attempts."""
    container.missions.get(user, mission_id)  # 404 if it is not this player's
    return container.runs.history(user, mission_id=mission_id)
