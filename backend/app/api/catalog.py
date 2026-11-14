from typing import Optional

from fastapi import APIRouter

from backend.app.deps import ContainerDep
from backend.app.schemas import CatalogView, Health, ScenarioList
from backend.app.services.design_validation import get_scenario

router = APIRouter(tags=["catalog"])


@router.get("/health", response_model=Health)
def health(container: ContainerDep) -> Health:
    c = container.catalog
    return Health(catalog_version=c.catalog_version, data_status=c.data_status)


@router.get("/scenarios", response_model=ScenarioList)
def scenarios(container: ContainerDep) -> ScenarioList:
    c = container.catalog
    return ScenarioList(
        catalog_version=c.catalog_version, data_status=c.data_status, scenarios=list(c.scenarios.values())
    )


@router.get("/catalog", response_model=CatalogView)
def catalog(container: ContainerDep, scenario_id: Optional[str] = None) -> CatalogView:
    """Every selectable component, grouped by category. data_status 'mock' means placeholder numbers."""
    c = container.catalog
    allowed = None
    if scenario_id is not None:
        scenario = get_scenario(c, scenario_id)
        allowed = set(scenario.allowed_component_ids) if scenario.allowed_component_ids else None
    categories: dict[str, list] = {}
    for component in c.components.values():
        if allowed is None or component.id in allowed:
            categories.setdefault(component.category, []).append(component)
    return CatalogView(
        catalog_version=c.catalog_version,
        data_status=c.data_status,
        categories=categories,
        sources=list(c.sources.values()),
    )
