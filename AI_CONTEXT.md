# Space Mission Design Game --- Project Context

> **Purpose:** This is the shared source of truth for AI assistants and
> human teammates working on this project during the NASA Space Apps
> Challenge 2026.
>
> **How to use:** Read this file before proposing architecture changes
> or editing code. Update it after every major project decision,
> integration milestone, or change in scope. Do not assume that an idea
> in this document has already been implemented.

------------------------------------------------------------------------

## 1. Project identity

**Project name:** Space Mission Design Game\
**Challenge:** NASA Space Apps Challenge 2026 --- Space Mission Design
Game\
**Team size:** 6 university students\
**Time constraint:** 30-hour hackathon\
**Product type:** Interactive educational game / simplified
space-mission engineering simulator

### Short description

An interactive game in which players take the role of a space mission
engineering team. They receive a mission objective, design a spacecraft,
choose scientific instruments and subsystems, select an orbit and launch
vehicle, validate their design against engineering constraints, simulate
the mission, respond to operational events, and receive an explainable
engineering debrief.

### Main goal

Build a complete, playable, scientifically grounded mission-design
experience that teaches players how engineering decisions affect mission
outcomes.

The project should make engineering trade-offs understandable and
engaging. It should not merely be a collection of forms or a decorative
3D scene.

------------------------------------------------------------------------

## 2. Challenge understanding and product requirements

The challenge asks teams to create an interactive game or simulation
that allows participants to design and manage a complete space mission
while learning engineering trade-offs.

The experience should cover, as appropriate to the available time:

-   Mission objectives and requirements.
-   Spacecraft architecture and scientific instruments.
-   Launch vehicles and orbit selection.
-   Mass, power, budget, data, communications, and mission lifetime
    constraints.
-   Mission simulation and explanation of outcomes.
-   Resource management, mission objectives, engineering decisions, and
    teamwork.
-   Optional extensions such as scenarios, difficulty levels, events, 3D
    visualization, reports, leaderboards, saving/sharing, and
    multiplayer.

**Important:** Treat this as our understanding of the challenge brief,
not as a replacement for the official challenge page. Check the official
challenge instructions for exact judging criteria and submission
requirements.

### Product principle

Every meaningful engineering choice should affect one or more other
systems.

Examples: - A more capable scientific instrument may improve scientific
value but increase mass, power demand, cost, and data generation. -
Larger solar panels may increase available power but add mass and
cost. - A higher-capacity communication system may improve data
transmission but consume more power and resources. - A selected orbit
may improve coverage for a particular objective while creating different
communication or mission-operation trade-offs. - A launch vehicle must
be compatible with the spacecraft mass and required destination/orbit.

Do not make choices cosmetic if they are presented as engineering
choices.

------------------------------------------------------------------------

## 3. Intended player experience

The game should feel like a journey through a space agency mission, not
like filling out disconnected forms.

### Main player journey

1.  **Mission Control / Welcome**
    -   Register or log in (a guest can still design and launch, but
        nothing is saved to a history).
    -   Start a new mission, continue a saved mission, review past
        missions, or enter a tutorial/training mode if implemented.
    -   Briefly establish the player's role as part of a mission
        engineering team.
2.  **Mission Briefing**
    -   Present a clear mission story and scientific objective.
    -   Explain what the mission is expected to accomplish.
3.  **Mission Requirements**
    -   Show the budget and relevant technical constraints.
    -   Explain units, limits, and what each requirement means.
4.  **Spacecraft Architecture**
    -   Choose a suitable spacecraft platform or architecture.
    -   Show how the choice affects available capacity, mass, and cost.
5.  **Scientific Instruments**
    -   Select instruments that serve the mission objective.
    -   Display their capabilities and engineering properties.
6.  **Subsystem Configuration**
    -   Configure power, communications, propulsion, and
        navigation/attitude control as relevant.
    -   Show the effects of each selection.
7.  **Orbit Selection**
    -   Choose an appropriate orbit.
    -   Explain relevant characteristics and mission implications.
8.  **Launch Vehicle Selection**
    -   Select a launch vehicle compatible with the spacecraft and
        mission profile.
9.  **Engineering Review**
    -   Show a live resource dashboard: mass, power, budget,
        data/communications, and other implemented constraints.
    -   Distinguish hard constraints from soft performance goals.
10. **Pre-launch Validation**
    -   Run checks and explain warnings or failures.
    -   Let players return to the relevant design step and revise their
        choices.
11. **Launch and Deployment**
    -   Show a short launch/deployment sequence if time allows.
    -   Keep animations connected to the actual mission state.
12. **Mission Operations**
    -   Simulate mission progress.
    -   Present understandable events and decisions if implemented.
    -   Events must have fair, explainable consequences.
13. **Mission Results / Debrief**
    -   Report objectives achieved, scientific results, resource use,
        reliability, and constraints.
    -   Explain why the mission succeeded, partially succeeded, or
        failed.
    -   Identify design decisions that contributed to the outcome.
14. **Improve and Replay**
    -   Let players revise their design and compare a new attempt with
        the previous result.
    -   Let logged-in players open their mission history and review any
        old mission in full (design flown, log, debrief).

### UX rules

-   Every screen should have a clear purpose and a clear next action.
-   Explain technical terms in accessible language.
-   Show live consequences when the player changes a component.
-   Do not overwhelm beginners with all technical details at once; use
    concise summaries with optional explanations.
-   Preserve the player's configuration when navigating backwards.
-   Provide clear empty, loading, error, and validation states.
-   Make the core experience usable without multiplayer.
-   Do not let visual effects obscure important information.

------------------------------------------------------------------------

## 4. Engineering and scoring philosophy

### Use both constraints and final evaluation

Do not choose between a limited budget and a final score. Use both.

**Hard constraints** represent fundamental compatibility or feasibility
conditions. Examples may include: - Launch vehicle payload capacity. -
Power availability for required operations. - Required subsystem
compatibility. - Essential mission capability.

A hard-constraint violation should normally prevent a standard mission
launch or clearly mark the run as an experimental/high-risk attempt,
depending on the chosen game rules.

**Current backend rule:** a design that is incomplete or fails a hard
constraint cannot launch (`409 not_launchable`). An "experimental
launch" mode is not implemented.

**Soft goals** affect the quality of the design rather than
automatically preventing launch. Examples: - Budget efficiency. -
Scientific value beyond the minimum objective. - Mass margin. -
Communication efficiency. - Reliability margin. - Mission lifetime
margin.

The game should explain the distinction.

### Scoring

Use a transparent score, potentially out of 100, with separate
categories such as: - Scientific achievement. - Mission objective
completion. - Engineering reliability. - Resource efficiency. -
Communication/data performance.

A possible starting point for discussion (not an official NASA formula):

`Total score = 0.35 × science + 0.25 × reliability + 0.20 × efficiency + 0.20 × objectives`

Each category is normalized to 0--100. Adjust weights through
playtesting. Keep fundamental feasibility checks separate so a
physically incompatible design cannot receive a misleadingly high
success rating.

The weights live in each scenario file (`scoring_weights`), not in
backend code.

**Do not reward spending as little as possible at the expense of the
mission objective.** The goal is good engineering under constraints, not
simply the cheapest design.

### Debrief requirements

The final screen should do more than display a number. It should
explain: - What the mission achieved. - Which requirements were met or
missed. - Which constraints were close to their limits or violated. -
What design decisions had the largest effects. - What the player could
change in a second attempt.

------------------------------------------------------------------------

## 5. Scientific integrity and assumptions

Scientific credibility is a major differentiator.

### Rules for scientific data

1.  Prefer NASA technical documentation, mission documentation, agency
    publications, and other authoritative technical sources.
2.  Record a source for every important real-world value.
3.  Record units explicitly (kg, W, Wh, Mbps, \$, km, days, etc.).
4.  Distinguish measured/published values from estimates and gameplay
    abstractions.
5.  Do not invent values and present them as real.
6.  Do not claim a simplified model is an exact real-world physics
    simulation.
7.  Document assumptions and limitations in the UI or project
    documentation where appropriate.
8.  If a value is unknown, mark it as an estimate or leave it
    configurable rather than silently fabricating precision.
9.  Check unit conversions and calculation boundaries with tests.

### How the code enforces these rules

-   Every numeric field of a component in `data/components/*.json` must
    have a `provenance` entry with `kind` = `published` (needs a
    `source_id` present in `data/sources.json`), `estimate`, or
    `gameplay`. The catalog loader refuses to start otherwise.
-   `data/catalog_meta.json` carries `data_status`: `mock` or
    `reviewed`. The API returns it with every catalog response so the UI
    can show a placeholder-data banner.

**CURRENT STATE: two data sets and two engines exist side by side.**

-   `data/components/*.json` with `simulation/engine.py` is still the
    mock placeholder (`kind: gameplay`, `data_status: mock`). None of it
    is real spacecraft data. Do not present it as real. Saved missions,
    runs and history use this one.
-   `data/equipment_v4.json` with `simulation/engine_v4/` uses real,
    sourced research data (3 platforms, 21 instruments, 17 power, 8
    communication, 9 propulsion, 7 ADCS, 5 orbits, 7 launch vehicles).
    It is a simplified game model, not a high-fidelity simulation. Its
    scenario file `data/scenarios_v4/earth_observation_v4.json` holds
    only requirements and gameplay assumptions.
-   `equipment_v4.json` is not in the `data/components/*.json`
    per-field provenance format. The v4 engine reads it through one
    loader, `simulation/engine_v4/data_loader.py`. `null` means unknown,
    never zero.

### Appropriate scope

A simplified, transparent model is better than an ambitious but
inaccurate physics engine.

For the hackathon MVP, focus on consistent and explainable models for
the constraints actually implemented. Do not attempt high-fidelity
orbital mechanics unless the team has enough time and can validate the
model.

------------------------------------------------------------------------

## 6. Team structure --- three pairs

The team has six members working in three pairs. Names can be added by
the team.

### Pair 1 --- Science and Simulation

**Person 1: Space Science and Research** - Research mission objectives,
spacecraft components, instruments, orbits, launch vehicles, and
relevant technical values. - Collect and document trustworthy sources. -
Provide units, assumptions, and concise explanations. - Supply
structured data to the simulation developer. - Work on research
independently while the calculation engine uses clearly marked mock
data.

**Person 2: Simulation and Game Mechanics** - Implement resource
calculations and constraints. - Implement mission scoring and outcome
evaluation. - Implement mission state and event consequences where
feasible. - Write unit tests and edge-case tests. - Keep calculations
independent from UI rendering.

### Pair 2 --- Frontend and Visualization

**Person 3: Frontend Developer** - Build the player journey and
application screens. - Implement mission briefing, configuration,
dashboards, validation, operations, and debrief UI. - Integrate API
calls. - Handle application state, loading, error, and validation
states.

**Person 4: Visualization and UI/UX** - Build spacecraft, Earth, orbit,
and mission visualizations. - Implement meaningful animations and visual
feedback. - Ensure selected components and mission state are reflected
in the visualization. - Help maintain a coherent, polished design
system.

### Pair 3 --- Backend and Integration

**Person 5: Backend Developer** - Build API endpoints and data
validation. - Manage mission configuration and results. - Connect
frontend requests to the simulation. - Build player accounts and
mission history.

**Person 6: Integration, Testing, Game Design, and Demo** - Define and
maintain integration contracts with the team. - Integrate working
modules frequently. - Test complete player journeys and edge cases. -
Design mission scenarios and difficulty. - Prepare deployment, demo
flow, README, and submission material. - Contribute from hour one; do
not wait until the end to begin integration.

### Team collaboration rules

-   Pairs are ownership groups, not isolated silos.
-   Everyone should understand the full player journey and help unblock
    other members.
-   Use mock data and agreed interfaces to avoid waiting for another
    pair.
-   Integrate small working changes frequently.
-   Hold short checkpoints roughly every 2--3 hours.
-   Keep decisions and task status visible in GitHub.

### Folder ownership (keeps merges clean)

| Folder | Owner | Notes |
| --- | --- | --- |
| `data/` | Person 1 | Scenarios, components, events, sources |
| `simulation/` | Person 2 | Engine. `simulation/models.py` is shared: change it by pull request reviewed by Person 2 and one of Pair 3 |
| `frontend/` | Pair 2 | Not created yet |
| `backend/`, `scripts/`, `data/fixtures/` | Pair 3 | API, accounts, storage, fixtures |

------------------------------------------------------------------------

## 7. Technical architecture

**Backend, simulation interface and data layout below are implemented
(see section 13 for what has been tested). The frontend stack is still a
proposal.**

### Stack

-   **Frontend (proposed):** React + TypeScript.
-   **Styling (proposed):** Tailwind CSS or a small consistent CSS
    design system.
-   **Backend (implemented):** Python 3.10+ and FastAPI, one process.
-   **Simulation (implemented as a placeholder):** pure Python package
    with deterministic functions and tests.
-   **Data models (implemented):** Pydantic v2, defined once in
    `simulation/models.py` and reused as API bodies.
-   **Persistence (implemented):** SQLite through the standard-library
    `sqlite3` module. No ORM, no migrations: delete the file if the
    schema changes.
-   **Accounts (implemented):** username + password. Passwords hashed
    with scrypt (standard library). Opaque bearer session tokens; only
    their SHA-256 hash is stored. No JWT and no auth library.
-   **3D visualization (proposed):** Three.js or React Three Fiber.
-   **Version control:** Git + GitHub.
-   **Quick file transfer:** LocalSend.

Backend dependencies are only `fastapi`, `uvicorn`, `pydantic`, and for
tests `pytest` and `httpx`. Do not add more without a clear need.

### Architecture principles

-   Keep UI, API, simulation logic, and scientific data separated.
-   `backend` imports `simulation`; `simulation` imports neither
    `backend` nor FastAPI.
-   `backend/app/services/engine_adapter.py` is the ONLY backend file
    that imports the engine. If the engine's functions change shape,
    change that file only.
-   The backend never computes or adjusts a score. It stores and returns
    what the engine produces.
-   Backend validates every id in a design before calling the engine.
-   An infeasible design is a normal `200` result from `/evaluate` with
    failed constraints. Only launching it is refused.
-   Scenarios, components, orbits, launch vehicles and events are
    read-only data files. There are no API endpoints to create them.
-   Run state and debrief are stored as whole JSON documents, so the
    tables do not change when the simulation tracks something new.
-   `resources`, `telemetry` and `score` are open name-to-number maps.
    The simulation can add entries with no backend change.
-   Frontend should use the fixtures in `data/fixtures/` as mocks until
    it calls the real API.
-   After the contract is agreed: fields may be added at any time;
    renaming or removing a field needs a team message and updated
    fixtures in the same pull request.
-   Do not share a live SQLite database file over a network folder.
    Access it through the backend.
-   Do not commit credentials, tokens, private keys, `.env` or `*.db`
    files.

### Actual repository structure (backend side)

``` text
space-mission-game/
├── AI_CONTEXT.md
├── README.md                     # how to run, endpoint table
├── requirements.txt
├── backend/
│   ├── app/
│   │   ├── main.py               # create_app(): routers, CORS, error handlers, static files
│   │   ├── config.py             # Settings from environment variables
│   │   ├── container.py          # builds catalog, database and services once
│   │   ├── deps.py               # FastAPI dependencies: container, current player
│   │   ├── errors.py             # ApiError -> {"error": {...}}
│   │   ├── schemas.py            # API-only bodies: accounts, missions, run views
│   │   ├── check_data.py         # python -m backend.app.check_data
│   │   ├── api/
│   │   │   ├── auth.py           # register, login, logout, me
│   │   │   ├── catalog.py        # health, scenarios, catalog
│   │   │   ├── evaluate.py       # POST /evaluate
│   │   │   ├── missions.py       # saved designs
│   │   │   └── runs.py           # launch, decisions, history
│   │   ├── services/
│   │   │   ├── catalog_loader.py     # read and validate data/
│   │   │   ├── design_validation.py  # ids exist and sit in the right slot
│   │   │   ├── engine_adapter.py     # only file that calls simulation.engine
│   │   │   ├── auth_service.py
│   │   │   ├── mission_service.py
│   │   │   └── run_service.py
│   │   └── storage/
│   │       └── db.py             # SQLite schema and connection
│   └── tests/
│       ├── test_services.py      # needs only pydantic + pytest
│       └── test_api.py           # HTTP tests; needs fastapi + httpx
├── simulation/
│   ├── models.py                 # SHARED: every field name and unit
│   ├── engine.py                 # the four functions (PLACEHOLDER model)
│   └── tests/test_engine.py
├── data/
│   ├── catalog_meta.json         # catalog_version, data_status
│   ├── sources.json
│   ├── scenarios/earth_observation_01.json
│   ├── components/*.json         # one file per category
│   ├── events/events.json
│   └── fixtures/*.json           # example design, evaluations, run states
└── scripts/
    └── make_fixtures.py          # regenerate fixtures from real code
```

`frontend/` and `docs/` do not exist yet.

### Database tables

| Table | Holds |
| --- | --- |
| `users` | id, username (unique, lower-case), password hash, salt, created_at |
| `sessions` | token hash, user id, created_at, expires_at (7 days by default) |
| `missions` | A saved design owned by one player: name, scenario id, design JSON, timestamps |
| `runs` | One launched mission: owner (NULL for a guest), optional mission id, seed, catalog version, status, full run state JSON (includes the design flown), debrief JSON, outcome, total score, timestamps |
| `simulation_runs` | One launched real-data (engine v4) mission, always complete: owner (NULL for a guest), optional name, scenario id, dataset id, engine version, seed, feasibility, outcome, total score, whether scenario parameters were overridden, configuration JSON, override JSON, full result JSON, created_at |

### Real-data engine (`simulation/engine_v4/`, implemented)

``` text
simulation/engine_v4/
├── data_loader.py        # loads and indexes equipment_v4.json; null stays None
├── configuration.py      # MissionConfig, ScenarioParams, selection rules
├── results.py            # ConstraintResult, statuses, overall feasibility
├── evaluation.py         # runs every engineering check
├── constraints/          # mass, volume, power, communications, orbit, pointing, propulsion, launch
├── mission/              # performance (science rules), scoring, events, operations
├── optimizer/recommend.py# bounded candidates + Pareto filter
├── engine.py             # run_simulation(config, scenario_parameters, seed)
├── api.py                # framework-free request handlers
├── devui.py, devui.html  # developer test page
├── examples/             # example request bodies
└── tests/test_engine_v4.py
backend/app/api/simulation_v4.py      # thin router, registered in main.py
backend/tests/test_simulation_v4_api.py
frontend/engine-v4-api.js             # window.EngineV4API bridge
frontend/ENGINE_V4_INTEGRATION.md
data/equipment_v4.json, data/scenarios_v4/
```

It is additive, like the Mars rover API: no existing route, model or
existing table changed. It is NOT behind the four-function interface
below: it runs a whole mission in one call and has no player decisions
during operations. Its launched runs are stored in their own table,
`simulation_runs`, through
`backend/app/services/simulation_v4_service.py` (the only backend file
that calls the v4 engine).

### Simulation engine interface

The backend calls exactly these four pure functions in
`simulation/engine.py`:

``` python
def evaluate_design(design: Design, scenario: Scenario, catalog: Catalog) -> Evaluation
def start_run(design: Design, scenario: Scenario, catalog: Catalog, seed: int) -> RunState
def apply_decision(state: RunState, decision: Decision, scenario: Scenario, catalog: Catalog) -> RunState
def build_debrief(state: RunState, scenario: Scenario, catalog: Catalog) -> Debrief
```

`start_run` and `apply_decision` advance the mission to the next event
that needs the player, or to the end. Randomness comes only from the
run's seed, so a run can be replayed exactly.

------------------------------------------------------------------------

## 8. API and data contracts

All routes are under `/api/v1`. The live schema is at `/docs` when the
server runs. Working examples of every body are in `data/fixtures/`.

### Endpoints (implemented)

| Method and path | Login | Purpose |
| --- | --- | --- |
| `GET /health` | no | Liveness, catalog version, `data_status` |
| `GET /scenarios` | no | Scenarios with briefing, objectives, budget |
| `GET /catalog?scenario_id=` | no | Components grouped by category, with provenance |
| `POST /evaluate` | no | Design in; resources, constraints, `launchable` out. Accepts partial designs |
| `POST /auth/register` | no | Body `{username, password}`; returns a bearer token |
| `POST /auth/login` | no | Same body; returns a bearer token |
| `POST /auth/logout` | yes | Ends this session |
| `GET /auth/me` | yes | The logged-in player |
| `POST /missions` | yes | Save a design: `{name, design}` |
| `GET /missions` | yes | The player's saved designs |
| `GET`, `PUT`, `DELETE /missions/{mission_id}` | yes | Load, update, delete one |
| `GET /missions/{mission_id}/runs` | yes | Past runs of one saved design |
| `POST /runs` | optional | Launch: `{design, mission_id?, seed?}` |
| `GET /runs` | yes | The player's mission history, newest first |
| `GET /runs/{run_id}` | owner | One run in full: design flown, log, debrief |
| `POST /runs/{run_id}/decisions` | owner | Answer the pending event: `{event_id, option_id}` |

Authentication: send `Authorization: Bearer <token>`.

Access rules:

-   Username: 3--32 characters, letters, digits and underscore.
    Password: 8--128 characters.
-   Missions and history belong to one player. Another player's mission
    or run answers `404`, never `403`.
-   A guest may call `POST /runs`. A guest run has no owner, appears in
    no history, and can be read by anyone holding its id.
-   Deleting a saved mission keeps its past runs in the history.

### Design (request body)

``` json
{
  "scenario_id": "earth_observation_01",
  "spacecraft": {
    "platform_id": "small_platform",
    "instrument_ids": ["optical_camera"],
    "power_system_id": "solar_array_small",
    "communication_system_id": "x_band_high_gain",
    "propulsion_system_id": "cold_gas",
    "adcs_system_id": "reaction_wheels"
  },
  "orbit_id": "sun_synchronous",
  "launch_vehicle_id": "small_launcher"
}
```

Only `scenario_id` is required; every other field may be `null` or
missing while the player is still designing.

Changes from the first draft of this section, and why:

-   `budget_limit` and `objective_ids` were removed from the request.
    They come from the scenario, so a client cannot give itself a bigger
    budget.
-   `mission_id` became `scenario_id`. A mission id now means a saved
    design.
-   `mission_type` was dropped; the scenario carries that.
-   `adcs_system_id` was added for navigation and attitude control.

### Evaluation (response of `/evaluate`)

``` json
{
  "catalog_version": "0.1.0-mock",
  "complete": true,
  "launchable": false,
  "missing": [],
  "resources": {
    "total_mass_kg": 300.0,
    "power_required_w": 395.0,
    "power_available_w": 300.0,
    "cost_usd": 56500000.0,
    "budget_usd": 80000000.0
  },
  "constraints": [
    {
      "id": "power_balance",
      "severity": "hard",
      "status": "failed",
      "value": 395.0,
      "limit": 300.0,
      "unit": "W",
      "margin_fraction": -0.3167,
      "related_step": "power",
      "message": "The selected components need more power than the power system produces."
    }
  ]
}
```

-   `severity`: `hard` or `soft`. `status`: `passed`, `warning`,
    `failed`, or `not_evaluated` (an input is still missing).
-   `launchable` is true only when the design is complete and no hard
    constraint has failed.
-   `related_step` names the design screen that fixes the problem:
    `platform`, `instruments`, `power`, `communications`, `propulsion`,
    `adcs`, `orbit`, `launch_vehicle`, `budget`.
-   `resources` is an open map; treat unknown keys as displayable
    numbers.

### Run (response of `/runs` routes)

Fields: `run_id`, `mission_id`, `scenario_id`, `catalog_version`,
`created_at`, `completed_at`, `status` (`awaiting_decision` or
`completed`), `seed`, `design` (snapshot of what was flown),
`progress {step, total_steps, elapsed_days}`, `resources`, `telemetry`,
`pending_event {event_id, title, description, options[]}` or `null`,
`occurred_event_ids`, `log[] {step, message}`, and `debrief` (`null`
until completed).

`debrief`: `outcome` (`success`, `partial_success`, `failure`),
`score` (map that always contains `total`), `objectives[] {id,
achieved_fraction, message}`, `findings[] {kind, related_step, message,
suggestion}`.

History rows (`GET /runs`): `run_id`, `mission_id`, `mission_name`,
`scenario_id`, `status`, `outcome`, `score_total`, `created_at`,
`completed_at`.

### Errors

Every error has the same body:

``` json
{ "error": { "code": "unknown_component", "message": "No component with id 'xray_cam'.", "field": "spacecraft.instrument_ids[0]" } }
```

| HTTP | `code` | When |
| --- | --- | --- |
| 401 | `not_authenticated` | A login-only route was called without a token |
| 401 | `invalid_token` | The token is unknown or expired |
| 401 | `invalid_credentials` | Wrong username or password |
| 404 | `not_found` | Unknown scenario, mission or run (or not yours) |
| 409 | `username_taken` | Registration with an existing username |
| 409 | `not_launchable` | Launching an incomplete design or one failing a hard constraint; the error also carries `evaluation` |
| 409 | `no_pending_event` | A decision for a run that is complete, or already answered |
| 422 | `invalid_request` | The body does not match the schema |
| 422 | `unknown_component` | An id is not in the catalog, is in the wrong slot, or is not allowed in the scenario |
| 500 | `internal_error` | Anything unexpected; details only in the server log |

### Real-data simulation endpoints (implemented, under `/api/v1/simulation`)

| Method and path | Purpose |
| --- | --- |
| `GET /simulation/catalog` | The v4 catalog with all original fields, sources and caveats |
| `GET /simulation/scenarios` | Scenario briefing and default parameters (gameplay assumptions) |
| `POST /simulation/run` | `{configuration, scenario_parameters?, seed?}` in; feasibility, constraints, score, mission, debrief out |
| `POST /simulation/recommend` | Same body; up to five non-dominated alternatives |
| `POST /simulation/runs` | Launch and store: `{configuration, scenario_parameters?, seed?, name?}`. Login optional, same guest rules as `/runs`. `409 not_launchable` (with `result`) if a hard constraint fails |
| `GET /simulation/runs` | Login required. The player's stored real-data runs, newest first |
| `GET /simulation/runs/{run_id}` | Owner (or anyone for a guest run). `{run_id, name, created_at, status, uses_parameter_overrides, scenario_parameters, result}` |
| `GET /simulation/testbench` | Developer test page, not the game UI |

The v4 configuration differs from the mock `Design`: it is flat (no
`spacecraft` object), `communication_system_ids` is a list, and `power`
is `{mode, solar_array_ids, battery_ids, eps_id}` with `mode` =
`platform_payload_budget` (default) or `player_built_power_system`.

v4 constraint statuses are upper-case `PASS`, `FAIL`, `NOT_EVALUATED`,
`WARNING`. Overall feasibility is `FEASIBLE`, `INFEASIBLE` or
`CONDITIONAL` (no hard failure, but a hard constraint could not be
evaluated from real data). Outcomes are `SUCCESS`, `PARTIAL_SUCCESS`,
`FAILURE`. Full examples: `frontend/ENGINE_V4_INTEGRATION.md` and
`simulation/engine_v4/README.md`.

### Contract rules

-   Include units in field names or schema documentation.
-   Use consistent identifiers for components.
-   Define which fields are required and which are optional.
-   Define error response shapes.
-   Version or document breaking API changes.
-   Keep mock data aligned with the real schema: run
    `python -m scripts.make_fixtures` after changing models, engine or
    data, and commit the result.
-   Do not let frontend and backend independently invent incompatible
    field names.

------------------------------------------------------------------------

## 9. AI tools and how they should be used

AI tools are assistants, not sources of unquestioned truth. All AI
models must follow this file and the current repository.

### Planned AI roles

The team may use the following tools depending on availability and
competition rules:

-   **Claude Code --- primary coding agent:** inspect the repository,
    implement assigned modules, refactor carefully, run tests, and
    explain changes.
-   **ChatGPT --- architecture and problem-solving assistant:** help
    reason about system design, user experience, debugging, test plans,
    code review, and documentation.
-   **Gemini --- secondary reviewer/research assistant:** provide an
    independent explanation or review, and help explore technical
    topics. Verify scientific facts from primary sources.
-   **GitHub Copilot or another coding assistant --- optional
    autocomplete:** use only if it improves speed without introducing
    inconsistent patterns.

The team must confirm which tools are actually being used and update
this list. Do not assume every tool is available or permitted by the
event rules.

### AI coding rules

Before changing code, an AI assistant should:

1.  Read this file and the relevant README.
2.  Inspect the existing repository and identify the actual framework
    and conventions.
3.  State which files it plans to change.
4.  Work only on the assigned task.
5.  Preserve existing working functionality.
6.  Avoid broad rewrites unless explicitly requested.
7.  Avoid adding dependencies without explaining why.
8.  Use the agreed contracts and units.
9.  Add or update tests for logic changes.
10. Run relevant tests or checks when possible.
11. Report changed files, commands run, test results, assumptions, and
    remaining issues.
12. Never claim that code was tested if it was not run.

### Scientific research rules for AI

-   Ask for primary sources and direct citations.
-   Verify important values against the cited source.
-   Do not accept fabricated NASA references or unsupported numerical
    claims.
-   Keep a record of assumptions and simplified models.
-   Distinguish a proposed gameplay value from a real-world engineering
    specification.

### Reusable prompt for Claude Code and other coding agents

``` text
You are working on our NASA Space Apps Challenge 2026 project,
Space Mission Design Game.

First read AI_CONTEXT.md and README.md. Inspect the existing repository
before making changes.

Task:
[Describe one specific task.]

Rules:
- Follow the existing architecture and coding conventions.
- Modify only the files needed for this task.
- Do not rewrite unrelated working code.
- Do not invent scientific values or sources.
- Preserve agreed data contracts and units.
- Add or update tests for changed logic.
- If a requirement is ambiguous, state the assumption or ask before
  making a major architectural decision.
- Do not add dependencies without explaining the benefit.
- Run relevant checks and report their actual results.

Before implementation, briefly state:
1. What you found in the current code.
2. Your proposed approach.
3. Which files you expect to modify.

After implementation, report:
1. What changed.
2. Files created or modified.
3. Tests/checks run and their results.
4. Assumptions and limitations.
5. Any integration work required from another teammate.
```

------------------------------------------------------------------------

## 10. GitHub and collaboration workflow

GitHub is the single source of truth for code and project decisions.

-   Each person works on their own computer.
-   Use feature branches; avoid everyone committing directly to `main`.
-   Make small, frequent commits with descriptive messages.
-   Open pull requests for meaningful changes.
-   Review integration conflicts before merging.
-   Track tasks and bugs using GitHub Issues or Projects.
-   Use LocalSend for quick transfer of large files, screenshots, PDFs,
    and temporary assets.
-   If code arrives through LocalSend, integrate it into the repository
    and commit it to GitHub.
-   Never treat a LocalSend copy as the authoritative version of a
    source file.

Suggested branch names:

``` text
feature/mission-briefing
feature/spacecraft-designer
feature/orbit-visualization
simulation/resource-calculations
simulation/mission-scoring
backend/mission-api
integration/demo-flow
```

------------------------------------------------------------------------

## 11. Hackathon priorities and time management

The goal is a coherent end-to-end experience, not the maximum number of
features.

### MVP --- build first

1.  One complete mission scenario.
2.  Mission briefing and requirements.
3.  Component selection.
4.  Resource calculations for the implemented systems.
5.  Orbit and launch-vehicle selection, even if simplified.
6.  Constraint validation.
7.  A playable simulation/result flow.
8.  Final score and explanatory debrief.

### High-value improvements

-   Live resource dashboard.
-   Interactive spacecraft visualization.
-   Earth/orbit visualization.
-   Meaningful launch animation.
-   A small number of understandable mission events.
-   Design comparison and replay.
-   Player accounts and mission history (moved here from "optional" on
    2026-11-14; the backend side is built). The frontend needs login,
    register and history screens. Guests can still play, so the MVP flow
    does not depend on login.
-   Strong visual consistency and clear explanations.

### Optional only after MVP works

-   Multiplayer synchronization.
-   Many mission scenarios.
-   Complex account features (email, password reset, profiles).
-   Leaderboards.
-   Advanced orbital mechanics.
-   Elaborate 3D environments.
-   AI advisor inside the game.

### Suggested 30-hour schedule

  -----------------------------------------------------------------------
  Time                                Focus
  ----------------------------------- -----------------------------------
  Hours 0--1                          Agree on MVP, stack, contracts,
                                      repository, and ownership

  Hours 1--7                          Build independent modules using
                                      mock data; first demonstrations

  Hours 7--12                         Integrate the first end-to-end
                                      mission

  Hours 12--19                        Complete core mechanics, improve
                                      visualization, add one or two
                                      events

  Hours 19--23                        Full integration, testing, edge
                                      cases, deployment

  Hours 23--27                        Polish, demo scenario,
                                      documentation, presentation

  Hours 27--30                        Feature freeze, final regression
                                      test, submission
  -----------------------------------------------------------------------

Adapt the schedule to the actual remaining time. Freeze new features
before the final hours.

------------------------------------------------------------------------

## 12. Definition of done

A feature is not complete merely because a screen exists.

For each feature, check:

-   It works in the actual application.
-   It uses the agreed data contract.
-   It handles invalid or missing input.
-   Its calculations have tests where applicable.
-   Its units and assumptions are documented.
-   It has useful loading, success, and error states.
-   It does not break the main mission journey.
-   Another teammate can understand how to integrate or maintain it.

### MVP end-to-end acceptance test

A new player should be able to:

1.  Start the application.
2.  Select the Earth-observation mission.
3.  Read the objective and constraints.
4.  Select a spacecraft and at least one instrument.
5.  Configure the required subsystems.
6.  Select an orbit and launch vehicle.
7.  See updated mass, power, and budget.
8.  Receive clear feedback when a constraint is violated.
9.  Correct the design.
10. Run the mission simulation.
11. See the result and understand why it received its score.

If this flow works reliably, the team has a meaningful project to
demonstrate.

------------------------------------------------------------------------

## 13. Project status --- update this section continuously

**Status (2026-11-15):** Backend first version written. Real-data
engine v4 integrated into the backend as additive endpoints, including
stored runs and per-player history. Saved designs (`/missions`) and the
`/runs` routes still use the placeholder engine and mock data. No game UI
in this repository yet (only API bridge scripts in `frontend/`).

### Implemented

-   Catalog loading and validation, with `python -m backend.app.check_data`.
-   `/health`, `/scenarios`, `/catalog`, `/evaluate`.
-   Player accounts: register, login, logout, current player.
-   Saved missions: create, list, load, update, delete.
-   Runs: launch, answer events, read one run, mission history, runs per
    saved mission. Guest runs.
-   Placeholder simulation engine behind the four-function interface,
    with two mock events.
-   Mock catalog: 1 scenario, 18 components, 2 events.
-   Fixtures generated from the real code path.

-   Real-data engine v4: loader for all 8 categories; constraints for
    payload mass, payload volume, power (two explicit modes), command
    uplink, ground-station compatibility, downlink capacity, data
    balance, pointing, delta-v and burn time, launcher orbit support,
    launch mass and budget; score out of 100; six-stage deterministic
    mission with four seeded gameplay events; Pareto recommendations.
-   `/simulation/catalog`, `/simulation/scenarios`, `/simulation/run`,
    `/simulation/recommend`, `/simulation/testbench`.
-   Stored real-data runs: `POST /simulation/runs`,
    `GET /simulation/runs`, `GET /simulation/runs/{run_id}`, with the
    same ownership and guest rules as the placeholder runs.

### Test status (be honest about this)

-   **Engine v4, run and passing:** 96 tests in
    `simulation/engine_v4/tests/test_engine_v4.py`, including the
    framework-free request handlers.
-   **Engine v4 HTTP layer, run and passing in CI:**
    `backend/tests/test_simulation_v4_api.py` (13 tests through the real
    FastAPI app). FastAPI was not installed where it was written, so its
    first run was GitHub Actions on `feature/engine-v4-integration`:
    144 passed, none skipped (2026-11-15).
-   **Run and passing:** 19 tests covering the catalog loader, design
    validation, accounts, saved missions, runs, history, ownership
    rules, and the placeholder engine. These call the service layer
    directly.
-   **Written but NOT yet run:** `backend/tests/test_api.py` (4 HTTP
    tests) and therefore the FastAPI layer itself (`main.py`, `deps.py`,
    `api/*.py`). FastAPI was not installed where the code was written.
    These files compile, but the first `pip install -r requirements.txt`
    followed by `python -m pytest -q` is their first real run. Treat any
    failure there as expected first-run fixing, not as a regression.

### Not implemented

-   Frontend, 3D visualization.
-   Real scientific data and sources (Person 1).
-   Real simulation, scoring and events (Person 2).
-   "Experimental launch" of a design that fails a hard constraint.
-   Login rate limiting, password reset, email.
-   Deployment.

-   v4 engine behind the four-function interface. v4 runs and
    placeholder runs are stored and listed separately.
-   Saved designs (`/missions`) for a v4 configuration.
-   Player decisions during v4 operations.
-   Onboard storage limits, real reliability data, orbital lifetime,
    rocket-equation delta-v.

### Checklist

-   [ ] Final project name and tagline.
-   [x] Backend technology stack (section 7).
-   [ ] Frontend technology stack.
-   [ ] GitHub repository URL.
-   [ ] Team member names and pair assignments.
-   [x] Actual repository structure, backend side (section 7).
-   [x] Mission scenario selected for the MVP: Earth observation
    (`earth_observation_01`, mock content).
-   [ ] First agreed component dataset and sources.
-   [x] API request/response schemas (section 8) --- written by the
    backend pair; **needs confirmation from Pair 1 and Pair 2**.
-   [ ] Scoring formula and hard/soft constraints (placeholder only).
-   [ ] Known bugs and blockers.
-   [ ] Deployment/demo setup.

### Current decisions already agreed in principle

-   Six teammates organized into three pairs: Science & Simulation,
    Frontend & Visualization, Backend & Integration.
-   GitHub is the source of truth for code.
-   LocalSend is for quick direct file transfers.
-   Each teammate develops locally.
-   The product should have a constrained engineering design process and
    a final score with explanatory feedback.
-   A complete single-player mission takes priority over optional
    multiplayer.
-   Mock data should prevent one pair from waiting for another.
-   Scientific values and assumptions must be sourced and clearly
    identified.

### Decision log

Add a new entry whenever a major decision is made.

| Date/time | Decision or change | Reason | Affected areas |
| --- | --- | --- | --- |
| Hackathon start | Initial project direction documented | Establish shared context for all teammates and AI tools | Whole project |
| 2026-11-14 | Backend stack fixed: Python, FastAPI, Pydantic v2, SQLite via `sqlite3` | Matches the proposed default; smallest dependency set | Backend |
| 2026-11-14 | All formulas run on the server; the frontend calls `POST /evaluate` for the live dashboard | One engine and one set of tests; no second copy of the maths in TypeScript | Frontend, simulation |
| 2026-11-14 | Simulation reached only through four pure functions and one adapter file | Person 2 can change the engine without touching the backend | Simulation, backend |
| 2026-11-14 | Catalog is read-only JSON with provenance on every number; no API to create components, orbits or scenarios | Scientific data stays under review in pull requests | Data, backend |
| 2026-11-14 | Request contract changed: `budget_limit`, `objective_ids`, `mission_type` removed; `mission_id` renamed `scenario_id`; `adcs_system_id` added | Budget and objectives belong to the scenario; the journey includes attitude control | Frontend, backend |
| 2026-11-14 | A design failing a hard constraint cannot launch | Simplest fair rule; "experimental launch" can be added later | Game rules |
| 2026-11-14 | **Scope change:** player accounts and per-player mission history added. Supersedes "Accounts and complex persistence" being optional (section 11) and "add persistence only as needed" (section 6) | Team wants each player to review old missions | Backend, frontend, database |
| 2026-11-14 | Accounts use username + password with scrypt and opaque session tokens, standard library only | No extra dependency; no email collected | Backend |
| 2026-11-14 | Guests can still evaluate and launch; only saving and history need login | The MVP acceptance test must not depend on the login screens | Frontend, backend |
| 2026-11-14 | Storage is SQLite from the start; the earlier "in-memory first" plan was dropped | Accounts and history need durable storage; tests use an in-memory SQLite database | Backend |
| 2026-11-15 | Real-data engine added as `simulation/engine_v4/` with additive `/simulation/*` endpoints, beside the placeholder | Makes the real engine usable now without changing the shared `models.py`, `engine.py`, stored runs or the mock contract | Simulation, backend, frontend |
| 2026-11-15 | Default power mode is `platform_payload_budget`; `player_built_power_system` is selectable per design | Whether GSAT platforms include power hardware is unknown; the mode is explicit, never silent | Simulation, game rules |
| 2026-11-15 | A hard constraint that cannot be evaluated makes a design `CONDITIONAL`, never a pass | Unknown must not count as zero or as success | Simulation, frontend |
| 2026-11-15 | Total spacecraft mass needs `bus_mass_kg_assumption` in the scenario; it ships as `null` | Bus mass is unpublished; without it launch mass, rideshare price and delta-v are `NOT_EVALUATED` | Scenarios, game rules |
| 2026-11-15 | The v4 budget check covers platform plus launch only | Almost all component prices are unpublished and are not counted as zero | Scoring, scenarios |
| 2026-11-15 | v4 runs stored in a new `simulation_runs` table with their own routes, instead of reusing `runs` and `RunState` | The v4 result has a different shape and no pending decisions; a separate table leaves `models.py`, `RunState` and existing history untouched, and needs no database reset | Backend, database, frontend |
| 2026-11-15 | A v4 design that fails a hard constraint cannot launch (`409 not_launchable`); a `CONDITIONAL` design launches and is flagged | Same rule as the placeholder runs; whether `CONDITIONAL` may launch is still a team decision | Game rules |
| 2026-11-15 | Stored v4 runs accept scenario parameter overrides and record `uses_parameter_overrides` | A gameplay bus mass is currently only available as an override; the flag keeps such runs distinguishable in history. Remove overrides from `POST /simulation/runs` once the scenario values are agreed, so a client cannot give itself a bigger budget | Backend, game rules |

### Current blockers

-   FastAPI layer has never been executed (see Test status). Owner:
    Pair 3. Next action: install requirements and run the test suite.

### Next actions

1.  Pair 3: install, run `python -m pytest -q`, fix anything in the
    HTTP layer, push to GitHub.
2.  Whole team: confirm or correct the contract in section 8.
3.  Person 2: replace the placeholder bodies in `simulation/engine.py`.
4.  Person 1: replace the mock values in `data/` and fill
    `data/sources.json`.
5.  Pair 2: build against `data/fixtures/`, then the live API; add
    login, register and history screens.
6.  Decide where the demo runs.
7.  Whole team: decide the open v4 questions: set a gameplay bus mass
    or keep every design `CONDITIONAL`; may `CONDITIONAL` designs
    launch; count subsystems against platform payload mass and power;
    check volume for instruments only; which contract the new UI builds
    against (mock `Design` or v4 configuration).
8.  Whole team: once scenario values are agreed, stop accepting
    `scenario_parameters` on `POST /simulation/runs`.
9.  Pair 3: if the new UI adopts the v4 configuration, add saved designs
    for it and decide whether to merge the two history lists.

------------------------------------------------------------------------

## 14. Mandatory context-update protocol

This document must evolve with the project.

After every major change, the responsible teammate or AI assistant must
update this file in the same branch or pull request as the
implementation, where practical.

A **major change** includes: - A technology or architecture decision. -
A change to the mission journey or MVP scope. - A new or changed
API/data contract. - A new scientific model, constant, assumption, or
source. - A change to the scoring system or constraints. - Completion of
an important end-to-end feature. - A major bug fix or known
limitation. - A change in team ownership or integration
responsibilities.

When updating this document:

1.  Read the current version first.
2.  Preserve decisions that remain valid.
3.  Change only the relevant sections.
4.  Update the project status and decision log.
5.  Record what is implemented versus merely planned.
6.  Record important assumptions and unresolved questions.
7.  Never silently remove a decision; explain why it changed.
8.  Keep this file concise enough to remain useful, but detailed enough
    for a new AI assistant or teammate to understand the project.

### Prompt to update this file after a major change

``` text
Update AI_CONTEXT.md to reflect the changes made in this task.

First inspect the current file and the actual code changes.

- Preserve all still-valid decisions.
- Update only the relevant sections.
- Distinguish implemented features from planned features.
- Record new API contracts, scientific assumptions, units, and sources.
- Update project status, blockers, and the decision log.
- Do not claim that unimplemented functionality exists.
- Do not remove important context just to shorten the file.

At the end, summarize exactly what you updated and identify any
important project decisions that still need team approval.
```

------------------------------------------------------------------------

## 15. Instructions to every AI model

This project is a time-limited team hackathon. Optimize for a working,
integrated, understandable product.

**Your priorities, in order:**

1.  Preserve and understand the existing project.
2.  Help complete the end-to-end mission experience.
3.  Maintain scientific honesty and explainable calculations.
4.  Respect shared contracts and pair ownership.
5.  Keep changes small, testable, and easy to integrate.
6.  Communicate blockers and assumptions early.
7.  Update this context after major changes.

Do not independently redesign the product, change the stack, invent
science, or create a large feature that delays the playable MVP. When in
doubt, inspect the repository, explain the trade-off, and ask the team
before making a major decision.
