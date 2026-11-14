"""Simulation engine: the four functions the backend calls.

    PLACEHOLDER MODEL - owned by Person 2 (Simulation & Game Mechanics).

The formulas below are deliberately simple gameplay arithmetic so the whole
game can be played end to end while the real model is written. They are NOT
a physics simulation and must not be presented as one. Replace the bodies
freely; keep the four signatures and the models in ``simulation/models.py``.

Every function is pure: same inputs, same output. No files, network, clock
or global state. Randomness comes only from the run's seed.
"""

import random
from typing import Optional

from simulation.models import (
    Catalog,
    Component,
    ConstraintResult,
    Debrief,
    Decision,
    Design,
    Evaluation,
    Event,
    Finding,
    LogEntry,
    ObjectiveResult,
    PendingEvent,
    PendingEventOption,
    Progress,
    RunState,
    Scenario,
)

MIN_MARGIN = 0.10  # soft goal: keep 10 % mass and power margin


# --------------------------------------------------------------------------
# 1. evaluate_design
# --------------------------------------------------------------------------


def _selected(design: Design, catalog: Catalog) -> dict[str, list[Component]]:
    return {
        slot: [catalog.components[i] for i in ids if i in catalog.components]
        for slot, ids in design.slot_values().items()
    }


def _sum(components: list[Component], field: str) -> float:
    return float(sum(getattr(c, field) or 0 for c in components))


def _limit_check(
    id: str,
    severity: str,
    value: float,
    limit: float,
    unit: str,
    step: str,
    ready: bool,
    ok: str,
    bad: str,
) -> ConstraintResult:
    """value must be <= limit."""
    if not ready:
        return ConstraintResult(
            id=id, severity=severity, status="not_evaluated", unit=unit,
            related_step=step, message="Not evaluated yet: a selection is still missing.",
        )
    passed = value <= limit
    margin = round((limit - value) / limit, 4) if limit else None
    return ConstraintResult(
        id=id,
        severity=severity,
        status="passed" if passed else ("failed" if severity == "hard" else "warning"),
        value=value,
        limit=limit,
        unit=unit,
        margin_fraction=margin,
        related_step=step,
        message=ok if passed else bad,
    )


def evaluate_design(design: Design, scenario: Scenario, catalog: Catalog) -> Evaluation:
    sel = _selected(design, catalog)
    values = design.slot_values()

    spacecraft_slots = [s for s in sel if s.startswith("spacecraft.")]
    spacecraft = [c for s in spacecraft_slots for c in sel[s]]
    everything = [c for comps in sel.values() for c in comps]
    instruments = sel["spacecraft.instrument_ids"]
    power = sel["spacecraft.power_system_id"]
    comms = sel["spacecraft.communication_system_id"]
    orbit = sel["orbit_id"]
    launcher = sel["launch_vehicle_id"]

    mass = _sum(spacecraft, "mass_kg")
    power_required = _sum([c for c in spacecraft if c.category != "power"], "power_w")
    power_available = _sum(power, "power_output_w")
    cost = _sum(everything, "cost_usd")
    data_generated = _sum(instruments, "data_rate_gb_per_day")
    downlink = _sum(comms, "downlink_gb_per_day")
    capacity = _sum(launcher, "payload_capacity_kg")

    resources: dict[str, float] = {
        "total_mass_kg": mass,
        "power_required_w": power_required,
        "power_available_w": power_available,
        "data_generated_gb_per_day": data_generated,
        "downlink_capacity_gb_per_day": downlink,
        "cost_usd": cost,
        "budget_usd": float(scenario.budget_usd),
    }
    if launcher:
        resources["launch_capacity_kg"] = capacity
        if capacity:
            resources["mass_margin_fraction"] = round((capacity - mass) / capacity, 4)
    if power and power_available:
        resources["power_margin_fraction"] = round(
            (power_available - power_required) / power_available, 4
        )

    constraints: list[ConstraintResult] = []

    # --- hard constraints -------------------------------------------------
    constraints.append(_limit_check(
        "launch_mass", "hard", mass, capacity, "kg", "launch_vehicle", bool(launcher),
        "Spacecraft mass is within the launch vehicle's capacity.",
        "The spacecraft is heavier than the launch vehicle can carry.",
    ))
    constraints.append(_limit_check(
        "power_balance", "hard", power_required, power_available, "W", "power", bool(power),
        "The power system supplies enough power for every selected component.",
        "The selected components need more power than the power system produces.",
    ))
    constraints.append(_limit_check(
        "budget", "hard", cost, float(scenario.budget_usd), "USD", "budget", True,
        "The design is within the mission budget.",
        "The design costs more than the mission budget.",
    ))

    served = {o for c in instruments for o in c.serves_objective_ids}
    uncovered = [o.name for o in scenario.objectives if o.id not in served]
    if not instruments:
        cover_status, cover_msg = "not_evaluated", "Not evaluated yet: no instrument selected."
    elif uncovered:
        cover_status = "failed"
        cover_msg = "No selected instrument can perform: " + ", ".join(uncovered) + "."
    else:
        cover_status, cover_msg = "passed", "Every mission objective has an instrument that serves it."
    constraints.append(ConstraintResult(
        id="objective_coverage", severity="hard", status=cover_status,
        related_step="instruments", message=cover_msg,
    ))

    # --- soft goals -------------------------------------------------------
    constraints.append(_limit_check(
        "downlink_capacity", "soft", data_generated, downlink, "GB/day", "communications",
        bool(instruments and comms),
        "The antenna can send home all the data the instruments produce.",
        "The instruments produce more data each day than the antenna can send home; the excess is lost.",
    ))
    for cid, key, step, label in (
        ("mass_margin", "mass_margin_fraction", "launch_vehicle", "mass"),
        ("power_margin", "power_margin_fraction", "power", "power"),
    ):
        margin = resources.get(key)
        if margin is None:
            constraints.append(ConstraintResult(
                id=cid, severity="soft", status="not_evaluated", unit="fraction",
                related_step=step, message="Not evaluated yet: a selection is still missing.",
            ))
        else:
            ok = margin >= MIN_MARGIN
            constraints.append(ConstraintResult(
                id=cid, severity="soft", status="passed" if ok else "warning",
                value=margin, limit=MIN_MARGIN, unit="fraction", margin_fraction=margin,
                related_step=step,
                message=(
                    f"Healthy {label} margin."
                    if ok
                    else f"Thin {label} margin (below {int(MIN_MARGIN * 100)} %): little room for surprises."
                ),
            ))

    if not orbit:
        orbit_status, orbit_msg = "not_evaluated", "Not evaluated yet: no orbit selected."
    else:
        suitable = set(orbit[0].suitable_objective_ids)
        poor = [o.name for o in scenario.objectives if o.id not in suitable]
        orbit_status = "warning" if poor else "passed"
        orbit_msg = (
            "This orbit is a poor fit for: " + ", ".join(poor) + "."
            if poor
            else "The orbit suits the mission objectives."
        )
    constraints.append(ConstraintResult(
        id="orbit_suitability", severity="soft", status=orbit_status,
        related_step="orbit", message=orbit_msg,
    ))

    missing = [slot for slot in scenario.required_slots if not values.get(slot)]
    complete = not missing
    hard_failed = any(c.severity == "hard" and c.status == "failed" for c in constraints)

    return Evaluation(
        catalog_version=catalog.catalog_version,
        complete=complete,
        launchable=complete and not hard_failed,
        missing=missing,
        resources=resources,
        constraints=constraints,
    )


# --------------------------------------------------------------------------
# 2-3. start_run / apply_decision
# --------------------------------------------------------------------------


def _find_event(catalog: Catalog, event_id: str) -> Optional[Event]:
    return next((e for e in catalog.events if e.id == event_id), None)


def _orbit_factor(state: RunState, scenario: Scenario, catalog: Catalog) -> float:
    """Placeholder: a poorly suited orbit halves useful science."""
    orbit = catalog.components.get(state.design.orbit_id or "")
    if orbit is None:
        return 1.0
    suitable = set(orbit.suitable_objective_ids)
    return 1.0 if all(o.id in suitable for o in scenario.objectives) else 0.5


def _draw_event(state: RunState, step: int, catalog: Catalog) -> Optional[Event]:
    rng = random.Random(f"{state.seed}:{step}:event")
    for event in catalog.events:
        roll = rng.random()  # one draw per event keeps runs reproducible
        if event.id in state.occurred_event_ids:
            continue
        p = event.base_probability
        if event.risk_resource:
            margin = state.resources.get(event.risk_resource)
            if margin is not None and margin < event.risk_threshold and event.risk_threshold > 0:
                shortfall = (event.risk_threshold - margin) / event.risk_threshold
                p *= 1 + min(shortfall, 1.0) * event.risk_multiplier
        if roll < min(p, 1.0):
            return event
    return None


def _complete_step(state: RunState, step: int, step_days: float, scale: float, orbit_factor: float) -> None:
    r = state.resources
    daily = min(r.get("data_generated_gb_per_day", 0.0), r.get("downlink_capacity_gb_per_day", 0.0))
    health = state.telemetry.get("health_fraction", 1.0)
    gained = daily * step_days * health * scale * orbit_factor
    state.telemetry["science_data_returned_gb"] = round(
        state.telemetry.get("science_data_returned_gb", 0.0) + gained, 2
    )
    state.progress.step = step
    state.progress.elapsed_days = round(state.progress.elapsed_days + step_days, 2)
    state.log.append(LogEntry(step=step, message=f"Returned {gained:.0f} GB of science data."))


def _advance(
    state: RunState, scenario: Scenario, catalog: Catalog,
    first_step_scale: float = 1.0, skip_first_event: bool = False,
) -> RunState:
    total = state.progress.total_steps
    step_days = scenario.mission_duration_days / total
    orbit_factor = _orbit_factor(state, scenario, catalog)
    scale, skip = first_step_scale, skip_first_event
    while state.progress.step < total:
        step = state.progress.step + 1
        if not skip:
            event = _draw_event(state, step, catalog)
            if event is not None:
                state.status = "awaiting_decision"
                state.pending_event = PendingEvent(
                    event_id=event.id,
                    title=event.title,
                    description=event.description,
                    options=[
                        PendingEventOption(
                            option_id=o.option_id, label=o.label, effect_summary=o.effect_summary
                        )
                        for o in event.options
                    ],
                )
                state.log.append(LogEntry(step=step, message=f"Event: {event.title}."))
                return state
        _complete_step(state, step, step_days, scale, orbit_factor)
        scale, skip = 1.0, False
    state.status = "completed"
    state.pending_event = None
    state.log.append(LogEntry(step=total, message="Mission complete."))
    return state


def start_run(design: Design, scenario: Scenario, catalog: Catalog, seed: int) -> RunState:
    evaluation = evaluate_design(design, scenario, catalog)
    state = RunState(
        status="awaiting_decision",
        seed=seed,
        design=design.model_copy(deep=True),
        progress=Progress(step=0, total_steps=scenario.operations_steps, elapsed_days=0.0),
        resources=dict(evaluation.resources),
        telemetry={"science_data_returned_gb": 0.0, "health_fraction": 1.0},
        log=[LogEntry(step=0, message="Launch and deployment complete.")],
    )
    return _advance(state, scenario, catalog)


def apply_decision(state: RunState, decision: Decision, scenario: Scenario, catalog: Catalog) -> RunState:
    """Raises ValueError if the decision does not match the pending event."""
    if state.status != "awaiting_decision" or state.pending_event is None:
        raise ValueError("This run is not waiting for a decision.")
    if decision.event_id != state.pending_event.event_id:
        raise ValueError("The decision is for a different event than the pending one.")
    event = _find_event(catalog, decision.event_id)
    option = next((o for o in event.options if o.option_id == decision.option_id), None) if event else None
    if option is None:
        raise ValueError(f"Unknown option '{decision.option_id}' for event '{decision.event_id}'.")

    state = state.model_copy(deep=True)
    step = state.progress.step + 1
    rng = random.Random(f"{state.seed}:{step}:outcome")
    scale = 1.0
    notes = []
    for effect in option.effects:
        if effect.chance is not None and rng.random() >= effect.chance:
            notes.append("the risk did not materialise")
            continue
        if effect.op == "scale_step_science":
            scale *= effect.value
            notes.append(f"science for this period scaled by {effect.value:g}")
        elif effect.op == "health_delta":
            health = state.telemetry.get("health_fraction", 1.0) + effect.value
            state.telemetry["health_fraction"] = round(max(0.0, min(1.0, health)), 4)
            notes.append(f"spacecraft health changed by {effect.value:+g}")
    state.occurred_event_ids.append(event.id)
    state.pending_event = None
    state.log.append(LogEntry(
        step=step,
        message=f"Decision: {option.label}" + (f" ({'; '.join(notes)})." if notes else "."),
    ))
    return _advance(state, scenario, catalog, first_step_scale=scale, skip_first_event=True)


# --------------------------------------------------------------------------
# 4. build_debrief
# --------------------------------------------------------------------------


def build_debrief(state: RunState, scenario: Scenario, catalog: Catalog) -> Debrief:
    evaluation = evaluate_design(state.design, scenario, catalog)
    returned = state.telemetry.get("science_data_returned_gb", 0.0)
    health = state.telemetry.get("health_fraction", 1.0)
    generated_total = state.resources.get("data_generated_gb_per_day", 0.0) * scenario.mission_duration_days

    objectives = []
    for o in scenario.objectives:
        fraction = round(min(1.0, returned / o.target_data_gb), 4) if o.target_data_gb else 0.0
        objectives.append(ObjectiveResult(
            id=o.id,
            achieved_fraction=fraction,
            message=f"{o.name}: returned {returned:.0f} GB of the {o.target_data_gb:.0f} GB target.",
        ))
    achieved = sum(o.achieved_fraction for o in objectives) / len(objectives) if objectives else 0.0

    warnings = [c for c in evaluation.constraints if c.status == "warning"]
    score = {
        # share of the data the instruments collected that actually reached the ground
        "science": round(100 * min(1.0, returned / generated_total), 1) if generated_total else 0.0,
        "reliability": round(100 * health, 1),
        "efficiency": float(max(0, 100 - 20 * len(warnings))),
        "objectives": round(100 * achieved, 1),
    }
    weights = scenario.scoring_weights
    weight_sum = sum(weights.get(k, 0.0) for k in score) or 1.0
    score["total"] = round(sum(score[k] * weights.get(k, 0.0) for k in list(score)) / weight_sum, 1)

    outcome = "success" if achieved >= 0.9 else ("partial_success" if achieved >= 0.5 else "failure")

    findings: list[Finding] = []
    for c in warnings:
        findings.append(Finding(
            kind="weakness", related_step=c.related_step, message=c.message,
            suggestion=f"Revisit the {c.related_step.replace('_', ' ')} step before the next attempt.",
        ))
    if health < 1.0:
        findings.append(Finding(
            kind="weakness", related_step=None,
            message=f"The spacecraft ended the mission at {health * 100:.0f} % health after an operational event.",
            suggestion="A more cautious response to events protects later science.",
        ))
    if achieved >= 0.9:
        findings.append(Finding(kind="strength", message="The mission met its science data target."))
    if not warnings:
        findings.append(Finding(kind="strength", message="Every engineering margin was healthy at launch."))

    return Debrief(outcome=outcome, score=score, objectives=objectives, findings=findings)
