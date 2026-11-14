"""Settings, read from environment variables with working defaults."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    data_dir: Path = REPO_ROOT / "data"
    database_path: str = "space_mission.db"  # ":memory:" for tests
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173"])
    session_ttl_hours: int = 24 * 7
    frontend_dist: Optional[Path] = None  # built frontend to serve at "/"

    @classmethod
    def from_env(cls) -> "Settings":
        s = cls()
        if os.getenv("DATA_DIR"):
            s.data_dir = Path(os.environ["DATA_DIR"])
        if os.getenv("DATABASE_PATH"):
            s.database_path = os.environ["DATABASE_PATH"]
        if os.getenv("CORS_ORIGINS"):
            s.cors_origins = [o.strip() for o in os.environ["CORS_ORIGINS"].split(",") if o.strip()]
        if os.getenv("SESSION_TTL_HOURS"):
            s.session_ttl_hours = int(os.environ["SESSION_TTL_HOURS"])
        if os.getenv("FRONTEND_DIST"):
            s.frontend_dist = Path(os.environ["FRONTEND_DIST"])
        return s
