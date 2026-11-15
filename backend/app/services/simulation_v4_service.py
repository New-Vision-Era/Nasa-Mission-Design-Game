"""Stored runs of the real-data engine (engine_v4): launch, read, history.

Same ownership rules as the placeholder runs (run_service.py):
- launched while logged in: belongs to that player and appears in their history;
- launched as a guest: no owner, readable by anyone holding its id, in no history.

The engine runs a whole mission in one call, so a stored run is always complete.
The backend stores and returns what the engine produces; it never adjusts a score.
"""

import json
import secrets
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Optional

from simulation.engine_v4 import api as engine_api

from backend.app.errors import ApiError, not_found
from backend.app.schemas import SimulationRunCreate, SimulationRunSummary, User
from backend.app.storage.db import Database, now_iso


class SimulationV4Service:
    def __init__(self, db: Database, data_dir: Path) -> None:
        self.db = db
        self.catalog_path = data_dir / "equipment_v4.json"
        self.scenario_dir = data_dir / "scenarios_v4"

    # -- stateless ---------------------------------------------------------------

    @staticmethod
    def unwrap(result: tuple[int, dict]) -> dict:
        """Engine (status, body) -> body, or the backend's standard ApiError."""
        status, payload = result
        if status == 200:
            return payload
        err = payload["error"]
        raise ApiError(status, err["code"], err["message"], err.get("field"),
                       {"details": err.get("details", [])})

    def catalog(self) -> dict:
        return self.unwrap(engine_api.handle_catalog_request(catalog_path=self.catalog_path))

    def scenarios(self) -> dict:
        return self.unwrap(engine_api.handle_scenarios_request(self.scenario_dir))

    def run(self, body: dict[str, Any]) -> dict:
        return self.unwrap(engine_api.handle_run_request(
            body, catalog_path=self.catalog_path, scenario_dir=self.scenario_dir))

    def recommend(self, body: dict[str, Any]) -> dict:
        return self.unwrap(engine_api.handle_recommend_request(
            body, catalog_path=self.catalog_path, scenario_dir=self.scenario_dir))

    # -- launch and store ----------------------------------------------------------

    def launch(self, user: Optional[User], body: SimulationRunCreate) -> dict:
        seed = body.seed if body.seed is not None else secrets.randbelow(2**31)
        result = self.run({"configuration": body.configuration,
                           "scenario_parameters": body.scenario_parameters, "seed": seed})
        if result["feasibility"]["status"] == "INFEASIBLE":
            raise ApiError(
                409, "not_launchable",
                "This design cannot launch: it fails hard constraint(s) "
                + ", ".join(result["feasibility"]["hard_failed"]) + ".",
                extra={"result": result},
            )
        run_id, now = uuid.uuid4().hex, now_iso()
        overrides = body.scenario_parameters or {}
        self.db.execute(
            "INSERT INTO simulation_runs (id, user_id, name, scenario_id, dataset_id, engine_version, seed, "
            "feasibility, outcome, score_total, uses_parameter_overrides, configuration_json, "
            "scenario_parameters_json, result_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, user.id if user else None, body.name, result["scenario"]["id"], result["dataset_id"],
             result["engine_version"], seed, result["feasibility"]["status"], result["mission"]["outcome"],
             result["score"]["total"], 1 if overrides else 0, json.dumps(result["configuration"]),
             json.dumps(overrides), json.dumps(result), now),
        )
        return self._view(self._row(user, run_id))

    # -- reading -------------------------------------------------------------------

    def _row(self, user: Optional[User], run_id: str) -> sqlite3.Row:
        row = self.db.query_one("SELECT * FROM simulation_runs WHERE id = ?", (run_id,))
        if row is None:
            raise not_found("Run")
        owner = row["user_id"]
        if owner is not None and (user is None or user.id != owner):
            raise not_found("Run")  # 404, not 403: do not reveal that it exists
        return row

    @staticmethod
    def _view(row: sqlite3.Row) -> dict:
        return {
            "run_id": row["id"],
            "name": row["name"],
            "created_at": row["created_at"],
            "status": "completed",
            "uses_parameter_overrides": bool(row["uses_parameter_overrides"]),
            "scenario_parameters": json.loads(row["scenario_parameters_json"]),
            "result": json.loads(row["result_json"]),
        }

    def get(self, user: Optional[User], run_id: str) -> dict:
        return self._view(self._row(user, run_id))

    def history(self, user: User, limit: int = 50, offset: int = 0) -> list[SimulationRunSummary]:
        """A player's stored real-data runs, newest first."""
        rows = self.db.query(
            "SELECT id, name, scenario_id, dataset_id, seed, feasibility, outcome, score_total, "
            "uses_parameter_overrides, created_at FROM simulation_runs WHERE user_id = ? "
            "ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?",
            (user.id, max(1, min(limit, 200)), max(0, offset)),
        )
        return [
            SimulationRunSummary(
                run_id=r["id"], name=r["name"], scenario_id=r["scenario_id"], dataset_id=r["dataset_id"],
                seed=r["seed"], feasibility=r["feasibility"], outcome=r["outcome"],
                score_total=r["score_total"], uses_parameter_overrides=bool(r["uses_parameter_overrides"]),
                created_at=r["created_at"],
            )
            for r in rows
        ]
