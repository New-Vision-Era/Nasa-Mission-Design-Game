"""The backend without a server: the same services, called directly. Used by the hosted game.

GitHub Pages serves only static files, so the hosted game runs Python in the browser (Pyodide, in
a Web Worker: frontend/game/js/engine-worker.js). That worker calls `BrowserApi.handle()` with the
same method, path and JSON body the UI would send to FastAPI, and gets back the same status and
JSON. The rules, the data and the database code are the ones the server uses; only the HTTP layer
is replaced. The SQLite file lives in the browser (IndexedDB), so accounts and history are per
browser.

Routes covered: everything the game UI calls (see frontend/game/js/api.js). Anything else answers
404 like the server would for an unknown route.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from pydantic import BaseModel, ValidationError

from backend.app.config import Settings
from backend.app.container import build_container
from backend.app.errors import ApiError
from backend.app.services import surface_mission
from backend.app.schemas import Credentials


def _plain(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    return obj


def _error(status: int, code: str, message: str, field: Optional[str] = None) -> tuple[int, dict]:
    return status, {"error": {"code": code, "message": message, "field": field, "details": []}}


class BrowserApi:
    def __init__(self, database_path: str = ":memory:") -> None:
        settings = Settings.from_env()
        settings.database_path = database_path
        settings.frontend_dist = None
        self.c = build_container(settings)

    # ------------------------------------------------------------------ entry point
    def handle(self, method: str, path: str, body_json: Optional[str], token: Optional[str]) -> str:
        """Returns JSON: {"status": int, "body": ...}."""
        try:
            body = json.loads(body_json) if body_json else None
        except json.JSONDecodeError:
            status, out = _error(400, "invalid_json", "Body is not valid JSON.")
            return json.dumps({"status": status, "body": out})
        try:
            status, out = self._route(method.upper(), path.split("?")[0].rstrip("/"), body or {}, token)
        except ApiError as exc:
            status, out = exc.status, exc.body()
        except ValidationError as exc:
            first = exc.errors()[0]
            status, out = _error(422, "invalid_request", first.get("msg", "Invalid request."),
                                 ".".join(str(p) for p in first.get("loc", ())) or None)
        except surface_mission.SurfaceError as exc:
            unknown = str(exc).startswith("Unknown surface mission")
            status, out = _error(404 if unknown else 422, "not_found" if unknown else "invalid_request", str(exc))
        return json.dumps({"status": status, "body": _plain(out)})

    # ------------------------------------------------------------------ routing
    def _user(self, token: Optional[str]):
        return self.c.auth.user_for_token(token) if token else None

    def _need_user(self, token: Optional[str]):
        user = self._user(token)
        if user is None:
            raise ApiError(401, "unauthorized", "Login required.")
        return user

    def _route(self, m: str, p: str, body: dict, token: Optional[str]) -> tuple[int, Any]:
        V = self.c.simulation_v4
        if p.startswith("/api/v1"):
            p = p[len("/api/v1"):]
        if m == "GET" and p == "/health":
            return 200, {"status": "ok", "mode": "browser"}

        # engine v4 + MCAS (Earth observation)
        if m == "GET" and p == "/simulation/catalog":
            return 200, V.catalog()
        if m == "GET" and p == "/simulation/scenarios":
            return 200, V.scenarios()
        if m == "POST" and p == "/simulation/evaluate":
            return 200, V.evaluate_interactive(body)
        if m == "POST" and p == "/simulation/recommend":
            return 200, V.recommend(body)
        if m == "POST" and p == "/simulation/missions":
            return 201, V.start_mcas(self._user(token), body)
        if m == "GET" and p == "/simulation/missions":
            return 200, V.mcas_history(self._need_user(token))
        hit = re.fullmatch(r"/simulation/missions/([^/]+)(/decisions|/debrief)?", p)
        if hit:
            mission_id, tail = hit.groups()
            user = self._user(token)
            if m == "GET" and not tail:
                return 200, V.get_mcas(user, mission_id)
            if m == "GET" and tail == "/debrief":
                return 200, V.mcas_debrief(user, mission_id)
            if m == "POST" and tail == "/decisions":
                return 200, V.decide_mcas(user, mission_id, body)

        # surface missions (Mars, Moon)
        hit = re.fullmatch(r"/surface/([a-z]+)/(catalog|evaluate|fly|recommend)", p)
        if hit:
            mission, op = hit.groups()
            if op == "catalog" and m == "GET":
                return 200, surface_mission.catalog(mission)
            if m == "POST":
                sel = body.get("selection")
                if op == "evaluate":
                    return 200, surface_mission.evaluate(mission, sel)
                if op == "fly":
                    return 200, surface_mission.fly(mission, sel, body.get("decisions"))
                if op == "recommend":
                    return 200, surface_mission.recommend(mission, sel)

        # accounts
        if m == "POST" and p in ("/auth/register", "/auth/login"):
            cred = Credentials.model_validate(body)
            if p.endswith("register"):
                return 201, self.c.auth.register(cred.username, cred.password)
            return 200, self.c.auth.login(cred.username, cred.password)
        if m == "POST" and p == "/auth/logout":
            if token:
                self.c.auth.logout(token)
            return 204, None
        if m == "GET" and p == "/auth/me":
            return 200, self._need_user(token)

        return _error(404, "not_found", f"No route {m} {p} in the browser backend.")
