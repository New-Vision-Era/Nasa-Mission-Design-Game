"""Engine tests against a tiny hand-built catalog (no files, no backend).

These cover the PLACEHOLDER model. Person 2: keep the purity and
determinism tests when you replace the formulas.
"""

from simulation import engine
from simulation.models import Catalog, Component, Decision, Design, Event, EventOption, Objective, Scenario, Spacecraft


def tiny_catalog(event_probability: float = 0.0) -> Catalog:
    comps = [
        Component(id="bus", category="platform", name="Bus", mass_kg=100, power_w=50, cost_usd=10),
        Component(id="cam", category="instrument", name="Cam", mass_kg=10, power_w=50, cost_usd=10,
                  data_rate_gb_per_day=10, serves_objective_ids=["img"]),
        Component(id="sun", category="power", name="Sun", mass_kg=10, power_output_w=200, cost_usd=10),
        Component(id="ant", category="communication", name="Ant", mass_kg=5, power_w=20, cost_usd=10,
                  downlink_gb_per_day=10),
        Component(id="leo", category="orbit", name="LEO", suitable_objective_ids=["img"]),
        Component(id="rocket", category="launch_vehicle", name="Rocket", payload_capacity_kg=200, cost_usd=10),
    ]
    events = []
    if event_probability:
        events.append(Event(
            id="storm", title="Storm", description="", base_probability=event_probability,
            options=[
                EventOption(option_id="safe", label="Safe", effect_summary="",
                            effects=[{"op": "scale_step_science", "value": 0.5}]),
                EventOption(option_id="risk", label="Risk", effect_summary="",
                            effects=[{"op": "health_delta", "value": -0.5}]),
            ],
        ))
    scenario = Scenario(
        id="s", name="S", briefing="", budget_usd=100, mission_duration_days=100, operations_steps=4,
        objectives=[Objective(id="img", name="Imaging", target_data_gb=1000)],
        required_slots=["spacecraft.platform_id", "spacecraft.instrument_ids", "spacecraft.power_system_id",
                        "spacecraft.communication_system_id", "orbit_id", "launch_vehicle_id"],
    )
    return Catalog(catalog_version="t", data_status="mock", components={c.id: c for c in comps},
                   scenarios={"s": scenario}, events=events)


def design() -> Design:
    return Design(
        scenario_id="s",
        spacecraft=Spacecraft(platform_id="bus", instrument_ids=["cam"], power_system_id="sun",
                              communication_system_id="ant"),
        orbit_id="leo", launch_vehicle_id="rocket",
    )


def test_resource_sums_and_units():
    cat = tiny_catalog()
    ev = engine.evaluate_design(design(), cat.scenarios["s"], cat)
    assert ev.resources["total_mass_kg"] == 125          # launcher mass is not part of the spacecraft
    assert ev.resources["power_required_w"] == 120       # the power system does not consume
    assert ev.resources["power_available_w"] == 200
    assert ev.resources["cost_usd"] == 50                # the launcher's cost counts
    assert ev.launchable


def test_boundary_exactly_at_the_limit_passes():
    cat = tiny_catalog()
    cat.components["rocket"].payload_capacity_kg = 125
    ev = engine.evaluate_design(design(), cat.scenarios["s"], cat)
    assert next(c for c in ev.constraints if c.id == "launch_mass").status == "passed"
    cat.components["rocket"].payload_capacity_kg = 124.9
    ev = engine.evaluate_design(design(), cat.scenarios["s"], cat)
    assert next(c for c in ev.constraints if c.id == "launch_mass").status == "failed"
    assert not ev.launchable


def test_run_without_events_completes_in_one_call():
    cat = tiny_catalog()
    state = engine.start_run(design(), cat.scenarios["s"], cat, seed=1)
    assert state.status == "completed" and state.progress.step == 4
    assert state.telemetry["science_data_returned_gb"] == 1000  # 10 GB/day x 100 days
    debrief = engine.build_debrief(state, cat.scenarios["s"], cat)
    assert debrief.outcome == "success" and debrief.score["objectives"] == 100


def test_decisions_change_the_outcome_and_inputs_are_not_mutated():
    cat = tiny_catalog(event_probability=1.0)
    scenario = cat.scenarios["s"]
    start = engine.start_run(design(), scenario, cat, seed=1)
    assert start.status == "awaiting_decision" and start.progress.step == 0
    before = start.model_dump()

    safe = engine.apply_decision(start, Decision(event_id="storm", option_id="safe"), scenario, cat)
    risk = engine.apply_decision(start, Decision(event_id="storm", option_id="risk"), scenario, cat)
    assert start.model_dump() == before                    # pure: the input state is untouched
    assert safe.status == risk.status == "completed"       # the event does not repeat
    assert safe.telemetry["science_data_returned_gb"] == 875   # one of four periods halved
    assert risk.telemetry["health_fraction"] == 0.5
    assert risk.telemetry["science_data_returned_gb"] == 500   # every period at half health

    again = engine.apply_decision(start, Decision(event_id="storm", option_id="safe"), scenario, cat)
    assert again == safe                                   # deterministic


def test_declared_launch_vehicle_orbit_incompatibility_is_hard():
    cat = tiny_catalog()
    cat.components["rocket"].supported_orbit_ids = ["not_supported"]
    ev = engine.evaluate_design(design(), cat.scenarios["s"], cat)
    result = next(c for c in ev.constraints if c.id == "launch_orbit_compatibility")
    assert result.severity == "hard"
    assert result.status == "failed"
    assert ev.launchable is False
