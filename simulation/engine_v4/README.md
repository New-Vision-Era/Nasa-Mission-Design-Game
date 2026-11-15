# Simulation engine v4 (MVP)

A small, deterministic engineering engine on the real `equipment_v4.json` dataset. It is a simplified
game model, not a high-fidelity simulator.

## Install into the repository

Copy these into the repository root (nothing existing is overwritten):

| Path | What |
| --- | --- |
| `simulation/engine_v4/` | The engine package and its tests |
| `data/equipment_v4.json` | Canonical dataset (unchanged copy) |
| `data/scenarios_v4/earth_observation_v4.json` | Scenario: requirements and gameplay assumptions |
| `examples/*.json` | Example request bodies |
| `backend_integration/simulation_v4_router.py` | FastAPI wrapper, to copy to `backend/app/api/` (not yet executed) |

`simulation/__init__.py` in this bundle is an empty file; keep yours if it exists.
Dependencies: `pydantic` v2 and `pytest`, both already in the project.

## Run

```bash
python -m pytest simulation/engine_v4 -q                                   # tests
python -m simulation.engine_v4 simulation/engine_v4/examples/example_mission.json               # readable debrief
python -m simulation.engine_v4 simulation/engine_v4/examples/example_mission.json --full        # full JSON result
python -m simulation.engine_v4 simulation/engine_v4/examples/example_mission.json --recommend   # Pareto alternatives
```

Test page (standard library only, listens on 127.0.0.1):

```bash
python -m simulation.engine_v4.devui                 # opens http://127.0.0.1:8765
python -m simulation.engine_v4.devui --port 9000 --no-browser
```

It has one-click presets for each failure mode, auto-runs on every change, and shows constraints,
score reasons, mission stages, events, debrief and the raw JSON. It is a development tool, not the
game frontend.

From Python:

```python
from simulation.engine_v4 import run_simulation
result = run_simulation(configuration_dict, scenario_parameters=None, seed=42)
```

Dataset path order: `EQUIPMENT_V4_PATH` environment variable, else `data/equipment_v4.json`.

## API

`POST /api/v1/simulation/run`

```json
{
  "configuration": {
    "scenario_id": "earth_observation_v4",
    "platform_id": "gsat_50",
    "instrument_ids": ["hyperscape100"],
    "power": {"mode": "platform_payload_budget", "solar_array_ids": [], "battery_ids": [], "eps_id": null},
    "communication_system_ids": ["endurosat_s_band_transceiver", "endurosat_x_band_transmitter"],
    "adcs_system_id": "cubespace_cubeadcs_3axis_small_star",
    "propulsion_system_id": null,
    "orbit_id": "sso_500",
    "launch_vehicle_id": "rocket_lab_electron"
  },
  "scenario_parameters": {"bus_mass_kg_assumption": 40},
  "seed": 42
}
```

Response (top-level keys): `engine_version`, `dataset_id`, `seed`, `scenario`, `configuration`,
`feasibility {status, hard_failed, hard_not_evaluated, warnings}`, `resources`, `margins`, `constraints[]`,
`orbit`, `instruments_at_orbit[]`, `power`, `propulsion`, `performance`, `score`, `mission`,
`explanations[]`, `assumptions[]`, `limitations[]`, `provenance`.

One constraint:

```json
{
  "id": "launch_mass", "category": "launch", "status": "NOT_EVALUATED", "severity": "hard",
  "title": "Launch mass capacity",
  "message": "The launcher has a published capacity of 200 kg to SSO 500 km, but total spacecraft launch mass is not known. ...",
  "actual_value": null, "limit_value": 200, "unit": "kg",
  "affected_component_ids": ["rocket_lab_electron"], "value_kind": "published",
  "source_urls": ["..."], "assumptions": ["..."], "related_step": "launch_vehicle"
}
```

Also: `POST /api/v1/simulation/recommend` (same body) and `GET /api/v1/simulation/catalog`.

Errors use the backend's shape: `{"error": {"code", "message", "field", "details"}}` with
`422 invalid_request`, `422 unknown_component`, `404 not_found`, `500 internal_error`.

The handlers live in `simulation/engine_v4/api.py` and need no web framework. To expose them through the
existing design, call `handle_run_request` from `backend/app/services/engine_adapter.py`, or mount the router.

## Rules the engine follows

- `null` is unknown, never zero. A check that needs an unknown value returns `NOT_EVALUATED`, unless the
  known part alone already exceeds the limit, in which case it is `FAIL`.
- `FEASIBLE`: every hard constraint passes. `INFEASIBLE`: any hard constraint fails. `CONDITIONAL`: none
  fails but at least one hard constraint could not be evaluated.
- Payload mass is not spacecraft mass. Total mass, launch-mass fit, rideshare price and delta-v need
  `bus_mass_kg_assumption`, a labelled gameplay value. It is `null` in the shipped scenario.
- Launch capacity points apply only to their own orbit type and altitude.
- Power mode is explicit. Mode A never adds solar arrays to the budget; Mode B never adds the platform
  figure to generation.
- ADCS figures are compared with a hard requirement only for `upper_bound` and `per_axis_worst`.

## Value kinds per calculation

| Calculation | Inputs |
| --- | --- |
| Payload mass, single-item volume fit, launcher orbit list, capacity points, platform and launcher prices | Published |
| Orbit figures, GSD and swath at orbit, coverage rate, pointing offset, burn time | Derived |
| Power demand | Published powers, gameplay duty cycles, upper bounds where standby is unknown |
| Downlink capacity | Published rate, derived pass length, gameplay pass count and availability |
| Combined volume fit, total mass, delta-v, rideshare price, Mode B generation and battery | Depend on a gameplay assumption |
| Science rules, score weights, events, outcome thresholds | Gameplay |

## Decisions the team should confirm

1. Selected subsystems count against the platform payload mass and power (conservative; ownership unknown).
2. Volume is checked for instruments only (`volume_scope`); most subsystem dimensions are unpublished.
3. The budget covers platform plus launch; unpriced components are listed, not costed.
4. Whether to set `bus_mass_kg_assumption` in the scenario. Without it every design is `CONDITIONAL`.
5. Rideshare has no published mass cap, so its launch-mass check stays `NOT_EVALUATED` unless
   `rideshare_mass_cap_kg_assumption` is set.
