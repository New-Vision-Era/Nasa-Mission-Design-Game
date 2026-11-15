# AI_CONTEXT.md update: simulation engine v4 (2026-11-15)

Merge these blocks into `AI_CONTEXT.md` in the repository, in the sections named. Nothing here marks a
proposed feature as implemented.

## Section 5, replace the "CURRENT STATE" paragraph with

**CURRENT STATE:** two data sets and two engines exist side by side.

- `data/components/*.json` with `simulation/engine.py` is still the mock placeholder
  (`data_status: mock`). Do not present it as real.
- `data/equipment_v4.json` with `simulation/engine_v4/` uses real, sourced research data. It is a
  simplified game model, not a high-fidelity simulation. Its scenario file
  (`data/scenarios_v4/earth_observation_v4.json`) contains only requirements and gameplay assumptions.
- `equipment_v4.json` is not in the `data/components/*.json` per-field provenance format. The v4 engine
  reads it through one loader (`simulation/engine_v4/data_loader.py`).

## Section 7, add under "Actual repository structure"

``` text
simulation/engine_v4/           # real-data MVP engine (does not touch models.py or engine.py)
├── data_loader.py              # loads and indexes equipment_v4.json; null stays None
├── configuration.py            # MissionConfig, ScenarioParams, selection rules
├── results.py                  # ConstraintResult, PASS/FAIL/NOT_EVALUATED/WARNING, feasibility
├── evaluation.py               # runs every check
├── constraints/                # mass, volume, power, communications, orbit, pointing, propulsion, launch
├── mission/                    # performance (science rules), scoring, events, operations
├── optimizer/recommend.py      # bounded candidates + Pareto filter
├── engine.py                   # run_simulation(config, scenario_parameters, seed)
├── api.py                      # framework-free request handlers
└── tests/test_engine_v4.py
data/equipment_v4.json
data/scenarios_v4/earth_observation_v4.json
examples/example_mission.json, example_mission_with_assumptions.json
backend_integration/simulation_v4_router.py   # FastAPI wrapper, NOT yet executed
```

The v4 engine is not yet behind the four-function interface (`evaluate_design`, `start_run`,
`apply_decision`, `build_debrief`). It runs a whole mission in one call and has no player decisions
during operations.

## Section 8, add

### v4 simulation endpoints (handlers implemented and tested; FastAPI router written, not executed)

| Method and path | Purpose |
| --- | --- |
| `POST /simulation/run` | `{configuration, scenario_parameters?, seed?}` in; feasibility, constraints, score, mission, debrief out |
| `POST /simulation/recommend` | Same body; a few Pareto alternatives |
| `GET /simulation/catalog` | The v4 catalog with all original fields |

v4 configuration differs from the mock `Design`: flat (no `spacecraft` object),
`communication_system_ids` is a list, and `power` is an object
`{mode, solar_array_ids, battery_ids, eps_id}` with `mode` =
`platform_payload_budget` (default) or `player_built_power_system`.

v4 constraint statuses are upper-case `PASS`, `FAIL`, `NOT_EVALUATED`, `WARNING`. Overall feasibility is
`FEASIBLE`, `INFEASIBLE` or `CONDITIONAL` (no hard failure, but a hard constraint could not be
evaluated). Outcomes are `SUCCESS`, `PARTIAL_SUCCESS`, `FAILURE`. Request and response examples are in
`README_ENGINE_V4.md`.

## Section 13

**Status (2026-11-15):** real-data engine v4 written and tested standalone. Not yet wired into the
running backend. Frontend not started in this repository.

### Implemented (add)

- v4 loader for all 8 categories (3 platforms, 21 instruments, 17 power, 8 communications, 9 propulsion,
  7 ADCS, 5 orbits, 7 launch vehicles).
- Constraints: payload mass, payload volume, power Mode A and Mode B, command uplink, ground-station
  compatibility, downlink capacity, data balance, pointing, delta-v and burn time, launcher orbit support,
  launch mass, budget.
- Score out of 100 (science 35, objectives 25, reliability 20, efficiency 20; weights in the scenario).
- Six-stage deterministic mission with four seeded gameplay events.
- Candidate recommendation with a Pareto filter.

### Test status (add)

- **Run and passing:** 93 tests in `simulation/engine_v4/tests/test_engine_v4.py`
  (`python -m pytest simulation/engine_v4 -q`), including the request handlers and both example missions.
- **Written but NOT run:** `backend_integration/simulation_v4_router.py` (FastAPI was not installed where
  it was written; it compiles).

### Not implemented (add)

- v4 engine behind the four-function interface, saved runs and history for v4 results.
- Player decisions during v4 operations.
- Onboard storage limits, real reliability data, orbital lifetime, rocket-equation delta-v.

### Decision log (add rows)

| Date/time | Decision or change | Reason | Affected areas |
| --- | --- | --- | --- |
| 2026-11-15 | Real-data engine added as `simulation/engine_v4/`, beside the placeholder | Avoid overwriting shared `models.py` and `engine.py` before the team agrees the v4 contract | Simulation, backend |
| 2026-11-15 | Default power mode is `platform_payload_budget`; `player_built_power_system` is available per design | Power ownership of GSAT platforms is unknown; the mode is explicit, never silent | Simulation, game rules |
| 2026-11-15 | A hard constraint that cannot be evaluated makes the design `CONDITIONAL`, never a pass | Unknown must not count as zero or as success | Simulation, frontend |
| 2026-11-15 | Total spacecraft mass needs `bus_mass_kg_assumption` in the scenario; it ships as `null` | Bus mass is unpublished; without it launch mass, rideshare price and delta-v are `NOT_EVALUATED` | Scenarios, game rules |
| 2026-11-15 | Budget check covers platform plus launch only | Almost all component prices are unpublished and are not counted as zero | Scoring, scenarios |

### Needs team approval

1. Whether to set a gameplay bus mass (otherwise every design is `CONDITIONAL`).
2. Whether `CONDITIONAL` designs may launch (the v4 engine flies them and flags it; the current backend
   rule only blocks failed hard constraints).
3. Counting subsystems against platform payload mass and power.
4. Volume checked for instruments only.
5. Which contract the frontend builds against: the mock `Design` or the v4 configuration.

### Next actions (replace item 3)

3. Pair 3 with Person 2: install FastAPI, mount `simulation_v4_router.py` or call
   `simulation.engine_v4.api.handle_run_request` from `engine_adapter.py`, and run it once.
