"""Mission runs: launch, answer events, read the result, list a player's history.

The server keeps no run in memory between requests: load state, call the
engine, save the new state.

Ownership:
- A run started while logged in belongs to that player and appears in their history.
- A run started as a guest has no owner; anyone holding its id can read it,
  and it appears in no history.
"""

import secrets
import sqlite3
import uuid
from typing import Optional

from simulation.models import Catalog, Debrief, Decision, Design, Evaluation, RunState

from backend.app.errors import ApiError, not_found
from backend.app.schemas import RunCreate, RunSummary, RunView, User
from backend.app.services.design_validation import get_scenario, validate_design
from backend.app.services.engine_adapter import EngineAdapter
from backend.app.storage.db import Database, now_iso


def _view(row: sqlite3.Row) -> RunView:
    state = RunState.model_validate_json(row["state_json"])
    return RunView(
        **state.model_dump(),
        run_id=row["id"],
        mission_id=row["mission_id"],
        scenario_id=row["scenario_id"],
        catalog_version=row["catalog_version"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
        debrief=Debrief.model_validate_json(row["debrief_json"]) if row["debrief_json"] else None,
    )


class RunService:
    def __init__(self, db: Database, catalog: Catalog, engine: EngineAdapter) -> None:
        self.db = db
        self.catalog = catalog
        self.engine = engine

    # -- evaluate (stateless) --------------------------------------------------

    def evaluate(self, design) -> Evaluation:
        scenario = validate_design(design, self.catalog)
        return self.engine.evaluate(design, scenario)

    # -- launch ----------------------------------------------------------------

    def start(self, user: Optional[User], body: RunCreate) -> RunView:
        scenario = validate_design(body.design, self.catalog)

        if body.mission_id is not None:
            if user is None:
                raise ApiError(401, "not_authenticated", "Log in to launch a saved mission.")
            owned = self.db.query_one(
                "SELECT id, scenario_id, design_json FROM missions WHERE id = ? AND user_id = ?",
                (body.mission_id, user.id),
            )
            if owned is None:
                raise not_found("Mission")
            saved_design = owned["design_json"]
            if (
                owned["scenario_id"] != body.design.scenario_id
                or Design.model_validate_json(saved_design) != body.design
            ):
                raise ApiError(
                    409, "mission_design_mismatch",
                    "The submitted design does not match the saved mission. Load the saved design before launching it.",
                    field="design",
                )

        evaluation = self.engine.evaluate(body.design, scenario)
        if not evaluation.launchable:
            raise ApiError(
                409,
                "not_launchable",
                "This design cannot launch: it is incomplete or fails a hard constraint.",
                extra={"evaluation": evaluation.model_dump()},
            )

        seed = body.seed if body.seed is not None else secrets.randbelow(2**31)
        state = self.engine.start_run(body.design, scenario, seed)
        run_id, now = uuid.uuid4().hex, now_iso()
        self.db.execute(
            "INSERT INTO runs (id, user_id, mission_id, scenario_id, catalog_version, seed, status, "
            "state_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, user.id if user else None, body.mission_id, scenario.id,
             self.catalog.catalog_version, seed, state.status, state.model_dump_json(), now),
        )
        self._finish_if_completed(run_id, state)
        return _view(self._row(user, run_id))

    # -- operations --------------------------------------------------------------

    def decide(self, user: Optional[User], run_id: str, decision: Decision) -> RunView:
        row = self._row(user, run_id)
        state = RunState.model_validate_json(row["state_json"])
        if state.status != "awaiting_decision" or state.pending_event is None:
            raise ApiError(409, "no_pending_event", "This run is not waiting for a decision.")
        if decision.event_id != state.pending_event.event_id:
            raise ApiError(
                409, "no_pending_event",
                "This decision is for a different event than the one pending.", field="event_id",
            )
        if decision.option_id not in {o.option_id for o in state.pending_event.options}:
            raise ApiError(422, "invalid_request", "Unknown option for this event.", field="option_id")

        scenario = get_scenario(self.catalog, row["scenario_id"])
        try:
            new_state = self.engine.apply_decision(state, decision, scenario)
        except ValueError as exc:
            raise ApiError(409, "no_pending_event", str(exc))

        # Only write if the run is still where we read it: blocks double submits.
        changed = self.db.execute(
            "UPDATE runs SET status = ?, state_json = ? WHERE id = ? AND state_json = ?",
            (new_state.status, new_state.model_dump_json(), run_id, row["state_json"]),
        )
        if not changed:
            raise ApiError(409, "no_pending_event", "This event was already answered.")
        self._finish_if_completed(run_id, new_state)
        return _view(self._row(user, run_id))

    def _finish_if_completed(self, run_id: str, state: RunState) -> None:
        if state.status != "completed":
            return
        scenario = get_scenario(self.catalog, state.design.scenario_id)
        debrief = self.engine.build_debrief(state, scenario)
        self.db.execute(
            "UPDATE runs SET debrief_json = ?, outcome = ?, score_total = ?, completed_at = ? WHERE id = ?",
            (debrief.model_dump_json(), debrief.outcome, debrief.score.get("total"), now_iso(), run_id),
        )

    # -- reading -----------------------------------------------------------------

    def _row(self, user: Optional[User], run_id: str) -> sqlite3.Row:
        row = self.db.query_one("SELECT * FROM runs WHERE id = ?", (run_id,))
        if row is None:
            raise not_found("Run")
        owner = row["user_id"]
        if owner is not None and (user is None or user.id != owner):
            raise not_found("Run")  # 404, not 403: do not reveal that it exists
        return row

    def get(self, user: Optional[User], run_id: str) -> RunView:
        return _view(self._row(user, run_id))

    def history(self, user: User, mission_id: Optional[str] = None, limit: int = 50, offset: int = 0) -> list[RunSummary]:
        """A player's past runs, newest first. Optionally only one mission's runs."""
        sql = (
            "SELECT r.id, r.mission_id, m.name AS mission_name, r.scenario_id, r.status, r.outcome, "
            "r.score_total, r.created_at, r.completed_at "
            "FROM runs r LEFT JOIN missions m ON m.id = r.mission_id WHERE r.user_id = ?"
        )
        params: list = [user.id]
        if mission_id is not None:
            sql += " AND r.mission_id = ?"
            params.append(mission_id)
        sql += " ORDER BY r.created_at DESC, r.rowid DESC LIMIT ? OFFSET ?"
        params += [max(1, min(limit, 200)), max(0, offset)]
        return [
            RunSummary(
                run_id=r["id"], mission_id=r["mission_id"], mission_name=r["mission_name"],
                scenario_id=r["scenario_id"], status=r["status"], outcome=r["outcome"],
                score_total=r["score_total"], created_at=r["created_at"], completed_at=r["completed_at"],
            )
            for r in self.db.query(sql, tuple(params))
        ]
