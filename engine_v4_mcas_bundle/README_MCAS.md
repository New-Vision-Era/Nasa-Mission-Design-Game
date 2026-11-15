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
| `mission/operations.py` | `simulate_mission` flew every period in one loop | `simulate_mission` runs through MCAS with the four original events and default responses. `build_mission` builds the result from an MCAS run |
| `configuration.py` | `Scenario(id, name, briefing, params)` | `Scenario.mission_type` added (default `earth_observation`) |
| `api.py` | run, recommend, catalog handlers | Four handlers added: evaluate, start, decision, debrief |
| `evaluation.py`, `constraints/`, `scoring.py`, `performance.py`, `results.py`, `engine.py` | | Not touched |

`run_simulation()` returns the same result as before. This was checked two ways: the 93 existing
tests pass, and the original `simulate_mission` was compared with the new one on 5,440 runs
(34 designs x 4 parameter sets x 40 seeds) with byte-identical JSON.

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

## Needs team approval

1. **One-call and step-by-step results can differ.** `run_simulation()` keeps the original four
   events only. The step-by-step run also applies `data_backlog` choices and `pointing_instability`
   (which lowers observation even with the default response). Decide whether `run_simulation()`
   should use the full MVP scope; that would change scores for designs with a pointing warning.
2. Adding operational availability to the reliability category.
3. The five gameplay rules above.
4. Wiring into the backend: the backend's four functions take `Design`, `Scenario`, `Catalog` and
   `RunState` objects; these take a v4 configuration dict and a JSON state. `engine_adapter.py`
   needs a translation, and `pending_event {event_id, options[]}` maps to
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
