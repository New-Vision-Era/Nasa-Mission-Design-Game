"""Framework-free request handlers. A web framework only needs to call these.

Each handler returns (http_status, json_body). Errors use the backend's shape:
    {"error": {"code": ..., "message": ..., "field": ..., "details": [...]}}
Internal exceptions are never exposed to the client.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from .configuration import ConfigError
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


def handle_run_request(body: Any, catalog: Optional[Catalog] = None) -> tuple[int, dict]:
    """POST /simulation/run. Body: {"configuration": {...}, "scenario_parameters": {...}?, "seed": int?}."""
    if not isinstance(body, dict) or not isinstance(body.get("configuration"), dict):
        return _error(422, "invalid_request", "Body must be an object with a 'configuration' object.",
                      "configuration")
    seed = body.get("seed", 0)
    if isinstance(seed, bool) or not isinstance(seed, int):
        return _error(422, "invalid_request", "'seed' must be an integer.", "seed")
    try:
        result = run_simulation(body["configuration"], body.get("scenario_parameters"), seed, catalog)
        return 200, result
    except ConfigError as exc:
        return _config_error(exc)
    except CatalogError:
        log.exception("dataset problem")
        return _error(500, "internal_error", "The component dataset could not be loaded.")
    except Exception:  # noqa: BLE001 - never leak internals to the client
        log.exception("unexpected simulation error")
        return _error(500, "internal_error", "Unexpected error while running the simulation.")


def handle_recommend_request(body: Any, catalog: Optional[Catalog] = None) -> tuple[int, dict]:
    """POST /simulation/recommend. Same body as run; returns Pareto alternatives."""
    if not isinstance(body, dict) or not isinstance(body.get("configuration"), dict):
        return _error(422, "invalid_request", "Body must be an object with a 'configuration' object.",
                      "configuration")
    try:
        from .configuration import parse_config
        cfg = parse_config(body["configuration"])
        return 200, recommend(cfg, body.get("scenario_parameters"), catalog)
    except ConfigError as exc:
        return _config_error(exc)
    except Exception:  # noqa: BLE001
        log.exception("unexpected recommendation error")
        return _error(500, "internal_error", "Unexpected error while building recommendations.")


def handle_catalog_request(catalog: Optional[Catalog] = None) -> tuple[int, dict]:
    """GET /simulation/catalog. The v4 component catalog with all original fields."""
    try:
        return 200, (catalog or load_catalog()).to_public_dict()
    except Exception:  # noqa: BLE001
        log.exception("catalog could not be loaded")
        return _error(500, "internal_error", "The component dataset could not be loaded.")


# ---------------------------------------------------------------- MCAS: step-by-step missions
# Bodies carry either "state" (the run state returned earlier; lets the caller store runs itself)
# or "mission_id" (a run kept in this process's memory).

_DECISION_STATUS = {"not_found": 404, "no_pending_decision": 409, "wrong_anomaly": 409, "decision_pending": 409,
                    "response_unavailable": 409, "unknown_response": 422, "unknown_anomaly": 422,
                    "invalid_state": 422}


def _mcas_call(func, *args):
    from .mission.mcas.models import DecisionError
    try:
        return 200, func(*args)
    except ConfigError as exc:
        return _config_error(exc)
    except DecisionError as exc:
        return _error(_DECISION_STATUS.get(exc.code, 409), exc.code, exc.message)
    except CatalogError:
        log.exception("dataset problem")
        return _error(500, "internal_error", "The component dataset could not be loaded.")
    except Exception:  # noqa: BLE001
        log.exception("unexpected MCAS error")
        return _error(500, "internal_error", "Unexpected error while running the mission.")


def _mission_ref(body: Any):
    if isinstance(body, dict) and isinstance(body.get("state"), dict):
        return body["state"]
    if isinstance(body, dict) and isinstance(body.get("mission_id"), str):
        return body["mission_id"]
    return None


def handle_evaluate_request(body: Any, catalog: Optional[Catalog] = None) -> tuple[int, dict]:
    """POST /simulation/evaluate. Body: {"configuration", "scenario_parameters"?}. Adds the risk assessment."""
    from . import interactive
    if not isinstance(body, dict) or not isinstance(body.get("configuration"), dict):
        return _error(422, "invalid_request", "Body must be an object with a 'configuration' object.",
                      "configuration")
    return _mcas_call(interactive.evaluate_design, body["configuration"], body.get("scenario_parameters"), catalog)


def handle_start_request(body: Any, catalog: Optional[Catalog] = None) -> tuple[int, dict]:
    """POST /simulation/missions. Body: {"configuration", "scenario_parameters"?, "seed"?, "mission_id"?}."""
    from . import interactive
    if not isinstance(body, dict) or not isinstance(body.get("configuration"), dict):
        return _error(422, "invalid_request", "Body must be an object with a 'configuration' object.",
                      "configuration")
    seed = body.get("seed", 0)
    if isinstance(seed, bool) or not isinstance(seed, int):
        return _error(422, "invalid_request", "'seed' must be an integer.", "seed")
    return _mcas_call(interactive.start_run, body["configuration"], seed, body.get("scenario_parameters"),
                      body.get("mission_id"), catalog)


def handle_decision_request(body: Any, catalog: Optional[Catalog] = None) -> tuple[int, dict]:
    """POST /simulation/missions/decisions. Body: {"state" | "mission_id", "anomaly_id", "response_id"}."""
    from . import interactive
    ref = _mission_ref(body)
    if ref is None:
        return _error(422, "invalid_request", "Body needs 'state' (object) or 'mission_id' (string).", "state")
    for name in ("anomaly_id", "response_id"):
        if not isinstance(body.get(name), str):
            return _error(422, "invalid_request", f"'{name}' must be a string.", name)
    return _mcas_call(interactive.apply_decision, ref, body["anomaly_id"], body["response_id"], catalog)


def handle_debrief_request(body: Any, catalog: Optional[Catalog] = None) -> tuple[int, dict]:
    """POST /simulation/missions/debrief. Body: {"state" | "mission_id"}."""
    from . import interactive
    ref = _mission_ref(body)
    if ref is None:
        return _error(422, "invalid_request", "Body needs 'state' (object) or 'mission_id' (string).", "state")
    return _mcas_call(interactive.build_debrief, ref, catalog)
