# Real-data simulation engine: frontend integration

The engine in `simulation/engine_v4/` runs on the researched dataset `data/equipment_v4.json`.
It is exposed by the backend next to the existing routes. Nothing existing changed: the mock
Earth-observation API and the Mars rover API work as before.

## Endpoints (under `/api/v1/simulation`)

| Method and path | Purpose |
| --- | --- |
| `GET /catalog` | Real components by category, with every original field, sources and caveats |
| `GET /scenarios` | Scenario briefing and default parameters (gameplay assumptions) |
| `POST /run` | Configuration in; feasibility, constraints, score, mission and debrief out |
| `POST /recommend` | Same body; up to five non-dominated alternative designs |
| `POST /runs` | Launch and store. Body adds optional `name`. `201` with `{run_id, name, created_at, scenario_parameters, result}` |
| `GET /runs` | Login required. The player's stored runs, newest first |
| `GET /runs/{run_id}` | One stored run in full |
| `GET /testbench` | Developer test page (not the game UI) |

Stored runs follow the same rules as the existing `/runs` routes: send `Authorization: Bearer <token>`
to save to a player's history; a guest run has no owner and is readable by anyone holding its id;
another player's run answers `404`. A design that fails a hard constraint answers `409 not_launchable`
and the error carries the full `result`. A `CONDITIONAL` design launches and is flagged.
Each history row records `uses_parameter_overrides`, so runs that changed scenario parameters
(for example a larger budget) can be told apart from runs on the scenario's own values.

## Try it

From the repository root:

```bash
pip install -r requirements.txt
uvicorn backend.app.main:create_app --factory --reload --port 8000
```

Open http://127.0.0.1:8000/api/v1/simulation/testbench. It has one-click presets for each
behaviour and shows the full response. Swagger is at http://127.0.0.1:8000/docs.

## Use it from a page

```html
<script src="engine-v4-api.js"></script>
<script>
  const result = await EngineV4API.run({
    scenario_id: "earth_observation_v4",
    platform_id: "gsat_50",
    instrument_ids: ["hyperscape100"],
    power: {mode: "platform_payload_budget", solar_array_ids: [], battery_ids: [], eps_id: null},
    communication_system_ids: ["endurosat_s_band_transceiver", "endurosat_x_band_transmitter"],
    adcs_system_id: "cubespace_cubeadcs_3axis_small_star",
    propulsion_system_id: null,
    orbit_id: "sso_500",
    launch_vehicle_id: "rocket_lab_electron"
  }, {bus_mass_kg_assumption: 40}, 42);
</script>
```

Set `window.ENGINE_V4_API_BASE` before the script if the backend runs elsewhere.

## What a UI needs from the response

| Field | Use |
| --- | --- |
| `feasibility.status` | `FEASIBLE`, `INFEASIBLE` or `CONDITIONAL` |
| `constraints[]` | `status` (`PASS`, `FAIL`, `NOT_EVALUATED`, `WARNING`), `severity` (`hard`, `soft`), `title`, `message`, `actual_value`, `limit_value`, `unit`, `related_step`, `affected_component_ids`, `assumptions`, `source_urls` |
| `resources`, `margins` | Dashboard figures. A `null` value means unknown, never zero |
| `score` | `total` out of 100, `completeness`, `categories[]` with `points`, `weight`, `reasons[]` |
| `mission` | `outcome` (`SUCCESS`, `PARTIAL_SUCCESS`, `FAILURE`), `stages[]`, `events[]`, `objectives[]` |
| `explanations[]` | Debrief findings with `kind` and `related_step` |
| `assumptions[]`, `limitations[]`, `provenance` | What is gameplay, what is real, and where it came from |

Errors use the backend's shape: `{"error": {"code", "message", "field", "details"}}`.

## Not integrated yet

- Saved designs (`/missions`) still use the mock `Design`; there is no saved-design slot for a v4
  configuration yet. Stored v4 runs keep the configuration that was flown.
- v4 runs are listed by `GET /simulation/runs`, separately from the placeholder runs in `GET /runs`.
- The v4 engine runs a whole mission in one call; there are no player decisions during operations.
- Every design is `CONDITIONAL` unless the scenario sets `bus_mass_kg_assumption`, because the
  platform bus mass is not published.

More detail: `simulation/engine_v4/README.md`.
