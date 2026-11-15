# Game UI (`frontend/game/`)

The playable game: briefing → design → validation → launch → operations with MCAS
decisions → score → debrief → improve and replay. Plain HTML, CSS and JavaScript
modules: no build step, no npm install.

## Run it

From the repository root:

```bash
pip install -r requirements.txt
uvicorn backend.app.main:create_app --factory --reload --port 8000
```

Open **http://127.0.0.1:8000/**. The backend serves this folder at `/` by default
(set `FRONTEND_DIST` to serve something else). Opening the files with VS Code Live
Server on port 5500 also works: the UI then calls `http://127.0.0.1:8000/api/v1`.
Set `window.GAME_API_BASE` before `js/app.js` loads to point anywhere else.

## Layout rules (team decisions)

- The page never scrolls: every screen fits the viewport (tested at 1280×720,
  1366×768 and 1920×1080). Long lists are paged, long notes are clamped with the
  full text in a tooltip.
- Little text: numbers, short labels and one-line explanations.
- No sidebar and no top bar. The profile and saves icons are on the home screen only.
- Palette: `--bg #141210`, `--panel #1e1b18`, `--panel2 #282420`, `--line #3a3430`,
  `--text #f7f4ef`, `--muted #a39b93`, `--accent #d97706`, `--green #059669`,
  `--yellow #d97706`, `--red #dc2626` (top of `css/game.css`).
- Launch review has three verdicts from the engine's `launch_assessment`: **GO**,
  **RISKY** (launch anyway; the failed checks become accidents or damage in flight)
  and **NO GO** (catastrophic only).

## Files

| File | What it does |
| --- | --- |
| `index.html` | Shell: sidebar journey, top bar, screen host, modal root |
| `css/game.css` | All styles |
| `js/app.js` | Boot, routing between screens, journey sidebar |
| `js/api.js` | Calls to `/api/v1` (catalog, evaluate, MCAS missions, recommend, auth) |
| `js/state.js` | Game state, saved in `localStorage`; broadcasts `smdg:state` |
| `js/catalog.js` | Designer slots and how each component is summarised |
| `js/screens/*.js` | One file per screen, plus `account.js` (login, history) |

## Endpoints used

| Screen | Endpoint |
| --- | --- |
| Boot | `GET /simulation/catalog`, `GET /simulation/scenarios`, `GET /auth/me` |
| Engineering workspace, validation | `POST /simulation/evaluate` (live, debounced) |
| Launch | `POST /simulation/missions` |
| Operations | `POST /simulation/missions/{id}/decisions` |
| Results | the `debrief` returned with the completed mission |
| Debrief | `POST /simulation/recommend` (the "Engineers suggest" card) |
| History | `GET /simulation/missions`, `GET /simulation/missions/{id}` |
| Profile | `POST /auth/register`, `/auth/login`, `/auth/logout` |

The UI computes no score and invents no consequence: every number shown comes
from the engine. `n/p` means not published; `*` marks an estimate or a gameplay
assumption.

## 3D views (for the visualization pair)

Two empty containers are reserved and must stay free of UI:

| Element | Screen | `data-view` |
| --- | --- | --- |
| `#viewport-designer` | Engineering workspace | `spacecraft` |
| `#viewport-operations` | Mission operations | `mission` |

Mount a canvas inside them. To follow the game, listen to one event:

```js
window.addEventListener("smdg:state", (e) => {
  const { reason, screen, configuration, evaluation, mission, shownPeriod } = e.detail;
  // reason: "screen" | "design" | "evaluation" | "launched" | "period" | "decision" | "completed" | ...
  // configuration: the v4 configuration (component ids)
  // mission: the MCAS run state (timeline, pending_decision, ...) once launched
  // shownPeriod: the operation period the playback has reached
});
```

Screens are rebuilt on navigation, so re-attach your canvas when `reason === "screen"`
and the container exists again.

## Not done yet

- Lunar and Mars missions are shown as "Soon" (the engine refuses them).
- Saved design slots: the current design is kept in the browser only.
- Multiplayer (the wireframe's player-count selector) is not implemented.
