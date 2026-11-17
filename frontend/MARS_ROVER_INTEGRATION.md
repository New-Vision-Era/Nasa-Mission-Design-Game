# Mars rover UI integration

The Mars rover UI is provided as the companion archive `mission-control-mars-backend-integrated.zip`.
Extract its `mission-control/` directory and serve that directory with a static server (for example VS Code Live Server on port 5500).

The frontend adapter calls:
- `GET /api/v1/mars/catalog`
- `POST /api/v1/mars/evaluate`
- `POST /api/v1/mars/simulate`

By default it uses `http://127.0.0.1:8000/api/v1/mars`. Set `window.MARS_API_BASE` before `js/mars-api.js` if the backend runs elsewhere.

## Run locally

From the repository root:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.app.main:create_app --factory --reload --port 8000
```

Open the extracted UI's `index.html` using Live Server. Configure a complete rover on the designer page, then use Review and Launch. Review and the four-stage simulation require the Mars API; the original local calculations remain available for the designer dashboard and option filtering.

## Test

```bash
pytest -q backend/tests simulation/tests
```

The Mars engine is separate from the existing Earth-observation engine and uses the prototype's educational assumptions: $100M budget, 2,000 kg mission cap, 200 W bus load, and launch/cruise/landing/surface stages. These are not official NASA mission specifications.
