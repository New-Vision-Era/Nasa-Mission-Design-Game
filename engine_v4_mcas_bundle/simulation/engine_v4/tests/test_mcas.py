"""Tests for MCAS. Run from the repository root: python -m pytest simulation/engine_v4 -q"""
from __future__ import annotations

import copy
import json

import pytest

from simulation.engine_v4 import api, configuration, interactive, run_simulation
from simulation.engine_v4.configuration import ConfigError, load_scenario, parse_config
from simulation.engine_v4.data_loader import load_catalog
from simulation.engine_v4.engine import evaluate_design as engine_evaluate
from simulation.engine_v4.mission import operations
from simulation.engine_v4.mission.mcas import anomaly_catalog, state_manager, trigger_engine
from simulation.engine_v4.mission.mcas.models import (AWAITING_DECISION, COMPLETED, HIGH, LOW, MEDIUM, NOT_LAUNCHED,
                                                      PERSISTING, RECOVERED, UNKNOWN, DecisionError, RunContext)
from simulation.engine_v4.mission.mcas.risk_assessment import assess_risk

SCENARIO = "earth_observation_v4"
RATES = {"data_generation_kbps": {"hyperscape100": 20000, "mantis": 5000, "c3d": 100}}
NO_EVENTS = {"events": {"enabled": False}}
ALWAYS = {"events": {"comm_outage_probability": 1.0, "reduced_solar_probability": 1.0,
                     "optical_cloud_probability": 1.0, "instrument_unavailable_probability": 1.0}}
MODE_B = {"mode": "player_built_power_system", "solar_array_ids": ["endurosat_6u_solar_panel"] * 3,
          "battery_ids": ["gomspace_bp4"]}


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


def config(**overrides) -> dict:
    base = {
        "scenario_id": SCENARIO, "platform_id": "gsat_50", "instrument_ids": ["hyperscape100"],
        "power": {"mode": "platform_payload_budget"},
        "communication_system_ids": ["endurosat_s_band_transceiver", "endurosat_x_band_transmitter"],
        "adcs_system_id": "cubespace_cubeadcs_3axis_small_star", "propulsion_system_id": None,
        "orbit_id": "sso_500", "launch_vehicle_id": "rocket_lab_electron",
    }
    base.update(overrides)
    return base


def merged(*parts: dict) -> dict:
    out: dict = {}
    for part in parts:
        for key, value in part.items():
            out[key] = {**out[key], **value} if isinstance(value, dict) and isinstance(out.get(key), dict) else value
    return out


def context(cfg: dict, params: dict | None, catalog, seed: int = 0) -> RunContext:
    parsed = parse_config(cfg)
    scenario = load_scenario(parsed.scenario_id, params)
    sel, evaluation, performance = engine_evaluate(parsed, scenario.params, catalog)
    return RunContext(parsed, scenario.id, scenario.mission_type, sel, scenario.params, evaluation, performance, seed)


def play(state: dict, choose) -> dict:
    """Answer every decision with choose(pending) until the run ends."""
    guard = 0
    while state["status"] == AWAITING_DECISION:
        pending = state["pending_decision"]
        state = interactive.apply_decision(state, pending["anomaly_id"], choose(pending))
        guard += 1
        assert guard < 200
    return state


def default_choice(pending: dict) -> str:
    return next(r["id"] for r in pending["responses"] if r["is_default"])


def first_alternative(pending: dict) -> str:
    return next(r["id"] for r in pending["responses"] if r["available"] and not r["is_default"])


# ------------------------------------------------------------------ catalogue

def test_every_definition_is_complete_and_labelled():
    for d in anomaly_catalog.CATALOG.values():
        assert d.cause and d.symptom and d.description and d.recovery and d.phases
        assert d.value_kind == "gameplay_assumption"
        assert d.trigger["check"] in trigger_engine.CHECKS
        assert 2 <= len(d.responses) <= 3
        assert sum(r.default for r in d.responses) == 1
        assert d.default_response().requires is None


def test_mvp_scope_is_four_shared_plus_two_earth_observation():
    eo = {d.id for d in anomaly_catalog.definitions_for("earth_observation")}
    assert eo == {"power_shortage", "communication_outage", "data_backlog", "instrument_unavailable",
                  "pointing_instability", "optical_downlink_cloud"}
    shared = {d.id for d in anomaly_catalog.definitions_for("moon_landing")}
    assert shared == {"power_shortage", "communication_outage", "data_backlog", "instrument_unavailable"}


def test_three_mission_types_are_declared_and_only_earth_observation_is_implemented():
    types = anomaly_catalog.MISSION_TYPES
    assert set(types) == {"earth_observation", "moon_landing", "mars_landing"}
    assert types["earth_observation"]["implemented"] is True
    assert "landing" not in types["earth_observation"]["phases"]
    for name in ("moon_landing", "mars_landing"):
        assert types[name]["implemented"] is False and types[name]["not_implemented_reason"]
    assert "atmospheric_entry" in types["mars_landing"]["phases"]
    assert "atmospheric_entry" not in types["moon_landing"]["phases"]


def test_unimplemented_mission_type_is_refused_not_faked(tmp_path, monkeypatch):
    source = json.loads((configuration.SCENARIO_DIR / f"{SCENARIO}.json").read_text(encoding="utf-8"))
    source.update(id="moon_test", mission_type="moon_landing")
    (tmp_path / "moon_test.json").write_text(json.dumps(source), encoding="utf-8")
    monkeypatch.setattr(configuration, "SCENARIO_DIR", tmp_path)
    with pytest.raises(ConfigError) as err:
        interactive.start_run(config(scenario_id="moon_test"), 1)
    assert err.value.errors[0]["code"] == "not_implemented"


# ------------------------------------------------------------------ risk assessment

def test_risk_levels_follow_the_engineering_evaluation(catalog):
    risk = assess_risk(context(config(), RATES, catalog))
    by_id = {r["id"]: r for r in risk["risks"]}
    assert by_id["constraint.data_balance"]["level"] == MEDIUM
    assert by_id["constraint.data_balance"]["linked_anomaly_ids"] == ["data_backlog"]
    assert by_id["margin.power_margin_fraction"]["level"] == LOW
    assert by_id["exposure.communication_outage"]["level"] == LOW      # S-band backs up X-band
    assert by_id["exposure.instrument_unavailable"]["level"] == MEDIUM  # single suitable instrument
    assert risk["feasibility_status"] == "CONDITIONAL" and risk["launchable"] is True


def test_unknown_values_stay_unknown_in_the_risk_assessment(catalog):
    risk = assess_risk(context(config(), None, catalog))
    by_id = {r["id"]: r for r in risk["risks"]}
    assert by_id["constraint.data_balance"]["level"] == UNKNOWN          # no data rate published
    assert by_id["constraint.data_balance"]["linked_anomaly_ids"] == []
    assert by_id["exposure.power_shortage"]["level"] == UNKNOWN          # platform generation not modelled
    assert risk["counts"][UNKNOWN] >= 2


def test_hard_failure_is_high_risk_and_blocks_launch(catalog):
    cfg = config(communication_system_ids=["endurosat_x_band_transmitter"])  # transmit only: not commandable
    risk = assess_risk(context(cfg, None, catalog))
    blocking = [r for r in risk["risks"] if r["blocks_launch"]]
    assert blocking and all(r["level"] == HIGH for r in blocking)
    assert risk["launchable"] is False and risk["feasibility_status"] == "INFEASIBLE"


def test_limited_power_margin_is_medium_and_exposed_to_reduced_generation(catalog):
    risk = assess_risk(context(config(power=MODE_B), None, catalog))
    by_id = {r["id"]: r for r in risk["risks"]}
    assert by_id["margin.power_margin_fraction"]["level"] == MEDIUM
    assert by_id["exposure.power_shortage"]["level"] == MEDIUM


# ------------------------------------------------------------------ deterministic triggers

def test_data_backlog_triggers_deterministically_whatever_the_seed():
    for seed in (0, 1, 99):
        state = interactive.start_run(config(), seed, merged(RATES, NO_EVENTS))
        assert state["status"] == AWAITING_DECISION
        pending = state["pending_decision"]
        assert pending["anomaly_id"] == "data_backlog" and pending["trigger_type"] == "deterministic"
        assert pending["category"] == "engineering" and pending["period"] == 1


def test_data_backlog_is_not_eligible_when_rates_are_unknown():
    state = interactive.start_run(config(), 3, NO_EVENTS)
    assert state["status"] == COMPLETED
    assert [e["definition_id"] for e in state["events_not_applicable"]] == ["data_backlog"]
    assert state["resources"]["data_backlog_bits"] is None
    assert state["resources"]["battery_energy_wh"] is None
    assert state["resources"]["propellant_remaining_kg"] is None


def test_no_backlog_anomaly_when_the_downlink_is_sufficient():
    state = interactive.start_run(config(), 3, merged({"data_generation_kbps": {"hyperscape100": 100}}, NO_EVENTS))
    assert state["status"] == COMPLETED and state["resolved_anomalies"] == [] and state["active_anomalies"] == []
    assert state["resources"]["data_backlog_bits"] == 0.0


def test_pointing_instability_comes_from_the_pointing_constraint():
    cfg = config(adcs_system_id="cubespace_cubeadcs_3axis_small")
    state = interactive.start_run(cfg, 0, NO_EVENTS)
    records = state["active_anomalies"] + state["resolved_anomalies"]
    rec = next(r for r in records if r["definition_id"] == "pointing_instability")
    assert 0 < rec["facts"]["miss_fraction"] <= 1
    assert "cubespace_cubeadcs_3axis_small" in rec["contributing_design_decision"]
    better = interactive.start_run(config(), 0, NO_EVENTS)
    assert not any(r["definition_id"] == "pointing_instability"
                   for r in better["active_anomalies"] + better["resolved_anomalies"])


def test_accepting_missed_targets_reduces_observation_by_the_miss_fraction():
    cfg = config(adcs_system_id="cubespace_cubeadcs_3axis_small")
    state = play(interactive.start_run(cfg, 0, NO_EVENTS), default_choice)
    rec = next(r for r in state["active_anomalies"] if r["definition_id"] == "pointing_instability")
    debrief = interactive.build_debrief(state)
    observe = next(o for o in debrief["objectives"] if o["id"] == "observe_target")
    assert observe["achieved_fraction"] == pytest.approx(1 - rec["facts"]["miss_fraction"], abs=1e-3)
    assert rec["status"] == PERSISTING


# ------------------------------------------------------------------ reproducibility

def test_same_configuration_seed_and_decisions_reproduce_the_run():
    params = merged(RATES, {"events": {"comm_outage_probability": 0.5, "instrument_unavailable_probability": 0.4}})
    a = play(interactive.start_run(config(), 11, params, mission_id="a"), first_alternative)
    b = play(interactive.start_run(config(), 11, params, mission_id="a"), first_alternative)
    assert a == b
    assert interactive.build_debrief(a) == interactive.build_debrief(b)
    other = play(interactive.start_run(config(), 12, params, mission_id="a"), first_alternative)
    assert other["timeline"] != a["timeline"]


def test_a_stored_state_resumes_after_a_json_round_trip():
    state = interactive.start_run(config(), 0, RATES)
    stored = json.loads(json.dumps(state))
    interactive._RUNS.clear()
    resumed = play(stored, default_choice)
    assert resumed["status"] == COMPLETED
    assert json.loads(json.dumps(interactive.build_debrief(resumed)))["outcome"] == resumed["outcome"]


def test_an_anomaly_occurrence_is_never_triggered_twice():
    state = play(interactive.start_run(config(), 5, merged(RATES, ALWAYS)), default_choice)
    ids = [r["anomaly_id"] for r in state["active_anomalies"] + state["resolved_anomalies"]]
    assert len(ids) == len(set(ids))
    assert ids.count("data_backlog") == 1


# ------------------------------------------------------------------ decisions

def test_wrong_unknown_and_unavailable_responses_are_rejected():
    state = interactive.start_run(config(), 0, RATES)
    assert state["pending_decision"]["anomaly_id"] == "data_backlog"
    with pytest.raises(DecisionError) as err:
        interactive.apply_decision(state, "power_shortage-p01", "suspend_instruments")
    assert err.value.code == "wrong_anomaly"
    with pytest.raises(DecisionError) as err:
        interactive.apply_decision(state, "data_backlog", "reboot_everything")
    assert err.value.code == "unknown_response"
    with pytest.raises(DecisionError) as err:  # only one instrument on board: nothing secondary to switch off
        interactive.apply_decision(state, "data_backlog", "suspend_secondary_instruments")
    assert err.value.code == "response_unavailable"
    unavailable = next(r for r in state["pending_decision"]["responses"]
                       if r["id"] == "suspend_secondary_instruments")
    assert unavailable["available"] is False and unavailable["unavailable_reason"]


def test_no_decision_is_accepted_on_a_finished_run_or_before_a_debrief_is_due():
    done = interactive.start_run(config(), 3, NO_EVENTS)
    with pytest.raises(DecisionError) as err:
        interactive.apply_decision(done, "data_backlog", "continue_full_observation")
    assert err.value.code == "no_pending_decision"
    waiting = interactive.start_run(config(), 0, RATES)
    with pytest.raises(DecisionError) as err:
        interactive.build_debrief(waiting)
    assert err.value.code == "decision_pending"


def test_secondary_instruments_can_be_switched_off_only_when_there_are_some():
    cfg = config(instrument_ids=["hyperscape100", "c3d"])  # c3d is RGB: not a required family
    state = interactive.start_run(cfg, 0, merged({"data_generation_kbps": {"hyperscape100": 20000, "c3d": 20000}},
                                                 NO_EVENTS))
    option = next(r for r in state["pending_decision"]["responses"] if r["id"] == "suspend_secondary_instruments")
    assert option["available"] is True
    state = interactive.apply_decision(state, "data_backlog", "suspend_secondary_instruments")
    debrief = interactive.build_debrief(state)
    observe = next(o for o in debrief["objectives"] if o["id"] == "observe_target")
    assert observe["achieved_fraction"] == 1.0
    assert debrief["mission"]["totals"]["data_generated_bits"] == pytest.approx(
        0.5 * interactive.build_debrief(play(interactive.start_run(cfg, 0, state["scenario_parameters"]),
                                             default_choice))["mission"]["totals"]["data_generated_bits"])


# ------------------------------------------------------------------ same anomaly, different spacecraft

def test_communication_outage_depends_on_the_radios_carried():
    params = merged({"data_generation_kbps": {"hyperscape100": 5}},  # low enough for the S-band radio alone
                    {"events": {"comm_outage_probability": 1.0, "reduced_solar_probability": 0.0,
                                "optical_cloud_probability": 0.0, "instrument_unavailable_probability": 0.0}})
    two_bands = interactive.start_run(config(), 0, params)
    assert two_bands["status"] == AWAITING_DECISION  # a real choice: S-band can back up X-band
    option = next(r for r in two_bands["pending_decision"]["responses"] if r["id"] == "switch_to_backup_radio")
    assert option["available"] is True
    switched = interactive.build_debrief(play(two_bands, first_alternative))
    waited = interactive.build_debrief(play(interactive.start_run(config(), 0, params), default_choice))
    assert switched["mission"]["totals"]["data_downlinked_bits"] > 0
    assert waited["mission"]["totals"]["data_downlinked_bits"] == 0

    one_band = interactive.start_run(config(communication_system_ids=["endurosat_s_band_transceiver"]), 0, params)
    assert one_band["status"] == COMPLETED  # no backup: nothing to decide, and the debrief says why
    rec = one_band["resolved_anomalies"][0]
    assert rec["decided_by"] == "automatic" and "one ground-station type" in rec["contributing_design_decision"]
    assert next(r for r in rec["responses"] if r["id"] == "switch_to_backup_radio")["available"] is False


def test_reduced_solar_is_absorbed_or_becomes_a_shortage_depending_on_margin(catalog):
    events = {"events": {"comm_outage_probability": 0.0, "reduced_solar_probability": 1.0,
                         "optical_cloud_probability": 0.0, "instrument_unavailable_probability": 0.0}}
    tight = interactive.start_run(config(power=MODE_B), 0, events)
    assert tight["status"] == AWAITING_DECISION
    pending = tight["pending_decision"]
    assert pending["definition_id"] == "power_shortage"
    assert pending["facts"]["reduced_w"] < pending["facts"]["demand_w"]

    roomy = dict(MODE_B, solar_array_ids=["endurosat_6u_solar_panel"] * 6)
    ample = interactive.start_run(config(power=roomy), 0, events)
    assert ample["status"] == COMPLETED
    assert {r["status"] for r in ample["resolved_anomalies"]} == {RECOVERED}
    assert all(r["response_id"] is None for r in ample["resolved_anomalies"])

    platform = interactive.start_run(config(), 0, events)  # platform-supplied power: not modelled, not invented
    assert platform["resolved_anomalies"] == []
    assert {e["definition_id"] for e in platform["events_not_applicable"]} >= {"power_shortage"}


def test_power_saving_is_refused_when_standby_demand_already_exceeds_generation():
    events = {"events": {"comm_outage_probability": 0.0, "reduced_solar_probability": 1.0,
                         "optical_cloud_probability": 0.0, "instrument_unavailable_probability": 0.0}}
    state = interactive.start_run(config(power=MODE_B), 0, events)
    option = next(r for r in state["pending_decision"]["responses"] if r["id"] == "activate_power_saving_mode")
    assert option["available"] is False and "standby" in option["unavailable_reason"]


def test_power_saving_keeps_part_of_the_science_and_continuing_loses_the_downlink_too():
    # factor 0.8 leaves generation between standby demand and full demand, so reduced operation is possible
    events = {"events": {"comm_outage_probability": 0.0, "reduced_solar_probability": 1.0,
                         "reduced_solar_factor": 0.8,
                         "optical_cloud_probability": 0.0, "instrument_unavailable_probability": 0.0}}
    results = {}
    for choice in ("suspend_instruments", "activate_power_saving_mode", "continue_operations"):
        state = play(interactive.start_run(config(power=MODE_B), 0, events), lambda pending, c=choice: c)
        results[choice] = next(o for o in interactive.build_debrief(state)["objectives"]
                               if o["id"] == "observe_target")["achieved_fraction"]
        duty = state["resolved_anomalies"][0]["facts"]["power_limited_duty"]
    assert results["suspend_instruments"] == 0.0 and results["continue_operations"] == 0.0
    assert 0 < duty < 1 and results["activate_power_saving_mode"] == pytest.approx(duty, abs=1e-3)


def test_optical_cloud_never_affects_a_radio_frequency_design():
    events = {"events": {"comm_outage_probability": 0.0, "reduced_solar_probability": 0.0,
                         "optical_cloud_probability": 1.0, "instrument_unavailable_probability": 0.0}}
    state = interactive.start_run(config(), 0, events)
    assert state["status"] == COMPLETED and state["resolved_anomalies"] == []
    assert {e["definition_id"] for e in state["events_not_applicable"]} == {"optical_downlink_cloud", "data_backlog"}


def test_instrument_recovery_trades_downlink_for_observation():
    params = merged(RATES, {"events": {"comm_outage_probability": 0.0, "reduced_solar_probability": 0.0,
                                       "optical_cloud_probability": 0.0,
                                       "instrument_unavailable_probability": 1.0}})
    def run(choice):
        def choose(pending):
            return choice if pending["definition_id"] == "instrument_unavailable" else default_choice(pending)
        return interactive.build_debrief(play(interactive.start_run(config(), 0, params), choose))
    waited, recovered = run("wait_for_recovery"), run("run_recovery_procedure")
    observe = lambda d: next(o for o in d["objectives"] if o["id"] == "observe_target")["achieved_fraction"]
    assert observe(waited) == 0.0 and observe(recovered) == 0.5
    assert recovered["anomalies"][-1]["impact"]["data_not_downlinked_bits"] > 0


# ------------------------------------------------------------------ feasibility and scoring

def test_a_design_with_a_hard_failure_cannot_launch_and_gets_no_anomalies():
    cfg = config(communication_system_ids=["endurosat_x_band_transmitter"])
    state = interactive.start_run(cfg, 0, merged(RATES, ALWAYS))
    assert state["status"] == NOT_LAUNCHED and state["feasibility"]["status"] == "INFEASIBLE"
    assert state["pending_decision"] is None and state["resolved_anomalies"] == [] and state["timeline"] == []
    debrief = interactive.build_debrief(state)
    assert debrief["anomalies"] == [] and debrief["mission"]["launched"] is False
    assert debrief["score"]["valid_for_ranking"] is False and debrief["feasibility"]["status"] == "INFEASIBLE"


def test_conditional_feasibility_is_kept_through_the_run():
    state = play(interactive.start_run(config(), 0, RATES), first_alternative)
    debrief = interactive.build_debrief(state)
    assert state["conditional_launch"] is True
    assert debrief["feasibility"]["status"] == "CONDITIONAL" == debrief["score"]["feasibility_status"]


def test_score_weights_and_categories_are_unchanged_and_completeness_is_reported():
    debrief = interactive.build_debrief(play(interactive.start_run(config(), 0, RATES), first_alternative))
    weights = {c["id"]: c["weight"] for c in debrief["score"]["categories"]}
    assert weights == {"science": 35, "objectives": 25, "reliability": 20, "efficiency": 20}
    assert "completeness" in debrief["score"]
    assert debrief["operational_availability"]["included_in_score"] is False


def test_score_moves_only_through_what_the_mission_achieved():
    quiet = interactive.build_debrief(interactive.start_run(config(), 0, NO_EVENTS))
    assert quiet["anomalies"] == [] and quiet["reference_without_anomalies"]["score_difference"] == 0.0
    params = {"events": {"comm_outage_probability": 1.0, "reduced_solar_probability": 0.0,
                         "optical_cloud_probability": 0.0, "instrument_unavailable_probability": 0.0}}
    # data rates unknown: outages happen every period but cost nothing that can be evaluated
    busy = interactive.build_debrief(play(interactive.start_run(config(), 0, params), default_choice))
    assert len(busy["anomalies"]) == 12
    assert busy["score"]["total"] == quiet["score"]["total"]


def test_debrief_explains_every_anomaly_and_separates_the_five_groups():
    params = merged(RATES, {"events": {"comm_outage_probability": 0.6}})
    debrief = interactive.build_debrief(play(interactive.start_run(config(), 0, params), first_alternative))
    assert debrief["anomalies"]
    for rec in debrief["anomalies"]:
        for key in ("what_happened", "period", "affected_system", "cause", "contributing_design_decision",
                    "impact", "response_id", "recovered", "outcome"):
            assert key in rec
    assert set(debrief["debrief"]) == {"engineering_weaknesses", "external_events", "player_decisions",
                                       "mission_consequences", "gameplay_assumptions"}
    assert debrief["debrief"]["player_decisions"] and debrief["debrief"]["external_events"]
    assert len(debrief["anomaly_summaries"]) == len(debrief["anomalies"])
    json.dumps(debrief)


# ------------------------------------------------------------------ compatibility with the one-call engine

def test_run_simulation_is_unchanged_by_the_refactor(catalog):
    """Default responses over the original four event types reproduce the one-call result."""
    params = merged(RATES, {"events": {"comm_outage_probability": 0.3, "instrument_unavailable_probability": 0.3}})
    for seed in range(5):
        result = run_simulation(config(), params, seed)
        mission = result["mission"]
        assert set(mission) == {"launched", "conditional_launch", "outcome", "objective_fraction", "objectives",
                                "stages", "events", "timeline", "totals", "explanation"}
        assert isinstance(mission["totals"]["science_periods_completed"], int)
        ctx = context(config(), params, catalog, seed)
        prog = state_manager.advance(ctx, {}, scope=anomaly_catalog.SCOPE_LEGACY, interactive=False)
        assert operations.build_mission(ctx, prog, legacy_shape=True) == mission


# ------------------------------------------------------------------ request handlers

def test_handlers_cover_evaluate_start_decide_and_debrief():
    status, evaluation = api.handle_evaluate_request({"configuration": config(), "scenario_parameters": RATES})
    assert status == 200 and evaluation["risk_assessment"]["risks"]
    status, state = api.handle_start_request({"configuration": config(), "scenario_parameters": RATES, "seed": 4})
    assert status == 200 and state["status"] == AWAITING_DECISION
    status, body = api.handle_debrief_request({"state": state})
    assert status == 409 and body["error"]["code"] == "decision_pending"
    status, body = api.handle_decision_request({"state": state, "anomaly_id": "data_backlog", "response_id": "x"})
    assert status == 422 and body["error"]["code"] == "unknown_response"
    while state["status"] == AWAITING_DECISION:
        pending = state["pending_decision"]
        status, state = api.handle_decision_request({"mission_id": state["mission_id"],
                                                     "anomaly_id": pending["anomaly_id"],
                                                     "response_id": default_choice(pending)})
        assert status == 200
    status, debrief = api.handle_debrief_request({"mission_id": state["mission_id"]})
    assert status == 200 and debrief["outcome"] == state["outcome"]
    assert api.handle_decision_request({"mission_id": "nope", "anomaly_id": "a", "response_id": "b"})[0] == 404
    assert api.handle_start_request({"configuration": config(platform_id="nope")})[0] == 422
