"""Stored runs of the real-data engine v4, including resumable MCAS missions.

The legacy one-call /simulation/runs API remains unchanged. Interactive mission state
is persisted as JSON so a player can leave and resume between HTTP requests or processes.
"""

import json
import secrets
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Optional

from simulation.engine_v4 import api as engine_api
from simulation.engine_v4 import interactive
from simulation.engine_v4.configuration import ConfigError
from simulation.engine_v4.data_loader import CatalogError, load_catalog
from simulation.engine_v4.mission.mcas.models import DecisionError, AWAITING_DECISION, COMPLETED, NOT_LAUNCHED

from backend.app.errors import ApiError, not_found
from backend.app.schemas import SimulationRunCreate, SimulationRunSummary, User
from backend.app.storage.db import Database, now_iso


class SimulationV4Service:
    def __init__(self, db: Database, data_dir: Path) -> None:
        self.db = db
        self.catalog_path = data_dir / "equipment_v5.json"
        self.scenario_dir = data_dir / "scenarios_v4"
        # Reuse the integration branch's equipment_v5 catalog. Do not replace it
        # with the older equipment_v4 dataset shipped with the MCAS source bundle.
        self.engine_catalog = load_catalog(self.catalog_path)

    # -- shared engine error translation -----------------------------------------

    @staticmethod
    def unwrap(result: tuple[int, dict]) -> dict:
        """Engine (status, body) -> body, or the backend's standard ApiError."""
        status, payload = result
        if status == 200:
            return payload
        err = payload["error"]
        raise ApiError(status, err["code"], err["message"], err.get("field"),
                       {"details": err.get("details", [])})

    def _interactive_call(self, func, *args):
        try:
            return func(*args, catalog=self.engine_catalog)
        except ConfigError as exc:
            first = exc.errors[0] if exc.errors else {
                "code": "invalid_request", "message": "Invalid configuration.", "field": None
            }
            status = 404 if first["code"] == "not_found" else 422
            raise ApiError(status, first["code"], first["message"], first.get("field"),
                           {"details": exc.errors}) from None
        except DecisionError as exc:
            statuses = {
                "not_found": 404, "no_pending_decision": 409, "wrong_anomaly": 409,
                "decision_pending": 409, "response_unavailable": 409,
                "unknown_response": 422, "unknown_anomaly": 422, "invalid_state": 422,
            }
            raise ApiError(statuses.get(exc.code, 409), exc.code, exc.message) from None
        except CatalogError:
            raise ApiError(500, "internal_error", "The component dataset could not be loaded.") from None

    # -- stateless endpoints ------------------------------------------------------

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

    def evaluate_interactive(self, body: dict[str, Any]) -> dict:
        if not isinstance(body, dict) or not isinstance(body.get("configuration"), dict):
            raise ApiError(422, "invalid_request",
                           "Body must contain a 'configuration' object.", "configuration")
        return self._interactive_call(
            interactive.evaluate_design, body["configuration"], body.get("scenario_parameters")
        )

    # -- existing one-call launch and store (unchanged contract) ------------------

    def launch(self, user: Optional[User], body: SimulationRunCreate) -> dict:
        seed = body.seed if body.seed is not None else secrets.randbelow(2**31)
        result = self.run({"configuration": body.configuration, "seed": seed})  # scenario values only
        if result["feasibility"]["status"] == "INFEASIBLE":
            raise ApiError(
                409, "not_launchable",
                "This design cannot launch: it fails hard constraint(s) "
                + ", ".join(result["feasibility"]["hard_failed"]) + ".",
                extra={"result": result},
            )
        run_id, now = uuid.uuid4().hex, now_iso()
        self.db.execute(
            "INSERT INTO simulation_runs (id, user_id, name, scenario_id, dataset_id, engine_version, seed, "
            "feasibility, outcome, score_total, uses_parameter_overrides, configuration_json, "
            "scenario_parameters_json, result_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, user.id if user else None, body.name, result["scenario"]["id"], result["dataset_id"],
             result["engine_version"], seed, result["feasibility"]["status"], result["mission"]["outcome"],
             result["score"]["total"], 0, json.dumps(result["configuration"]),
             "{}", json.dumps(result), now),
        )
        return self._view(self._row(user, run_id))

    # -- MCAS interactive missions -------------------------------------------------

    @staticmethod
    def _validate_mcas_body(body: Any) -> tuple[dict, Optional[dict], int, Optional[str]]:
        if not isinstance(body, dict) or not isinstance(body.get("configuration"), dict):
            raise ApiError(422, "invalid_request",
                           "Body must contain a 'configuration' object.", "configuration")
        overrides = body.get("scenario_parameters")
        if overrides is not None and not isinstance(overrides, dict):
            raise ApiError(422, "invalid_request", "'scenario_parameters' must be an object.",
                           "scenario_parameters")
        seed = body.get("seed")
        if seed is None:
            seed = secrets.randbelow(2**31)
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            raise ApiError(422, "invalid_request", "'seed' must be a non-negative integer.", "seed")
        name = body.get("name")
        if name is not None and (not isinstance(name, str) or not name.strip() or len(name) > 80):
            raise ApiError(422, "invalid_request", "'name' must be 1-80 characters.", "name")
        return body["configuration"], overrides, seed, name

    @staticmethod
    def _is_finished(state: dict) -> bool:
        return state.get("status") in (COMPLETED, NOT_LAUNCHED)

    def start_mcas(self, user: Optional[User], body: dict[str, Any]) -> dict:
        configuration, overrides, seed, name = self._validate_mcas_body(body)
        state = self._interactive_call(
            interactive.start_run, configuration, seed, overrides, None
        )
        mission_id = state["mission_id"]
        now = now_iso()
        debrief = self._interactive_call(interactive.build_debrief, state) if self._is_finished(state) else None
        self.db.execute(
            "INSERT INTO simulation_mcas_runs "
            "(id, user_id, name, scenario_id, engine_version, seed, feasibility, status, state_json, "
            "debrief_json, outcome, score_total, created_at, updated_at, completed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (mission_id, user.id if user else None, name, state["scenario_id"], state["engine_version"],
             seed, state["feasibility"]["status"], state["status"], json.dumps(state),
             json.dumps(debrief) if debrief is not None else None,
             debrief.get("outcome") if debrief else state.get("outcome"),
             debrief.get("score", {}).get("total") if debrief else state.get("score_total"),
             now, now, now if debrief is not None else None),
        )
        return self._mcas_view(self._mcas_row(user, mission_id))

    def _mcas_row(self, user: Optional[User], mission_id: str) -> sqlite3.Row:
        row = self.db.query_one("SELECT * FROM simulation_mcas_runs WHERE id = ?", (mission_id,))
        if row is None:
            raise not_found("Mission run")
        owner = row["user_id"]
        if owner is not None and (user is None or user.id != owner):
            raise not_found("Mission run")
        return row

    @staticmethod
    def _mcas_view(row: sqlite3.Row) -> dict:
        return {
            "mission_id": row["id"],
            "name": row["name"],
            "scenario_id": row["scenario_id"],
            "seed": row["seed"],
            "feasibility": row["feasibility"],
            "status": row["status"],
            "state": json.loads(row["state_json"]),
            "debrief": json.loads(row["debrief_json"]) if row["debrief_json"] else None,
            "outcome": row["outcome"],
            "score_total": row["score_total"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "completed_at": row["completed_at"],
        }

    def get_mcas(self, user: Optional[User], mission_id: str) -> dict:
        return self._mcas_view(self._mcas_row(user, mission_id))

    def decide_mcas(self, user: Optional[User], mission_id: str, body: dict[str, Any]) -> dict:
        if not isinstance(body, dict) or not isinstance(body.get("anomaly_id"), str) or not isinstance(body.get("response_id"), str):
            raise ApiError(422, "invalid_request",
                           "Body must contain string 'anomaly_id' and 'response_id'.")
        row = self._mcas_row(user, mission_id)
        state = json.loads(row["state_json"])
        if state.get("status") != AWAITING_DECISION:
            raise ApiError(409, "no_pending_decision", "This mission is not waiting for a decision.")
        new_state = self._interactive_call(
            interactive.apply_decision, state, body["anomaly_id"], body["response_id"]
        )
        debrief = self._interactive_call(interactive.build_debrief, new_state) if self._is_finished(new_state) else None
        now = now_iso()
        changed = self.db.execute(
            "UPDATE simulation_mcas_runs SET status = ?, state_json = ?, debrief_json = ?, outcome = ?, "
            "score_total = ?, updated_at = ?, completed_at = ? WHERE id = ? AND state_json = ?",
            (new_state["status"], json.dumps(new_state), json.dumps(debrief) if debrief is not None else None,
             debrief.get("outcome") if debrief else new_state.get("outcome"),
             debrief.get("score", {}).get("total") if debrief else new_state.get("score_total"),
             now, now if debrief is not None else None, mission_id, row["state_json"]),
        )
        if not changed:
            raise ApiError(409, "no_pending_decision", "This decision was already submitted.")
        return self._mcas_view(self._mcas_row(user, mission_id))

    def mcas_debrief(self, user: Optional[User], mission_id: str) -> dict:
        row = self._mcas_row(user, mission_id)
        if not row["debrief_json"]:
            raise ApiError(409, "decision_pending", "The mission has not completed yet.")
        return json.loads(row["debrief_json"])

    def mcas_history(self, user: User, limit: int = 50, offset: int = 0) -> list[dict]:
        rows = self.db.query(
            "SELECT id, name, scenario_id, seed, feasibility, status, outcome, score_total, "
            "created_at, completed_at FROM simulation_mcas_runs WHERE user_id = ? "
            "ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?",
            (user.id, max(1, min(limit, 200)), max(0, offset)),
        )
        return [dict(r) | {"mission_id": r["id"]} for r in rows]

    # -- existing completed-run reads ---------------------------------------------

    def _row(self, user: Optional[User], run_id: str) -> sqlite3.Row:
        row = self.db.query_one("SELECT * FROM simulation_runs WHERE id = ?", (run_id,))
        if row is None:
            raise not_found("Run")
        owner = row["user_id"]
        if owner is not None and (user is None or user.id != owner):
            raise not_found("Run")
        return row

    @staticmethod
    def _view(row: sqlite3.Row) -> dict:
        return {
            "run_id": row["id"], "name": row["name"], "created_at": row["created_at"],
            "status": "completed", "result": json.loads(row["result_json"]),
        }

    def get(self, user: Optional[User], run_id: str) -> dict:
        return self._view(self._row(user, run_id))

    def history(self, user: User, limit: int = 50, offset: int = 0) -> list[SimulationRunSummary]:
        rows = self.db.query(
            "SELECT id, name, scenario_id, dataset_id, seed, feasibility, outcome, score_total, "
            "created_at FROM simulation_runs WHERE user_id = ? "
            "ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?",
            (user.id, max(1, min(limit, 200)), max(0, offset)),
        )
        return [
            SimulationRunSummary(
                run_id=r["id"], name=r["name"], scenario_id=r["scenario_id"], dataset_id=r["dataset_id"],
                seed=r["seed"], feasibility=r["feasibility"], outcome=r["outcome"],
                score_total=r["score_total"], created_at=r["created_at"],
            )
            for r in rows
        ]
