"""Saved mission designs. Every mission belongs to one player."""

import sqlite3
import uuid

from simulation.models import Catalog, Design

from backend.app.errors import not_found
from backend.app.schemas import MissionCreate, MissionUpdate, MissionView, User
from backend.app.services.design_validation import validate_design
from backend.app.storage.db import Database, now_iso

_SELECT = """
SELECT m.*,
       (SELECT COUNT(*) FROM runs r WHERE r.mission_id = m.id) AS run_count,
       (SELECT MAX(r.score_total) FROM runs r WHERE r.mission_id = m.id) AS best_score
FROM missions m
"""


def _view(row: sqlite3.Row) -> MissionView:
    return MissionView(
        mission_id=row["id"],
        name=row["name"],
        scenario_id=row["scenario_id"],
        design=Design.model_validate_json(row["design_json"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        run_count=row["run_count"],
        best_score=row["best_score"],
    )


class MissionService:
    def __init__(self, db: Database, catalog: Catalog) -> None:
        self.db = db
        self.catalog = catalog

    def create(self, user: User, body: MissionCreate) -> MissionView:
        validate_design(body.design, self.catalog)
        mission_id, now = uuid.uuid4().hex, now_iso()
        self.db.execute(
            "INSERT INTO missions (id, user_id, scenario_id, name, design_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (mission_id, user.id, body.design.scenario_id, body.name.strip(),
             body.design.model_dump_json(), now, now),
        )
        return self.get(user, mission_id)

    def list(self, user: User) -> list[MissionView]:
        rows = self.db.query(_SELECT + "WHERE m.user_id = ? ORDER BY m.updated_at DESC, m.rowid DESC", (user.id,))
        return [_view(r) for r in rows]

    def get(self, user: User, mission_id: str) -> MissionView:
        # Someone else's mission answers 404, not 403, so ids cannot be probed.
        row = self.db.query_one(_SELECT + "WHERE m.id = ? AND m.user_id = ?", (mission_id, user.id))
        if row is None:
            raise not_found("Mission")
        return _view(row)

    def update(self, user: User, mission_id: str, body: MissionUpdate) -> MissionView:
        current = self.get(user, mission_id)
        design = body.design or current.design
        if body.design is not None:
            validate_design(design, self.catalog)
        name = body.name.strip() if body.name is not None else current.name
        self.db.execute(
            "UPDATE missions SET name = ?, scenario_id = ?, design_json = ?, updated_at = ? "
            "WHERE id = ? AND user_id = ?",
            (name, design.scenario_id, design.model_dump_json(), now_iso(), mission_id, user.id),
        )
        return self.get(user, mission_id)

    def delete(self, user: User, mission_id: str) -> None:
        """Deletes the saved design. Its past runs stay in the player's history."""
        changed = self.db.execute("DELETE FROM missions WHERE id = ? AND user_id = ?", (mission_id, user.id))
        if not changed:
            raise not_found("Mission")
