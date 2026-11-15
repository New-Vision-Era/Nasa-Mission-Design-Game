# Space Mission Design Game — backend

NASA Space Apps Challenge 2026. Read `AI_CONTEXT.md` first.

## Run it

Python 3.10 or newer.

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m backend.app.check_data                     # validate data/ (no server needed)
python -m pytest -q                                  # all tests
uvicorn backend.app.main:create_app --factory --reload --port 8000
```

Interactive API docs: http://localhost:8000/docs

Run every command from the repository root.

## Layout

| Folder | Owner | What it is |
| --- | --- | --- |
| `backend/` | Pair 3 | FastAPI app: endpoints, accounts, storage |
| `simulation/` | Person 2 | Pure engine. `engine.py` is **a placeholder model**; `engine_v4/` is the real-data engine. `models.py` is shared |
| `data/` | Person 1 | Scenarios, components, events, sources. **Currently mock values** |
| `data/fixtures/` | Pair 3 | Example requests and responses for the frontend mocks |
| `scripts/` | Pair 3 | `make_fixtures.py` regenerates the fixtures |

## API (all under `/api/v1`)

| Method and path | Login | Purpose |
| --- | --- | --- |
| `GET /health` | no | Liveness, catalog version, `data_status` |
| `GET /scenarios` | no | Scenarios with briefing, objectives, budget |
| `GET /catalog?scenario_id=` | no | Components grouped by category |
| `POST /evaluate` | no | Design in; resources, constraints, `launchable` out |
| `POST /auth/register` | no | Create an account; returns a bearer token |
| `POST /auth/login` | no | Returns a bearer token |
| `POST /auth/logout` | yes | Ends this session |
| `GET /auth/me` | yes | The logged-in player |
| `POST /missions` | yes | Save a design |
| `GET /missions` | yes | My saved designs |
| `GET`, `PUT`, `DELETE /missions/{id}` | yes | Load, update, delete one |
| `GET /missions/{id}/runs` | yes | Past runs of one saved design |
| `POST /runs` | optional | Launch. Logged in: saved to history. Guest: not listed anywhere |
| `GET /runs` | yes | My mission history, newest first |
| `GET /runs/{id}` | owner | One run in full: design flown, log, debrief |
| `POST /runs/{id}/decisions` | owner | Answer the pending event |
| `GET /simulation/catalog` | no | Real component catalog (`data/equipment_v4.json`) |
| `GET /simulation/scenarios` | no | Real-data scenarios and their gameplay parameters |
| `POST /simulation/run` | no | Real-data engine: constraints, score, mission, debrief |
| `POST /simulation/recommend` | no | Alternative designs (Pareto filter) |
| `GET /simulation/testbench` | no | Developer test page for the real-data engine |

The `/simulation/*` routes use the real-data engine in `simulation/engine_v4/`
(see `frontend/ENGINE_V4_INTEGRATION.md`). Saved missions, runs and history
still use the placeholder engine and mock data.

Send the token as `Authorization: Bearer <token>`.

Errors always look like `{"error": {"code": "...", "message": "...", "field": "..."}}`.

## Environment variables

| Name | Default | Meaning |
| --- | --- | --- |
| `DATABASE_PATH` | `space_mission.db` | SQLite file. Delete it if the schema changes |
| `DATA_DIR` | `./data` | Catalog folder |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated list |
| `SESSION_TTL_HOURS` | `168` | Login lifetime |
| `FRONTEND_DIST` | unset | Folder with the built frontend, served at `/` |

## For Person 1 (data)

Edit the JSON files in `data/`. Every number needs a `provenance` entry
(`published` + `source_id`, `estimate`, or `gameplay`). Run
`python -m backend.app.check_data` to see any mistake by file and field.
When the values are real, set `data_status` to `reviewed` in `data/catalog_meta.json`.

## For Person 2 (simulation)

Replace the bodies of the four functions in `simulation/engine.py`. Keep their
signatures and keep them pure. `resources`, `telemetry` and `score` are open
maps: add entries freely. `backend/app/services/engine_adapter.py` is the only
backend file that calls your code.

## Known limits

- The simulation model and all catalog numbers are placeholders.
- Accounts are username + password with no rate limiting, password reset or
  email. Fine for a demo; serve over HTTPS when hosted.
