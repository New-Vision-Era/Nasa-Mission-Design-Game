# MCAS — Mission Consequence & Anomaly System (engine v4)

MCAS turns the one-call v4 mission into a step-by-step mission with player decisions. It is a
simplified educational game model, not a reliability simulator. It adds no mass, power,
communications, propulsion or pointing formula: it reads the existing engineering evaluation.

Status (2026-11-15): foundation implemented for the Earth-observation mission. Moon and Mars
landing are declared in the catalogue as **not implemented** and are refused, not faked.

## What was in the engine, and what changed

| Existing module | Before | Now |
| --- | --- | --- |
| `mission/events.py` | Seeded generation and resolution of four event types | Unchanged. MCAS reuses `generate_events` for external events, so seeds give the same events as before |
| `mission/operations.py` | `simulate_mission` flew every period in one loop | `simulate_mission` runs through the full MCAS MVP scope (four seeded external events plus deterministic data-backlog and pointing anomalies), applying each declared default response. `build_mission` returns the anomaly records and expanded timeline |
| `configuration.py` | `Scenario(id, name, briefing, params)` | `Scenario.mission_type` added (default `earth_observation`) |
| `api.py` | run, recommend, catalog handlers | Four handlers added: evaluate, start, decision, debrief |
| `evaluation.py`, `constraints/`, `scoring.py`, `performance.py`, `results.py`, `engine.py` | | Not touched |

`run_simulation()` now includes the two design-caused anomalies (`data_backlog` and
`pointing_instability`) as well as the four seeded event types. Scores can therefore change for
designs with a data-rate/downlink imbalance or a pointing warning. Quick mode resolves all
anomalies with their declared default responses; an interactive run that selects those same
defaults is expected to produce the same mission outcome and score. A regression test checks this
for a design that triggers both design-caused anomalies.

## New files

```text
simulation/engine_v4/
├── interactive.py                 # evaluate_design, start_run, apply_decision, build_debrief
├── mission/mcas/
│   ├── models.py                  # statuses, definitions, modifiers, RunContext
│   ├── anomaly_catalog.py         # data-driven definitions, mission types, scopes
│   ├── trigger_engine.py          # eligibility and trigger checks, facts for the debrief
│   ├── anomaly_generator.py       # seeded external events (reuses events.py), occurrence ids
│   ├── decision_manager.py        # which responses are available, validation
│   ├── anomaly_resolver.py        # response -> modifiers, period arithmetic, per-anomaly impact
│   ├── state_manager.py           # advance to the next decision or to the end
│   ├── risk_assessment.py         # LOW / MEDIUM / HIGH / UNKNOWN from the evaluation
│   └── history.py                 # anomaly records and debrief text
└── tests/test_mcas.py             # 32 tests
```

## The four functions

```python
from simulation.engine_v4 import interactive

evaluation = interactive.evaluate_design(configuration, scenario_parameters=None)
state      = interactive.start_run(configuration, seed=0, scenario_parameters=None)
state      = interactive.apply_decision(state, anomaly_id, response_id)   # or a mission_id
debrief    = interactive.build_debrief(state)                             # or a mission_id
```

- `evaluate_design` returns feasibility, resources, margins, constraints and `risk_assessment`.
- `start_run` and `apply_decision` return a **run state**: a plain JSON dict. They stop at the next
  anomaly that offers a real choice (`status: AWAITING_DECISION`) or at the end (`COMPLETED`).
  An infeasible design returns `NOT_LAUNCHED`.
- The state holds the configuration, scenario overrides, seed and decisions. Every call replays the
  run from those, so a state stored as JSON (for example in the backend `runs` table) can be resumed
  later. Runs are also kept in process memory by `mission_id`; nothing is written to disk.
- Errors are `DecisionError` with a `code`: `no_pending_decision`, `wrong_anomaly`,
  `unknown_response`, `response_unavailable`, `decision_pending`, `not_found`, `invalid_state`.

Framework-free handlers in `api.py` (same error body as the other handlers):

| Handler | Suggested route | Body |
| --- | --- | --- |
| `handle_evaluate_request` | `POST /simulation/evaluate` | `{configuration, scenario_parameters?}` |
| `handle_start_request` | `POST /simulation/missions` | `{configuration, scenario_parameters?, seed?, mission_id?}` |
| `handle_decision_request` | `POST /simulation/missions/decisions` | `{state or mission_id, anomaly_id, response_id}` |
| `handle_debrief_request` | `POST /simulation/missions/debrief` | `{state or mission_id}` |

The routes are suggestions. No FastAPI router was written for them.

## Run state (main fields)

`mission_id`, `status`, `mission_type`, `scenario_id`, `seed`, `configuration`, `scenario_parameters`,
`decisions`, `feasibility`, `conditional_launch`, `current_phase`, `current_period`, `total_periods`,
`elapsed_days`, `resources`, `objectives`, `pending_decision`, `active_anomalies`,
`resolved_anomalies`, `events_not_applicable`, `decision_history`, `mission_history`, `timeline`,
`outcome`, `score_total`.

`resources.data_backlog_bits` is tracked when instrument data rates are known, otherwise `null`.
`battery_energy_wh` and `propellant_remaining_kg` are always `null`: the model has no start value or
update rule for them, and none was invented.

`pending_decision.responses[]` lists every response with `available`, `unavailable_reason`,
`trade_off` and `is_default`.

## Anomalies in the MVP

| Anomaly | Kind | Trigger | Responses |
| --- | --- | --- | --- |
| `communication_outage` | external, seeded | `comm_outage` event | store and wait; switch to a backup radio on another ground-station type |
| `power_shortage` | external, seeded | `reduced_solar` event, and reduced generation below demand (player-built power only) | suspend instruments; power-saving mode; continue operations |
| `data_backlog` | engineering, deterministic | daily data generated above daily downlink capacity | keep full rate; observe only what can be downlinked; switch off secondary instruments |
| `instrument_unavailable` | external, seeded | `instrument_unavailable` event | wait for the next period; run a recovery procedure |
| `pointing_instability` (EO) | engineering, deterministic | `pointing_vs_swath` is a WARNING for an instrument serving the objective | accept missed targets; repeat missed observations |
| `optical_downlink_cloud` (EO) | external, seeded | `optical_cloud` event, and the main downlink radio is optical | wait for clear sky; switch to a radio-frequency downlink |

Rules that hold for all of them:

- A response is offered only if the spacecraft can do it (a second radio, power to spare, a
  secondary instrument). The reason is given when it cannot.
- An event the design tolerates is recorded as absorbed, with no decision and no cost. An event the
  design cannot be affected by is listed under `events_not_applicable` and never becomes an anomaly.
- If only one response is available, it is applied automatically and the record says which design
  choice left no alternative.
- Consequences are computed from the evaluation and the current backlog. No fixed points are
  subtracted for an anomaly.
- A hard constraint failure never becomes an anomaly: the design is `NOT_LAUNCHED`.
- Engineering anomalies are checked once, at the first operation period, and persist.

## Risk assessment

`risk_assessment.risks[]` has one entry per failed, warned or unevaluated constraint, per margin
(mass, power) and per external event the design is exposed to. Levels are `LOW`, `MEDIUM`, `HIGH`
and `UNKNOWN`. `UNKNOWN` was added to the three levels in the specification so that a missing value
is not reported as low risk. Margins are compared with the scenario's existing
`margin_target_fraction`. TRL is not used.

## Scoring

Weights and categories are unchanged (35 / 25 / 20 / 20) and `compute_score` was not edited. The
score moves only because the mission result (observation periods, data returned) changes. The
debrief adds `reference_without_anomalies`: the same design flown with no event, and the score
difference. `operational_availability` is reported but **not** included in reliability.

## Gameplay assumptions introduced by MCAS

All are labelled `gameplay_assumption` in the catalogue and listed in the debrief.

1. Share of targets missed = ground pointing error / swath width, capped at 100%.
2. `recovery_period_fraction` = 0.5: after a recovery procedure the instrument works for half the
   period and half the period's downlink is lost.
3. Continuing normal operations in a power shortage puts the spacecraft in safe mode for the period
   (no observation, no downlink).
4. A communication outage affects the ground-station type of the main downlink radio only.
5. Power-saving mode cuts instrument operating time to what the reduced generation supports, using
   the existing power demand model.

Event probabilities are still the ones in the scenario file. No new probability was added.

## Team decisions recorded

The Science & Simulation team selected the following:

1. **1B — Use the full MCAS MVP scope in both modes.** The quick one-call simulation now includes
   the two deterministic design-caused anomalies, `data_backlog` and `pointing_instability`,
   alongside the four seeded external event types. Quick mode applies each anomaly's declared
   default response. Existing scores can change for designs with a data-rate/downlink imbalance or
   a pointing warning. The quick result now includes anomaly records and the expanded mission timeline.
2. **2A — Accept all five gameplay assumptions unchanged.** The recovery fraction remains `0.5`;
   the five rules remain labelled `gameplay_assumption` in the anomaly catalogue and debrief.
3. **3A — Keep operational availability out of reliability scoring.** Availability remains visible
   in the debrief only. The 35 / 25 / 20 / 20 score weights and reliability calculation are unchanged.

A regression test compares a quick run with an interactive run in which every decision uses its
default response. It also verifies that both design-caused anomalies are included in the quick run.

Backend integration still translates the engine's v4 configuration dict and JSON mission state
through the backend adapter; `pending_event {event_id, options[]}` maps to
`pending_decision {anomaly_id, responses[]}`.

## Not implemented

- Moon and Mars landing models, their anomalies and their equipment data.
- Thermal, propulsion and attitude-control anomalies from the shared list (no thermal model; a
  propulsion shortfall is already a hard constraint).
- Response deadlines (`UNRESOLVED`), battery state of charge, propellant use, onboard storage limits.
- Persistence, and a FastAPI router for the new handlers.

## Tests

`python -m pytest simulation/engine_v4 -q` → 125 passed (93 existing + 32 in `test_mcas.py`),
run on 2026-11-15. The backend and FastAPI layers were not run.
