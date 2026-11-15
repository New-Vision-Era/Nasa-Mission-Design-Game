"""Mission configuration, scenario parameters and selection rules.

A configuration holds component IDs only, never copied specifications.
Every ScenarioParams field is a GAMEPLAY ASSUMPTION or a scenario requirement,
not a real-world value. They are echoed in the result under "assumptions".
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .data_loader import Catalog

SCENARIO_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios_v4"

MODE_A = "platform_payload_budget"
MODE_B = "player_built_power_system"


class ConfigError(Exception):
    """Invalid request or selection. `errors` is a list of {code, field, message}."""

    def __init__(self, errors: list[dict[str, Any]]):
        super().__init__(errors[0]["message"] if errors else "invalid configuration")
        self.errors = errors


class PowerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["platform_payload_budget", "player_built_power_system"] = MODE_A
    solar_array_ids: list[str] = Field(default_factory=list)  # repeats allowed = quantity
    battery_ids: list[str] = Field(default_factory=list)       # repeats allowed = quantity
    eps_id: Optional[str] = None


class MissionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str
    platform_id: str
    instrument_ids: list[str] = Field(default_factory=list)
    power: PowerConfig = Field(default_factory=PowerConfig)
    communication_system_ids: list[str] = Field(default_factory=list)
    adcs_system_id: str
    propulsion_system_id: Optional[str] = None
    orbit_id: str
    launch_vehicle_id: str


class ScienceRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")
    required_instrument_families_any: list[str] = Field(default_factory=list)
    required_spectral_keywords_any: list[str] = Field(default_factory=list)
    max_gsd_m: Optional[float] = None
    min_swath_km: Optional[float] = None
    prefer_sun_synchronous: Optional[bool] = None


class EventSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    comm_outage_probability: float = Field(0.10, ge=0, le=1)
    reduced_solar_probability: float = Field(0.10, ge=0, le=1)
    reduced_solar_factor: float = Field(0.7, ge=0, le=1)
    optical_cloud_probability: float = Field(0.30, ge=0, le=1)
    instrument_unavailable_probability: float = Field(0.05, ge=0, le=1)


class ScoringWeights(BaseModel):
    model_config = ConfigDict(extra="forbid")
    science: float = Field(35, ge=0)
    objectives: float = Field(25, ge=0)
    reliability: float = Field(20, ge=0)
    efficiency: float = Field(20, ge=0)


class ScenarioParams(BaseModel):
    """Scenario requirements and gameplay assumptions. None of these are published specs."""

    model_config = ConfigDict(extra="forbid")

    mission_duration_days: float = Field(365, gt=0)
    budget_usd: Optional[float] = Field(None, ge=0)

    # ground segment
    ground_station_types: list[str] = Field(default_factory=lambda: ["uhf", "s_band", "x_band"])
    passes_per_day: float = Field(4, ge=0)
    average_usable_pass_duration_s: Optional[float] = Field(None, ge=0)
    usable_pass_fraction: float = Field(0.6, ge=0, le=1)  # of the orbit's max overhead pass
    link_availability: float = Field(0.9, ge=0, le=1)
    optical_cloud_availability: float = Field(0.5, ge=0, le=1)
    commandable_required: bool = True

    # operations
    instrument_duty_cycle: float = Field(0.2, ge=0, le=1)
    instrument_duty_cycle_overrides: dict[str, float] = Field(default_factory=dict)
    propulsion_firing_duty_cycle: float = Field(0.0, ge=0, le=1)
    data_generation_kbps: dict[str, float] = Field(default_factory=dict)  # per instrument id, while operating
    science_periods: int = Field(12, ge=1, le=120)

    # structure
    count_subsystems_in_payload_mass: bool = True
    volume_scope: Literal["instruments", "all"] = "instruments"
    packing_factor: float = Field(0.6, gt=0, le=1)
    bus_mass_kg_assumption: Optional[float] = Field(None, ge=0)
    rideshare_mass_cap_kg_assumption: Optional[float] = Field(None, ge=0)

    # player-built power (Mode B)
    solar_k_factor: float = Field(0.65, gt=0, le=1)
    battery_depth_of_discharge: float = Field(0.3, gt=0, le=1)

    # pointing / propulsion
    hard_pointing_requirement_deg: Optional[float] = Field(None, gt=0)
    pointing_swath_warning_fraction: float = Field(0.25, gt=0)
    min_delta_v_m_s: Optional[float] = Field(None, ge=0)

    # science, outcome, scoring
    science: ScienceRequirements = Field(default_factory=ScienceRequirements)
    success_threshold: float = Field(0.8, ge=0, le=1)
    partial_threshold: float = Field(0.4, ge=0, le=1)
    margin_target_fraction: float = Field(0.2, gt=0, le=1)
    deployable_array_penalty: float = Field(0.05, ge=0, le=1)
    scoring_weights: ScoringWeights = Field(default_factory=ScoringWeights)
    events: EventSettings = Field(default_factory=EventSettings)


@dataclass
class Scenario:
    id: str
    name: str
    briefing: str
    params: ScenarioParams


def _format_validation_error(exc: ValidationError, prefix: str = "") -> list[dict]:
    errors = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"])
        errors.append({
            "code": "invalid_request",
            "field": f"{prefix}{loc}" if loc else prefix.rstrip("."),
            "message": err["msg"],
        })
    return errors


def parse_config(data: Any) -> MissionConfig:
    if isinstance(data, MissionConfig):
        return data
    try:
        return MissionConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(exc)) from None


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_scenario(scenario_id: str, overrides: Optional[dict] = None,
                  scenario_dir: Optional[Path] = None) -> Scenario:
    """Read data/scenarios_v4/<id>.json and apply optional parameter overrides."""
    if not isinstance(scenario_id, str) or not scenario_id.replace("_", "").isalnum():
        raise ConfigError([{"code": "not_found", "field": "scenario_id",
                            "message": f"Unknown scenario '{scenario_id}'."}])
    path = (scenario_dir or SCENARIO_DIR) / f"{scenario_id}.json"
    if not path.is_file():
        raise ConfigError([{"code": "not_found", "field": "scenario_id",
                            "message": f"Unknown scenario '{scenario_id}'."}])
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    if overrides is not None and not isinstance(overrides, dict):
        raise ConfigError([{"code": "invalid_request", "field": "scenario_parameters",
                            "message": "scenario_parameters must be an object."}])
    merged = _merge(raw.get("parameters") or {}, overrides or {})
    try:
        params = ScenarioParams.model_validate(merged)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(exc, "scenario_parameters.")) from None
    return Scenario(id=raw.get("id", scenario_id), name=raw.get("name", scenario_id),
                    briefing=raw.get("briefing", ""), params=params)


@dataclass
class Selection:
    """Resolved component records for one configuration."""

    platform: dict
    instruments: list[dict]
    adcs: dict
    comms: list[dict]
    propulsion: Optional[dict]
    solar_arrays: list[dict]
    batteries: list[dict]
    eps: Optional[dict]
    orbit: dict
    launcher: dict
    power_mode: str

    def carried(self, include_subsystems: bool = True) -> list[tuple[str, dict]]:
        """Components the platform carries as payload: (category, record)."""
        out: list[tuple[str, dict]] = [("instruments", i) for i in self.instruments]
        if not include_subsystems:
            return out
        out.append(("adcs_systems", self.adcs))
        out += [("communication_systems", c) for c in self.comms]
        if self.propulsion:
            out.append(("propulsion_systems", self.propulsion))
        out += [("power_systems", p) for p in self.solar_arrays + self.batteries]
        if self.eps:
            out.append(("power_systems", self.eps))
        return out

    def all_records(self) -> list[dict]:
        return [self.platform, self.orbit, self.launcher] + [r for _, r in self.carried()]


def resolve_selection(cfg: MissionConfig, catalog: Catalog) -> Selection:
    """Turn IDs into records. Unknown IDs, wrong slots and duplicates are rejected."""
    errors: list[dict] = []

    def one(category: str, cid: Optional[str], field: str, family: Optional[str] = None):
        if cid is None:
            return None
        rec = catalog.get(category, cid)
        if rec is None:
            found = catalog.find(cid)
            hint = f" It is a '{found[0]}' component, not valid in this slot." if found else ""
            errors.append({"code": "unknown_component", "field": field,
                           "message": f"No {category} component with id '{cid}'.{hint}"})
            return None
        if family and rec.get("family") != family:
            errors.append({"code": "unknown_component", "field": field,
                           "message": f"'{cid}' is a {rec.get('family')} component; this slot needs a {family}."})
            return None
        return rec

    def many(category: str, ids: list[str], field: str, family: Optional[str] = None,
             unique: bool = True) -> list[dict]:
        out = []
        seen: set[str] = set()
        for pos, cid in enumerate(ids):
            if unique and cid in seen:
                errors.append({"code": "invalid_request", "field": f"{field}[{pos}]",
                               "message": f"'{cid}' is selected more than once."})
                continue
            seen.add(cid)
            rec = one(category, cid, f"{field}[{pos}]", family)
            if rec is not None:
                out.append(rec)
        return out

    platform = one("platforms", cfg.platform_id, "platform_id")
    instruments = many("instruments", cfg.instrument_ids, "instrument_ids")
    adcs = one("adcs_systems", cfg.adcs_system_id, "adcs_system_id")
    comms = many("communication_systems", cfg.communication_system_ids, "communication_system_ids")
    propulsion = one("propulsion_systems", cfg.propulsion_system_id, "propulsion_system_id")
    orbit = one("orbits", cfg.orbit_id, "orbit_id")
    launcher = one("launch_vehicles", cfg.launch_vehicle_id, "launch_vehicle_id")
    arrays = many("power_systems", cfg.power.solar_array_ids, "power.solar_array_ids", "solar_array", unique=False)
    batteries = many("power_systems", cfg.power.battery_ids, "power.battery_ids", "battery", unique=False)
    eps = one("power_systems", cfg.power.eps_id, "power.eps_id", "power_conditioning")

    if cfg.power.mode == MODE_B and not cfg.power.solar_array_ids:
        errors.append({"code": "invalid_request", "field": "power.solar_array_ids",
                       "message": "Power mode 'player_built_power_system' needs at least one solar array."})
    if errors:
        raise ConfigError(errors)
    return Selection(platform=platform, instruments=instruments, adcs=adcs, comms=comms,
                     propulsion=propulsion, solar_arrays=arrays, batteries=batteries, eps=eps,
                     orbit=orbit, launcher=launcher, power_mode=cfg.power.mode)
