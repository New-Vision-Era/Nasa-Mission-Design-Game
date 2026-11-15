"""MCAS data structures: statuses, anomaly definitions, period modifiers, run context.

MCAS (Mission Consequence & Anomaly System) is a simplified educational game model,
not a spacecraft reliability simulator. It computes nothing about mass, power,
communications, propulsion or pointing itself: it reads the engineering evaluation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from ...configuration import MissionConfig, ScenarioParams, Selection
from ...results import GAMEPLAY, ConstraintResult

# vulnerability levels (not probabilities). UNKNOWN keeps a missing value unknown.
LOW, MEDIUM, HIGH, UNKNOWN = "LOW", "MEDIUM", "HIGH", "UNKNOWN"

# anomaly lifecycle
NOT_ELIGIBLE = "NOT_ELIGIBLE"
ELIGIBLE = "ELIGIBLE"
TRIGGERED = "TRIGGERED"
DETECTED = "DETECTED"
AWAITING_PLAYER_DECISION = "AWAITING_PLAYER_DECISION"
RESOLVED = "RESOLVED"
MISSION_STATE_UPDATED = "MISSION_STATE_UPDATED"
IGNORED = "IGNORED"          # no player action was required or available
RECOVERED = "RECOVERED"      # the system returned to normal operation
PERSISTING = "PERSISTING"    # stays active and affects later periods
UNRESOLVED = "UNRESOLVED"    # reserved: response deadlines are not modelled in the MVP

# run status
ACTIVE = "ACTIVE"
AWAITING_DECISION = "AWAITING_DECISION"
COMPLETED = "COMPLETED"
NOT_LAUNCHED = "NOT_LAUNCHED"

ENGINEERING = "engineering"
EXTERNAL = "external"

DETERMINISTIC = "deterministic"
SEEDED = "seeded_probability"


class DecisionError(Exception):
    """A player decision that cannot be applied. `code` is stable for the API layer."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Response:
    id: str
    label: str
    description: str
    trade_off: str
    effects: dict[str, Any]              # declarative; interpreted by anomaly_resolver
    outcome: str                         # template filled from the trigger facts
    requires: Optional[str] = None       # named capability check in decision_manager
    default: bool = False                # applied when no player decision is asked for
    standing: bool = False               # effect lasts to the end of the mission
    assumptions: list[str] = field(default_factory=list)


@dataclass
class AnomalyDefinition:
    id: str
    name: str
    description: str
    mission_types: list[str]
    phases: list[str]
    category: str                        # ENGINEERING or EXTERNAL
    affected_system: str
    severity: str
    cause: str
    symptom: str
    trigger: dict[str, Any]              # {"type", "check", "source_event"?, "probability_parameter"?}
    responses: list[Response]
    recovery: str
    related_step: Optional[str] = None
    recurring: bool = False
    value_kind: str = GAMEPLAY
    source_urls: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    def response(self, response_id: str) -> Optional[Response]:
        return next((r for r in self.responses if r.id == response_id), None)

    def default_response(self) -> Response:
        return next(r for r in self.responses if r.default)

    def to_public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TriggerResult:
    eligible: bool
    triggered: bool
    reason: str
    facts: dict[str, Any] = field(default_factory=dict)
    design_link: Optional[str] = None    # which design choice created the vulnerability


@dataclass
class Modifiers:
    """What one resolved anomaly does to one period (or, if standing, to every later period)."""

    science_factor: float = 1.0
    data_factor: float = 1.0
    downlink_factor: float = 1.0
    primary_downlink_lost: bool = False
    backup_capacity_bits_per_day: Optional[float] = None
    instrument_fraction: dict[str, float] = field(default_factory=dict)


@dataclass
class RunContext:
    """Everything a run needs, derived once from the configuration. Never stored: rebuilt on demand."""

    cfg: MissionConfig
    scenario_id: str
    mission_type: str
    sel: Selection
    params: ScenarioParams
    evaluation: dict[str, Any]
    performance: dict[str, Any]
    seed: int

    @property
    def periods(self) -> int:
        return self.params.science_periods

    @property
    def days_per_period(self) -> float:
        return self.params.mission_duration_days / self.params.science_periods

    @property
    def relevant_ids(self) -> list[str]:
        return list(self.performance["relevant_instrument_ids"])

    @property
    def generated_day(self) -> Optional[float]:
        return self.evaluation["data"]["generated_bits_per_day"]

    @property
    def capacity_day(self) -> Optional[float]:
        return self.evaluation["downlink"]["bits_per_day"]

    @property
    def radio(self) -> Optional[dict]:
        rid = self.evaluation["downlink"]["radio_id"]
        return next((r for r in self.sel.comms if r["id"] == rid), None)

    @property
    def generation_w(self) -> Optional[float]:
        return (self.evaluation["power"].get("generation") or {}).get("value_w")

    @property
    def demand_w(self) -> float:
        return self.evaluation["power"]["demand"]["known_avg_w"]

    def constraint(self, constraint_id: str) -> Optional[ConstraintResult]:
        return next((r for r in self.evaluation["constraints"] if r.id == constraint_id), None)
