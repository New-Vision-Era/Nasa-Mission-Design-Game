"""Data-driven anomaly catalogue.

Each definition keeps cause, trigger, symptom, responses, recovery and assumptions together.
Triggers, capability checks and effects are NAMES resolved by trigger_engine, decision_manager
and anomaly_resolver. No string is ever evaluated as code.

Nothing here is a published reliability or environmental figure. Event probabilities stay in the
scenario file (`parameters.events`); every rule and factor below is a GAMEPLAY ASSUMPTION.
"""
from __future__ import annotations

from typing import Any, Optional

from .models import DETERMINISTIC, ENGINEERING, EXTERNAL, SEEDED, AnomalyDefinition, Response

EARTH_OBSERVATION = "earth_observation"
MOON_LANDING = "moon_landing"
MARS_LANDING = "mars_landing"

# gameplay parameters used by the responses below (value_kind: gameplay_assumption)
GAMEPLAY_PARAMETERS = {
    "recovery_period_fraction": {
        "value": 0.5,
        "value_kind": "gameplay_assumption",
        "meaning": "Share of an operation period an instrument works after a recovery procedure, and share "
                   "of that period's ground contact left for downlink while the procedure runs.",
    },
}

MISSION_TYPES: dict[str, dict[str, Any]] = {
    EARTH_OBSERVATION: {
        "implemented": True,
        "kind": "orbital",
        "phases": ["launch", "deployment", "commissioning", "science_operations", "data_downlink",
                   "mission_completion"],
        "specific_anomaly_ids": ["pointing_instability", "optical_downlink_cloud"],
    },
    MOON_LANDING: {
        "implemented": False,
        "kind": "landing_no_atmosphere",
        "phases": ["launch", "translunar_cruise", "lunar_orbit_or_approach", "powered_descent", "landing",
                   "surface_operations"],
        "planned_anomalies": ["Descent propulsion underperformance", "Landing navigation uncertainty",
                              "Excessive landing velocity", "Landing instability", "Surface power shortage",
                              "Dust-related equipment degradation"],
        "not_implemented_reason": "Needs a lunar mission model (descent, landing, surface) and validated lander "
                                  "equipment data. The Earth-observation catalogue is not sufficient.",
    },
    MARS_LANDING: {
        "implemented": False,
        "kind": "landing_with_atmosphere",
        "phases": ["launch", "interplanetary_cruise", "mars_approach", "atmospheric_entry", "descent",
                   "landing", "surface_operations"],
        "planned_anomalies": ["Atmospheric entry heating problem", "Heat-shield or thermal-protection issue",
                              "Parachute or descent-system problem", "Landing navigation uncertainty",
                              "Excessive landing velocity", "Surface power shortage", "Dust-related degradation"],
        "not_implemented_reason": "Needs an entry, descent and landing model with an atmosphere and validated "
                                  "equipment data. It must not reuse lunar-landing assumptions.",
    },
}

ALL_MISSIONS = [EARTH_OBSERVATION, MOON_LANDING, MARS_LANDING]
SCIENCE = ["science_operations"]

_DEFINITIONS: list[dict[str, Any]] = [
    # ---------------------------------------------------------------- shared
    {
        "id": "communication_outage",
        "name": "Communication outage",
        "description": "The ground-station network used by the main downlink radio is unavailable for one "
                       "operation period.",
        "mission_types": ALL_MISSIONS, "phases": SCIENCE,
        "category": EXTERNAL, "affected_system": "communications", "severity": "medium",
        "cause": "Ground contact on the main downlink band is unavailable this period (external event).",
        "symptom": "No carrier lock during the planned passes; nothing is downlinked on the main radio.",
        "trigger": {"type": SEEDED, "check": "communication_outage", "source_event": "comm_outage",
                    "probability_parameter": "events.comm_outage_probability"},
        "related_step": "communications",
        "recovery": "Contact returns at the start of the next operation period.",
        "recurring": True,
        "assumptions": ["The outage affects one ground-station type, the one the main downlink radio uses.",
                        "Onboard storage is not capped, so stored data is never overwritten."],
        "responses": [
            {"id": "store_and_wait", "label": "Store data and wait", "default": True,
             "description": "Keep observing and hold the data on board until contact returns.",
             "trade_off": "Science continues, but this period's data joins the backlog.",
             "effects": {"primary_downlink": "lost"},
             "outcome": "No data was downlinked this period; it waits on board for the next contact."},
            {"id": "switch_to_backup_radio", "label": "Downlink on the backup radio",
             "requires": "backup_radio_other_station",
             "description": "Use a second radio that talks to a different ground-station type.",
             "trade_off": "Keeps data flowing, at the backup radio's own (usually lower) rate.",
             "effects": {"primary_downlink": "lost", "backup_downlink": "backup"},
             "outcome": "Downlink moved to {backup_radio_id} at {backup_gb_per_day:.2f} GB per day for this "
                        "period (the main radio returns {primary_gb_per_day:.2f} GB per day)."},
        ],
    },
    {
        "id": "power_shortage",
        "name": "Power shortage",
        "description": "Solar generation drops and can no longer cover the spacecraft's average demand.",
        "mission_types": ALL_MISSIONS, "phases": SCIENCE,
        "category": EXTERNAL, "affected_system": "power", "severity": "high",
        "cause": "Reduced solar generation (external event) on a power system with too little margin to "
                 "absorb it.",
        "symptom": "Bus power falls below the demand of the systems that are switched on.",
        "trigger": {"type": SEEDED, "check": "power_shortage", "source_event": "reduced_solar",
                    "probability_parameter": "events.reduced_solar_probability"},
        "related_step": "power",
        "recovery": "Generation returns to normal at the start of the next operation period.",
        "recurring": True,
        "assumptions": ["Only modelled for a player-built power system; the platform's own generation is not "
                        "in the dataset.",
                        "Generation is multiplied by events.reduced_solar_factor for the period.",
                        "A demand above supply before any event is a hard constraint failure and blocks "
                        "launch; it is never turned into this anomaly."],
        "responses": [
            {"id": "suspend_instruments", "label": "Suspend the instruments", "default": True,
             "description": "Switch the instruments off until generation recovers.",
             "trade_off": "The spacecraft stays safe, but this period produces no science.",
             "effects": {"science": 0.0, "data": 0.0},
             "outcome": "Generation fell to {reduced_w:.1f} W against {demand_w:.1f} W of demand. Instruments "
                        "were off for the period: no observations, no new data."},
            {"id": "activate_power_saving_mode", "label": "Activate power-saving mode",
             "requires": "power_saving_possible",
             "description": "Cut instrument operating time until demand fits the reduced generation.",
             "trade_off": "Keeps part of the science, in proportion to the power that is left.",
             "effects": {"science": "power_limited_duty", "data": "power_limited_duty"},
             "outcome": "Instrument operating time was cut to {power_limited_duty_pct:.0f}% so that demand fits "
                        "the {reduced_w:.1f} W available. Observations and data fell in the same proportion."},
            {"id": "continue_operations", "label": "Continue normal operations",
             "description": "Leave everything on and accept the shortfall.",
             "trade_off": "No science is given up on purpose, but demand stays above supply.",
             "effects": {"science": 0.0, "data": 0.0, "primary_downlink": "lost"},
             "outcome": "Demand stayed {deficit_w:.1f} W above generation. The spacecraft dropped into safe "
                        "mode: no observations and no downlink this period.",
             "assumptions": ["A sustained power deficit puts the spacecraft in safe mode for the period "
                             "(gameplay rule; battery state of charge is not tracked)."]},
        ],
    },
    {
        "id": "data_backlog",
        "name": "Data backlog",
        "description": "The instruments produce more data each day than the downlink can return.",
        "mission_types": ALL_MISSIONS, "phases": SCIENCE,
        "category": ENGINEERING, "affected_system": "communications", "severity": "medium",
        "cause": "Daily data generation exceeds daily downlink capacity (engineering evaluation, "
                 "constraint data_balance).",
        "symptom": "Stored data grows every period and never clears.",
        "trigger": {"type": DETERMINISTIC, "check": "data_backlog", "source_constraint": "data_balance"},
        "related_step": "communications",
        "recovery": "Does not recover by itself: the imbalance comes from the design.",
        "assumptions": ["Evaluated only when instrument data rates and downlink capacity are both known.",
                        "Onboard storage is not capped; the cost of a backlog is data that never reaches Earth.",
                        "Data is shared between instruments by count, as in the v4 mission model."],
        "responses": [
            {"id": "continue_full_observation", "label": "Keep observing at full rate", "default": True,
             "standing": True,
             "description": "Observe as planned and downlink what fits.",
             "trade_off": "Full observation time, but about {lost_pct:.0f}% of the data stays on board.",
             "effects": {},
             "outcome": "Observations continued at full rate; only about {downlink_pct:.0f}% of the data "
                        "generated each day can be returned."},
            {"id": "match_observations_to_downlink", "label": "Observe only what can be downlinked",
             "standing": True,
             "description": "Reduce instrument operating time to the level the downlink can return.",
             "trade_off": "Everything observed reaches Earth, but observation time drops to "
                          "{downlink_pct:.0f}%.",
             "effects": {"science": "downlink_fraction", "data": "downlink_fraction"},
             "outcome": "Operating time was cut to {downlink_pct:.0f}% for the rest of the mission so that "
                        "all data generated can be returned."},
            {"id": "suspend_secondary_instruments", "label": "Switch off secondary instruments",
             "standing": True, "requires": "secondary_instruments",
             "description": "Stop the instruments that do not serve the mission objective.",
             "trade_off": "Frees downlink for the objective's data; the secondary instruments return nothing.",
             "effects": {"instruments_off": "secondary"},
             "outcome": "{secondary_list} switched off for the rest of the mission, leaving the downlink to "
                        "the instruments that serve the objective."},
        ],
    },
    {
        "id": "instrument_unavailable",
        "name": "Instrument unavailable",
        "description": "One instrument stops responding for an operation period.",
        "mission_types": ALL_MISSIONS, "phases": SCIENCE,
        "category": EXTERNAL, "affected_system": "payload", "severity": "medium",
        "cause": "An instrument becomes unavailable during operations (external event).",
        "symptom": "The instrument returns no telemetry and takes no observations.",
        "trigger": {"type": SEEDED, "check": "instrument_unavailable", "source_event": "instrument_unavailable",
                    "probability_parameter": "events.instrument_unavailable_probability"},
        "related_step": "instruments",
        "recovery": "The instrument is available again at the start of the next operation period.",
        "recurring": True,
        "assumptions": ["Which instrument is affected is drawn with the run seed.",
                        "recovery_period_fraction is a gameplay parameter, not a measured recovery time."],
        "responses": [
            {"id": "wait_for_recovery", "label": "Wait for the next period", "default": True,
             "description": "Leave the instrument off and carry on with the rest of the spacecraft.",
             "trade_off": "Downlink is untouched; the instrument contributes nothing this period.",
             "effects": {"instrument": 0.0},
             "outcome": "{instrument_id} stayed off this period. {redundancy_note}"},
            {"id": "run_recovery_procedure", "label": "Run a recovery procedure",
             "description": "Use this period's ground contacts to diagnose and restart the instrument.",
             "trade_off": "The instrument works for part of the period, but the contacts used for recovery "
                          "are not available for downlink.",
             "effects": {"instrument": "recovery_period_fraction", "downlink_factor": "recovery_period_fraction"},
             "outcome": "{instrument_id} was recovered and worked for {recovery_pct:.0f}% of the period. "
                        "Ground contact spent on the procedure left {recovery_pct:.0f}% of the period's "
                        "downlink."},
        ],
    },
    # ------------------------------------------------- Earth observation
    {
        "id": "pointing_instability",
        "name": "Pointing instability",
        "description": "Pointing error is a large share of the instrument swath, so part of the planned "
                       "targets fall outside the image.",
        "mission_types": [EARTH_OBSERVATION], "phases": SCIENCE,
        "category": ENGINEERING, "affected_system": "adcs", "severity": "medium",
        "cause": "ADCS pointing error on the ground is large against the instrument swath (engineering "
                 "evaluation, constraint pointing_vs_swath).",
        "symptom": "Commissioning images are offset from their targets.",
        "trigger": {"type": DETERMINISTIC, "check": "pointing_instability",
                    "source_constraint": "pointing_vs_swath"},
        "related_step": "adcs",
        "recovery": "Does not recover by itself: the pointing capability comes from the design.",
        "assumptions": ["Share of targets missed = ground pointing error / swath width, capped at 100% "
                        "(gameplay rule, not a coverage simulation).",
                        "Repeating an observation costs the same operating time and data as the first attempt."],
        "responses": [
            {"id": "accept_missed_targets", "label": "Accept the missed targets", "default": True,
             "standing": True,
             "description": "Keep the observation plan and accept that some targets are missed.",
             "trade_off": "No extra power or data, but about {miss_pct:.0f}% of observations miss.",
             "effects": {"science": "hit_fraction"},
             "outcome": "Pointing error of {offset_km:.1f} km against the {swath_km:g} km swath of "
                        "{instrument_id}: about {miss_pct:.0f}% of planned observations missed their target "
                        "for the whole mission."},
            {"id": "repeat_missed_observations", "label": "Repeat the missed observations",
             "standing": True, "requires": "power_for_repeat_observations",
             "description": "Re-observe missed targets on later orbits.",
             "trade_off": "Recovers the observations, but operating time, power demand and data volume rise "
                          "by {miss_pct:.0f}%.",
             "effects": {"data": "repeat_factor"},
             "outcome": "Missed targets were re-observed: full coverage, with {miss_pct:.0f}% more operating "
                        "time and data to downlink for the whole mission."},
        ],
    },
    {
        "id": "optical_downlink_cloud",
        "name": "Optical downlink blocked by cloud",
        "description": "Cloud over the optical ground station blocks the laser downlink for one period.",
        "mission_types": [EARTH_OBSERVATION], "phases": SCIENCE,
        "category": EXTERNAL, "affected_system": "communications", "severity": "medium",
        "cause": "Cloud over the optical ground station (external event) on a design whose main downlink "
                 "is optical.",
        "symptom": "The ground terminal cannot acquire the downlink beam.",
        "trigger": {"type": SEEDED, "check": "optical_downlink_cloud", "source_event": "optical_cloud",
                    "probability_parameter": "events.optical_cloud_probability"},
        "related_step": "communications",
        "recovery": "The optical link is available again at the start of the next operation period.",
        "recurring": True,
        "assumptions": ["Only eligible when the main downlink radio needs an optical ground station."],
        "responses": [
            {"id": "wait_for_clear_sky", "label": "Wait for clear sky", "default": True,
             "description": "Hold the data on board until the optical link is back.",
             "trade_off": "Science continues, but this period's data joins the backlog.",
             "effects": {"primary_downlink": "lost"},
             "outcome": "Cloud blocked the laser downlink this period; the data waits on board."},
            {"id": "switch_to_rf_downlink", "label": "Downlink on the radio-frequency link",
             "requires": "backup_radio_rf",
             "description": "Use a radio-frequency radio, which cloud does not block.",
             "trade_off": "Keeps data flowing, at the radio link's own (usually much lower) rate.",
             "effects": {"primary_downlink": "lost", "backup_downlink": "backup"},
             "outcome": "Downlink moved to {backup_radio_id} at {backup_gb_per_day:.2f} GB per day for this "
                        "period (the optical link returns {primary_gb_per_day:.2f} GB per day)."},
        ],
    },
]

# The four event types the v4 engine already had. run_simulation() uses exactly this scope with the
# default responses, so its results are unchanged.
SCOPE_LEGACY = ("communication_outage", "power_shortage", "optical_downlink_cloud", "instrument_unavailable")
SCOPE_MVP = SCOPE_LEGACY + ("data_backlog", "pointing_instability")


def _build(raw: dict[str, Any]) -> AnomalyDefinition:
    data = dict(raw)
    data["responses"] = [Response(**r) for r in raw["responses"]]
    definition = AnomalyDefinition(**data)
    defaults = [r for r in definition.responses if r.default]
    if len(defaults) != 1 or defaults[0].requires:
        raise ValueError(f"anomaly '{definition.id}' needs exactly one default response with no requirement")
    return definition


CATALOG: dict[str, AnomalyDefinition] = {d["id"]: _build(d) for d in _DEFINITIONS}


def get(anomaly_id: str) -> Optional[AnomalyDefinition]:
    return CATALOG.get(anomaly_id)


def definitions_for(mission_type: str, scope: tuple[str, ...] = SCOPE_MVP) -> list[AnomalyDefinition]:
    """Definitions that apply to a mission type, in catalogue order."""
    return [d for d in CATALOG.values() if d.id in scope and mission_type in d.mission_types]


def mission_type_info(mission_type: str) -> Optional[dict[str, Any]]:
    return MISSION_TYPES.get(mission_type)
