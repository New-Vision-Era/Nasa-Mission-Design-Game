"""Which responses the player may choose, and validation of the choice.

A response is only offered when the spacecraft has the capability or resource it needs.
"""
from __future__ import annotations

from typing import Any, Callable

from .models import AnomalyDefinition, DecisionError, Response


class _Blank(dict):
    def __missing__(self, key: str) -> str:
        return "?"


def fill(template: str, facts: dict[str, Any]) -> str:
    """Fill a catalogue text from the trigger facts. Unknown or missing values print as '?'."""
    try:
        return template.format_map(_Blank({k: v for k, v in facts.items() if v is not None}))
    except (ValueError, TypeError):
        return template


def _backup(facts: dict) -> tuple[bool, str]:
    if facts.get("backup_bits_per_day") is None:
        return False, "No other selected radio with a known downlink rate can reach a different ground station."
    return True, f"{facts['backup_radio_id']} is available."


def _backup_rf(facts: dict) -> tuple[bool, str]:
    if facts.get("backup_bits_per_day") is None:
        return False, "No radio-frequency radio with a known downlink rate is on board."
    return True, f"{facts['backup_radio_id']} is available."


def _power_saving(facts: dict) -> tuple[bool, str]:
    if facts.get("power_limited_duty") is None:
        return False, "Even with the instruments in standby, demand is above the reduced generation."
    return True, f"Instrument operating time can be held at {facts['power_limited_duty_pct']:.0f}%."


def _secondary(facts: dict) -> tuple[bool, str]:
    if not facts.get("secondary_ids"):
        return False, "Every selected instrument serves the mission objective."
    return True, f"Secondary instruments: {facts['secondary_list']}."


def _repeat(facts: dict) -> tuple[bool, str]:
    return bool(facts.get("repeat_power_ok")), facts.get("repeat_power_reason") or ""


REQUIREMENTS: dict[str, Callable[[dict], tuple[bool, str]]] = {
    "backup_radio_other_station": _backup,
    "backup_radio_rf": _backup_rf,
    "power_saving_possible": _power_saving,
    "secondary_instruments": _secondary,
    "power_for_repeat_observations": _repeat,
}


def describe(response: Response, facts: dict[str, Any]) -> dict[str, Any]:
    available, why = (True, "") if response.requires is None else REQUIREMENTS[response.requires](facts)
    return {"id": response.id, "label": response.label, "description": fill(response.description, facts),
            "trade_off": fill(response.trade_off, facts), "available": available,
            "unavailable_reason": None if available else why, "is_default": response.default,
            "value_kind": "gameplay_assumption"}


def available_responses(definition: AnomalyDefinition, facts: dict[str, Any]) -> list[dict[str, Any]]:
    """Every response of the anomaly, each marked available or not, with the reason."""
    return [describe(r, facts) for r in definition.responses]


def validate(definition: AnomalyDefinition, facts: dict[str, Any], response_id: Any) -> Response:
    """Return the chosen response or raise DecisionError (unknown_response, response_unavailable)."""
    response = definition.response(response_id) if isinstance(response_id, str) else None
    if response is None:
        valid = ", ".join(r.id for r in definition.responses)
        raise DecisionError("unknown_response",
                            f"'{response_id}' is not a response to '{definition.id}'. Valid: {valid}.")
    info = describe(response, facts)
    if not info["available"]:
        raise DecisionError("response_unavailable",
                            f"'{response_id}' is not available for this spacecraft: {info['unavailable_reason']}")
    return response
