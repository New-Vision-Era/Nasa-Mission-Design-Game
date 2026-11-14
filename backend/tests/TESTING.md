# How to test the backend

There are three ways to test, from fastest to most thorough:

1. **Automated tests** (`pytest`): about 1 second, run them before every push.
2. **Swagger UI** in the browser: click through the API by hand, no tools needed.
3. **`curl` walkthrough**: the whole player journey from the command line, with the
   expected result of every step.

Run every command from the repository root (the folder that holds `README.md`).

> **First run warning.** The service layer has been tested, but the FastAPI route
> layer (`backend/app/main.py`, `deps.py`, `api/*.py`) has never been run.
> Expect to fix a few small errors the first time you run step 1. That is
> expected first-run work, not a regression.

---

## 0. Setup (once)

Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Check that it worked:

```bash
python -c "import fastapi, httpx, pydantic; print('ok')"
```

---

## 1. Automated tests

### Check the data files

```bash
python -m backend.app.check_data
```

Expected:

```text
OK: 18 components, 1 scenario(s), 2 event(s), 0 source(s). Version 0.1.0-mock, status 'mock'.
```

If a data file is wrong, it lists every problem with its file and field and exits with code 1.
Person 1 should run this after every change to `data/`.

### Run all tests

```bash
python -m pytest -q
```

Expected once FastAPI is installed: **23 passed**, 0 skipped.

| File | Tests | What it covers |
| --- | --- | --- |
| `simulation/tests/test_engine.py` | 4 | Placeholder engine: sums, limits, events, determinism |
| `backend/tests/test_services.py` | 15 | Catalog loading, validation, accounts, missions, runs, history, privacy |
| `backend/tests/test_api.py` | 4 | The HTTP layer: routes, status codes, error shapes, login |

If you see **19 passed, 1 skipped**, FastAPI or httpx is not installed in the
active environment; `test_api.py` was skipped. Go back to step 0.

### Useful variations

```bash
python -m pytest -q backend/tests/test_api.py     # only the HTTP tests
python -m pytest -q -k history                   # only tests with "history" in the name
python -m pytest -x                              # stop at the first failure
python -m pytest -q -vv                          # show each test name
```

### After changing models, engine or data

Regenerate the example files the frontend mocks use, then rerun the tests:

```bash
python -m scripts.make_fixtures
python -m pytest -q
```

Commit the changed files in `data/fixtures/` with your change. A test fails if
the fixtures no longer match the models.

---

## 2. Manual test in the browser (Swagger UI)

Start the server:

```bash
uvicorn backend.app.main:create_app --factory --reload --port 8000
```

Open **http://localhost:8000/docs**. Every endpoint is listed; click one, then
**Try it out**, fill the body, and **Execute**.

To call routes that need login:

1. Run `POST /api/v1/auth/register` with `{"username": "ada", "password": "correct horse"}`.
2. Copy the `token` from the response.
3. Click **Authorize** (top right), paste the token, click **Authorize**.
   Every request after that is sent as that player.

A ready-made design to paste into bodies is in `data/fixtures/design_example.json`.

The server writes to `space_mission.db` in the repository root. To start from
an empty database, stop the server and delete that file.

---

## 3. Full journey with `curl`

Use a bash shell (Linux, macOS, or Git Bash on Windows). The server must be
running as in section 2. Run the steps in order in **one terminal** so the
variables carry over.

To start from a clean database first, stop the server, delete
`space_mission.db`, and start it again.

```bash
API=http://localhost:8000/api/v1
DESIGN=$(cat data/fixtures/design_example.json)
json() { python -c "import sys,json; d=json.load(sys.stdin); print(eval(sys.argv[1]))" "$1"; }
```

`json` is a small helper that pulls one value out of a response.

### 3.1 Server and catalog

```bash
curl -s $API/health
```

Expect `"status":"ok"` and `"data_status":"mock"`.

```bash
curl -s $API/scenarios | json "d['scenarios'][0]['id']"
```

Expect `earth_observation_01`.

```bash
curl -s "$API/catalog?scenario_id=earth_observation_01" | json "sorted(d['categories'])"
```

Expect the eight categories: `adcs`, `communication`, `instrument`,
`launch_vehicle`, `orbit`, `platform`, `power`, `propulsion`.

### 3.2 Evaluate designs (no login needed)

An empty design is evaluated, not rejected:

```bash
curl -s -X POST $API/evaluate -H 'Content-Type: application/json' \
  -d '{"scenario_id":"earth_observation_01"}' | json "(d['complete'], d['launchable'], len(d['missing']))"
```

Expect `(False, False, 8)`.

The example design is valid:

```bash
curl -s -X POST $API/evaluate -H 'Content-Type: application/json' -d "$DESIGN" \
  | json "(d['launchable'], d['resources']['total_mass_kg'], d['resources']['cost_usd'])"
```

Expect `(True, 255.0, 43500000.0)`.

Swap the camera for the hyperspectral imager, which needs too much power:

```bash
BAD=$(echo "$DESIGN" | python -c "import sys,json; d=json.load(sys.stdin); d['spacecraft']['instrument_ids']=['hyperspectral_imager']; print(json.dumps(d))")
curl -s -X POST $API/evaluate -H 'Content-Type: application/json' -d "$BAD" \
  | json "[(c['id'], c['status']) for c in d['constraints'] if c['status']=='failed']"
```

Expect `[('power_balance', 'failed')]`, with HTTP status 200 (an infeasible
design is a normal result).

An unknown id is an error:

```bash
curl -s -X POST $API/evaluate -H 'Content-Type: application/json' \
  -d '{"scenario_id":"earth_observation_01","orbit_id":"moon_base"}'
```

Expect `{"error":{"code":"unknown_component", ... "field":"orbit_id"}}`.

### 3.3 Accounts

```bash
TOKEN=$(curl -s -X POST $API/auth/register -H 'Content-Type: application/json' \
  -d '{"username":"ada","password":"correct horse"}' | json "d['token']")
AUTH="Authorization: Bearer $TOKEN"
curl -s $API/auth/me -H "$AUTH"
```

Expect `"username":"ada"`.

Check the failures:

| Command | Expected |
| --- | --- |
| Register `ada` again | `409` `username_taken` |
| Register with password `short` | `422` `invalid_request`, and the password is not in the response |
| Log in with a wrong password | `401` `invalid_credentials` |
| `GET /missions` with no token | `401` `not_authenticated` |
| `GET /auth/me` with `Authorization: Bearer nonsense` | `401` `invalid_token` |

For example:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST $API/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"ada","password":"wrong password"}'
```

Expect `401`.

### 3.4 Save a mission

```bash
MISSION=$(curl -s -X POST $API/missions -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"name\":\"Earth Watch A\",\"design\":$DESIGN}" | json "d['mission_id']")
curl -s $API/missions -H "$AUTH" | json "[(m['name'], m['run_count']) for m in d]"
```

Expect `[('Earth Watch A', 0)]`.

### 3.5 Launch and play a mission

A failing design cannot launch:

```bash
curl -s -X POST $API/runs -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"design\":$BAD}" | json "(d['error']['code'], d['error']['evaluation']['launchable'])"
```

Expect `('not_launchable', False)`.

Launch the good design with seed `0`. The seed fixes all randomness, so you get
exactly the events listed here:

```bash
RUN=$(curl -s -X POST $API/runs -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"design\":$DESIGN,\"mission_id\":\"$MISSION\",\"seed\":0}")
RUN_ID=$(echo "$RUN" | json "d['run_id']")
echo "$RUN" | json "(d['status'], d['pending_event']['event_id'])"
```

Expect `('awaiting_decision', 'solar_storm')`.

Answer the event:

```bash
curl -s -X POST $API/runs/$RUN_ID/decisions -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"event_id":"solar_storm","option_id":"safe_mode"}' | json "(d['status'], d['pending_event']['event_id'])"
```

Expect `('awaiting_decision', 'power_fault')`.

Send the same answer again; it must be refused:

```bash
curl -s -X POST $API/runs/$RUN_ID/decisions -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"event_id":"solar_storm","option_id":"safe_mode"}' | json "d['error']['code']"
```

Expect `no_pending_event`.

Answer the second event:

```bash
curl -s -X POST $API/runs/$RUN_ID/decisions -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"event_id":"power_fault","option_id":"shed_load"}' \
  | json "(d['status'], d['debrief']['outcome'], d['debrief']['score']['total'])"
```

Expect `('completed', 'success', 95.8)` with the current placeholder engine and
mock data. The score will change once Person 2 and Person 1 replace them.

### 3.6 Mission history

```bash
curl -s $API/runs -H "$AUTH" | json "[(r['mission_name'], r['outcome'], r['score_total']) for r in d]"
```

Expect `[('Earth Watch A', 'success', 95.8)]`.

Open the old mission in full:

```bash
curl -s $API/runs/$RUN_ID -H "$AUTH" | json "(d['design']['spacecraft']['instrument_ids'], len(d['log']), d['debrief']['outcome'])"
```

Expect the instrument list, a log of several lines, and `success`.

Runs of one saved mission, and its best score:

```bash
curl -s $API/missions/$MISSION/runs -H "$AUTH" | json "len(d)"
curl -s $API/missions/$MISSION -H "$AUTH" | json "(d['run_count'], d['best_score'])"
```

Expect `1`, then `(1, 95.8)`.

### 3.7 Privacy between players

```bash
TOKEN_B=$(curl -s -X POST $API/auth/register -H 'Content-Type: application/json' \
  -d '{"username":"bob","password":"correct horse"}' | json "d['token']")
AUTH_B="Authorization: Bearer $TOKEN_B"

curl -s $API/runs -H "$AUTH_B"
curl -s -o /dev/null -w '%{http_code}\n' $API/runs/$RUN_ID -H "$AUTH_B"
curl -s -o /dev/null -w '%{http_code}\n' $API/missions/$MISSION -H "$AUTH_B"
curl -s -o /dev/null -w '%{http_code}\n' $API/runs/$RUN_ID
```

Expect `[]`, then `404`, `404`, `404`. Another player and a guest cannot see Ada's
missions or runs, and the API does not reveal that they exist.

### 3.8 Guest play

```bash
curl -s -X POST $API/runs -H 'Content-Type: application/json' \
  -d "{\"design\":$DESIGN,\"seed\":1}" | json "(d['status'], d['pending_event']['event_id'])"
```

Expect `('awaiting_decision', 'solar_storm')`. A guest can play, but the run
appears in nobody's history.

### 3.9 Log out

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST $API/auth/logout -H "$AUTH"
curl -s -o /dev/null -w '%{http_code}\n' $API/auth/me -H "$AUTH"
```

Expect `204`, then `401`.

### 3.10 Data survives a restart

Stop the server (Ctrl+C), start it again, log in as `ada`, and list `GET /runs`.
The run from 3.5 is still there.

---

## 4. Checklist before pushing

- [ ] `python -m backend.app.check_data` prints `OK`
- [ ] `python -m pytest -q` shows **23 passed**, nothing skipped
- [ ] If models, engine or data changed: `python -m scripts.make_fixtures` and the fixture files are committed
- [ ] No `*.db`, `.env` or `.venv` in `git status`
- [ ] `AI_CONTEXT.md` updated if the contract or a decision changed

---

## 5. Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `ModuleNotFoundError: No module named 'backend'` | You are not in the repository root. `cd` to the folder with `README.md` |
| `19 passed, 1 skipped` | FastAPI or httpx missing in the active environment. Activate `.venv`, rerun `pip install -r requirements.txt` |
| Server will not start: `Catalog data is invalid` | A file in `data/` is wrong. Run `python -m backend.app.check_data` for the list |
| `sqlite3.OperationalError: no such column` | The schema changed. Stop the server and delete `space_mission.db` |
| `409 username_taken` in the walkthrough | The database already has that user. Delete `space_mission.db` or use another name |
| Browser frontend gets a CORS error | Set `CORS_ORIGINS` to the frontend's address, e.g. `CORS_ORIGINS=http://localhost:3000` |
| Different events or score than this guide | Engine or data changed since this guide was written; regenerate fixtures and update the expected values here |
| `Address already in use` | Another server is on port 8000. Stop it, or use `--port 8001` and change `API` |
