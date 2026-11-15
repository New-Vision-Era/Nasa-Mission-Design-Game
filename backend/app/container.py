"""Builds every service once. No FastAPI here, so tests can use it directly."""

from dataclasses import dataclass

from simulation.models import Catalog

from backend.app.config import Settings
from backend.app.services.auth_service import AuthService
from backend.app.services.catalog_loader import load_catalog
from backend.app.services.engine_adapter import EngineAdapter
from backend.app.services.mission_service import MissionService
from backend.app.services.run_service import RunService
from backend.app.services.simulation_v4_service import SimulationV4Service
from backend.app.storage.db import Database


@dataclass
class Container:
    settings: Settings
    catalog: Catalog
    db: Database
    auth: AuthService
    missions: MissionService
    runs: RunService
    simulation_v4: SimulationV4Service


def build_container(settings: Settings) -> Container:
    catalog = load_catalog(settings.data_dir)  # raises CatalogError on bad data
    db = Database(settings.database_path)
    engine = EngineAdapter(catalog)
    return Container(
        settings=settings,
        catalog=catalog,
        db=db,
        auth=AuthService(db, settings.session_ttl_hours),
        missions=MissionService(db, catalog),
        runs=RunService(db, catalog, engine),
        simulation_v4=SimulationV4Service(db, settings.data_dir),
    )
