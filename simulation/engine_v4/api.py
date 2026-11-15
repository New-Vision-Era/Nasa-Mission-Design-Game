"""Framework-free request handlers. A web framework only needs to call these.

Each handler returns (http_status, json_body). Errors use the backend's shape:
    {"error": {"code": ..., "message": ..., "field": ..., "details": [...]}}
Internal exceptions are never exposed to the client.

`catalog_path` and `scenario_dir` let the backend point at its own data folder;
left as None they default to <repo>/data/equipment_v5.json and <repo>/data/scenarios_v4.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from .configuration import SCENARIO_DIR, ConfigError, parse_config
from .data_loader import Catalog, CatalogError, load_catalog
from .engine import run_simulation
from .optimizer.recommend import recommend

log = logging.getLogger("simulation.engine_v4")


def _error(status: int, code: str, message: str, field: Optional[str] = None, details=None):
    return status, {"error": {"code": code, "message": message, "field": field, "details": details or []}}


def _config_error(exc: ConfigError):
    first = exc.errors[0] if exc.errors else {"code": "invalid_request", "message": "Invalid request.", "field": None}
    status = 404 if first["code"] == "not_found" else 422
    return _error(status, first["code"], first["message"], first.get("field"), exc.errors)


def _catalog(catalog: Optional[Catalog], catalog_path) -> Catalog:
    return catalog or load_catalog(catalog_path)


def _bad_body(body: Any):
    if not isinstance(body, dict) or not isinstance(body.get("configuration"), dict):
        return _error(422, "invalid_request", "Body must be an object with a 'configuration' object.",
                      "configuration")
    return None


def handle_run_request(body: Any, catalog: Optional[Catalog] = None, catalog_path=None,
                       scenario_dir=None) -> tuple[int, dict]:
    """POST /simulation/run. Body: {"configuration": {...}, "scenario_parameters": {...}?, "seed": int?}."""
    bad = _bad_body(body)
    if bad:
        return bad
    seed = body.get("seed", 0)
    if seed is None:
        seed = 0
    if isinstance(seed, bool) or not isinstance(seed, int):
        return _error(422, "invalid_request", "'seed' must be an integer.", "seed")
    try:
        result = run_simulation(body["configuration"], body.get("scenario_parameters"), seed,
                                _catalog(catalog, catalog_path), scenario_dir)
        return 200, result
    except ConfigError as exc:
        return _config_error(exc)
    except CatalogError:
        log.exception("dataset problem")
        return _error(500, "internal_error", "The component dataset could not be loaded.")
    except Exception:  # noqa: BLE001 - never leak internals to the client
        log.exception("unexpected simulation error")
        return _error(500, "internal_error", "Unexpected error while running the simulation.")


def handle_recommend_request(body: Any, catalog: Optional[Catalog] = None, catalog_path=None,
                             scenario_dir=None) -> tuple[int, dict]:
    """POST /simulation/recommend. Same body as run; returns Pareto alternatives."""
    bad = _bad_body(body)
    if bad:
        return bad
    try:
        cfg = parse_config(body["configuration"])
        return 200, recommend(cfg, body.get("scenario_parameters"), _catalog(catalog, catalog_path),
                              scenario_dir=scenario_dir)
    except ConfigError as exc:
        return _config_error(exc)
    except Exception:  # noqa: BLE001
        log.exception("unexpected recommendation error")
        return _error(500, "internal_error", "Unexpected error while building recommendations.")


def handle_catalog_request(catalog: Optional[Catalog] = None, catalog_path=None) -> tuple[int, dict]:
    """GET /simulation/catalog. The v4 component catalog with all original fields."""
    try:
        return 200, _catalog(catalog, catalog_path).to_public_dict()
    except Exception:  # noqa: BLE001
        log.exception("catalog could not be loaded")
        return _error(500, "internal_error", "The component dataset could not be loaded.")


def handle_scenarios_request(scenario_dir=None) -> tuple[int, dict]:
    """GET /simulation/scenarios. Scenario briefings and their default (gameplay) parameters."""
    out = []
    for path in sorted(Path(scenario_dir or SCENARIO_DIR).glob("*.json")):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, json.JSONDecodeError):
            log.warning("unreadable scenario file skipped: %s", path.name)
            continue
        out.append({"id": raw.get("id", path.stem), "name": raw.get("name", path.stem),
                    "briefing": raw.get("briefing", ""), "value_kind": "gameplay_assumption",
                    "parameters": raw.get("parameters") or {}})
    return 200, {"scenarios": out}
