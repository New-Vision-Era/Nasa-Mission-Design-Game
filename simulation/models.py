"""Shared data models: the single source of field names and units.

Both the backend (API bodies) and the simulation engine import these.
Change this file by pull request reviewed by Person 2 and the backend pair.

Rules:
- Units live in the field name (``_kg``, ``_w``, ``_usd``, ``_gb_per_day``, ``_km``, ``_days``).
- Money is whole US dollars.
- ``resources``, ``telemetry`` and ``score`` are open name -> number maps so the
  simulation can add entries without a backend change.
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------
# Catalog (scientific data, loaded from data/*.json)
# --------------------------------------------------------------------------

Category = Literal[
    "platform",
    "instrument",
    "power",
    "communication",
    "propulsion",
    "adcs",
    "orbit",
    "launch_vehicle",
]

ProvenanceKind = Literal["published", "estimate", "gameplay"]


class Provenance(BaseModel):
    kind: ProvenanceKind
    source_id: Optional[str] = None
    note: Optional[str] = None


class Source(BaseModel):
    id: str
    title: str
    publisher: Optional[str] = None
    url: Optional[str] = None
    accessed: Optional[str] = None


class Component(BaseModel):
    """One selectable item. Unknown extra fields are kept and passed through."""

    model_config = ConfigDict(extra="allow")

    id: str
    category: Category
    name: str
    summary: str = ""
    mass_kg: Optional[float] = None
    power_w: Optional[float] = None  # power consumed
    power_output_w: Optional[float] = None  # power produced (power systems)
    cost_usd: Optional[int] = None
    data_rate_gb_per_day: Optional[float] = None  # data generated (instruments)
    downlink_gb_per_day: Optional[float] = None  # data sent home (communication)
    payload_capacity_kg: Optional[float] = None  # launch vehicles
    supported_orbit_ids: list[str] = Field(default_factory=list)  # empty = unrestricted (legacy/mock catalogs)
    altitude_km: Optional[float] = None  # orbits
    inclination_deg: Optional[float] = None  # orbits
    serves_objective_ids: list[str] = Field(default_factory=list)
    suitable_objective_ids: list[str] = Field(default_factory=list)  # orbits
    provenance: dict[str, Provenance] = Field(default_factory=dict)
    visual: dict[str, Any] = Field(default_factory=dict)  # hints for the 3D view


class Objective(BaseModel):
    id: str
    name: str
    description: str = ""
    target_data_gb: float


# Design slot path -> component category it must hold.
SLOT_CATEGORIES: dict[str, str] = {
    "spacecraft.platform_id": "platform",
    "spacecraft.instrument_ids": "instrument",
    "spacecraft.power_system_id": "power",
    "spacecraft.communication_system_id": "communication",
    "spacecraft.propulsion_system_id": "propulsion",
    "spacecraft.adcs_system_id": "adcs",
    "orbit_id": "orbit",
    "launch_vehicle_id": "launch_vehicle",
}


class Scenario(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    briefing: str
    objectives: list[Objective]
    budget_usd: int
    mission_duration_days: int
    operations_steps: int = 5
    required_slots: list[str] = Field(default_factory=lambda: list(SLOT_CATEGORIES))
    allowed_component_ids: Optional[list[str]] = None  # None = whole catalog
    scoring_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "science": 0.35,
            "reliability": 0.25,
            "efficiency": 0.20,
            "objectives": 0.20,
        }
    )
    requirements: list[str] = Field(default_factory=list)


class EventEffect(BaseModel):
    op: Literal["scale_step_science", "health_delta"]
    value: float
    chance: Optional[float] = None  # None = always applies


class EventOption(BaseModel):
    option_id: str
    label: str
    effect_summary: str
    effects: list[EventEffect] = Field(default_factory=list)


class Event(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    description: str
    base_probability: float
    # Optional link to the design: when resources[risk_resource] is below
    # risk_threshold, the probability rises (up to x(1 + risk_multiplier)).
    risk_resource: Optional[str] = None
    risk_threshold: float = 0.2
    risk_multiplier: float = 2.0
    options: list[EventOption]


class Catalog(BaseModel):
    catalog_version: str
    data_status: Literal["mock", "reviewed"]
    components: dict[str, Component]
    scenarios: dict[str, Scenario]
    events: list[Event] = Field(default_factory=list)
    sources: dict[str, Source] = Field(default_factory=dict)

    def by_category(self, category: str) -> list[Component]:
        return [c for c in self.components.values() if c.category == category]


# --------------------------------------------------------------------------
# Design (what the player builds)
# --------------------------------------------------------------------------


class Spacecraft(BaseModel):
    platform_id: Optional[str] = None
    instrument_ids: list[str] = Field(default_factory=list)
    power_system_id: Optional[str] = None
    communication_system_id: Optional[str] = None
    propulsion_system_id: Optional[str] = None
    adcs_system_id: Optional[str] = None


class Design(BaseModel):
    """Only scenario_id is required; everything else may be empty mid-design."""

    scenario_id: str
    spacecraft: Spacecraft = Field(default_factory=Spacecraft)
    orbit_id: Optional[str] = None
    launch_vehicle_id: Optional[str] = None

    def slot_values(self) -> dict[str, list[str]]:
        """Slot path -> list of selected component ids (empty if unset)."""
        sc = self.spacecraft

        def one(value: Optional[str]) -> list[str]:
            return [value] if value else []

        return {
            "spacecraft.platform_id": one(sc.platform_id),
            "spacecraft.instrument_ids": list(sc.instrument_ids),
            "spacecraft.power_system_id": one(sc.power_system_id),
            "spacecraft.communication_system_id": one(sc.communication_system_id),
            "spacecraft.propulsion_system_id": one(sc.propulsion_system_id),
            "spacecraft.adcs_system_id": one(sc.adcs_system_id),
            "orbit_id": one(self.orbit_id),
            "launch_vehicle_id": one(self.launch_vehicle_id),
        }


# --------------------------------------------------------------------------
# Evaluation (result of checking a design)
# --------------------------------------------------------------------------


class ConstraintResult(BaseModel):
    id: str
    severity: Literal["hard", "soft"]
    status: Literal["passed", "warning", "failed", "not_evaluated"]
    value: Optional[float] = None
    limit: Optional[float] = None
    unit: Optional[str] = None
    margin_fraction: Optional[float] = None
    related_step: str
    message: str


class Evaluation(BaseModel):
    catalog_version: str
    complete: bool
    launchable: bool
    missing: list[str]
    resources: dict[str, float]
    constraints: list[ConstraintResult]


# --------------------------------------------------------------------------
# Mission run
# --------------------------------------------------------------------------


class Progress(BaseModel):
    step: int
    total_steps: int
    elapsed_days: float


class PendingEventOption(BaseModel):
    option_id: str
    label: str
    effect_summary: str


class PendingEvent(BaseModel):
    event_id: str
    title: str
    description: str
    options: list[PendingEventOption]


class LogEntry(BaseModel):
    step: int
    message: str


class Decision(BaseModel):
    event_id: str
    option_id: str


class RunState(BaseModel):
    """Everything needed to continue a run. Stored as one JSON document."""

    status: Literal["awaiting_decision", "completed"]
    seed: int
    design: Design
    progress: Progress
    resources: dict[str, float] = Field(default_factory=dict)  # launch-time snapshot
    telemetry: dict[str, float] = Field(default_factory=dict)
    pending_event: Optional[PendingEvent] = None
    occurred_event_ids: list[str] = Field(default_factory=list)
    log: list[LogEntry] = Field(default_factory=list)


class ObjectiveResult(BaseModel):
    id: str
    achieved_fraction: float
    message: str


class Finding(BaseModel):
    kind: Literal["strength", "weakness"]
    related_step: Optional[str] = None
    message: str
    suggestion: Optional[str] = None


class Debrief(BaseModel):
    outcome: Literal["success", "partial_success", "failure"]
    score: dict[str, float]  # always contains "total"
    objectives: list[ObjectiveResult]
    findings: list[Finding]
