# Pitch presentation — Space Mission Design Game

A cinematic, keyboard-driven HTML presentation for the 7-minute NASA Space Apps Challenge 2026 pitch.
It is separate from the game: nothing in `backend/`, `simulation/` or `data/` is used or changed at runtime.

## Launch

1. Open `presentation/index.html` in Chrome, Edge or Firefox (double-click it, or drag it into a browser window).
   No server, no internet and no install are needed. Fonts are bundled in `assets/fonts/`.
2. Press **F** for full screen.
3. Press **→** (or Space, or a clicker's "next" button) to advance.

Keep the `presentation/` folder together: `index.html` loads its fonts from `assets/fonts/`.
If the fonts are missing it still works, falling back to system fonts.

## Controls

| Key | Action |
| --- | --- |
| → · Space · PageDown · ↓ · Enter | Next beat, then next scene |
| ← · PageUp · ↑ · Backspace | Previous |
| 1 – 8 | Jump to a scene |
| F | Toggle full screen |
| P | Presenter overlay: current cue, next cue, timer, planned time window (hidden by default) |
| T | Reset the presenter timer |
| H | Hide the progress indicator |
| B or . | Black screen |
| ? | Key help |

Nothing advances on a timer. Each scene has a few **beats**: the speaker reveals them one at a time.
The timer starts on the first key press. You can also open a beat directly with a URL fragment, e.g. `index.html#6.2`.

## Scenes and beats

| # | Scene | Speech | Beats (press → for each) |
| --- | --- | --- | --- |
| 1 | Ahmed’s story | 0:00–0:50 | Ahmed studying · **on “But from this moment, everything is about to change.”** the room turns into mission control |
| 2 | Our solution | 0:50–1:25 | Name + spacecraft built from its blueprint · 5-step workflow |
| 3 | Beginner-friendly | 1:25–2:00 | Concept of the player flow · instrument chosen, requirements checked · next steps unlock |
| 4 | 3D visualization | 2:00–2:35 | Spacecraft above Earth · orbit view + derived orbit values |
| 5 | Scientific credibility | 2:35–3:25 | HyperScape100 examined · six value kinds · source → parameter → model → simulation |
| 6 | Multilayer evaluation | 3:25–5:25 | One decision, many consequences · Stage 1 feasibility · Stage 2 performance · traceability · debrief |
| 7 | Unexpected events | 5:25–6:10 | Mission timeline · power-shortage anomaly · response chosen, debrief recorded |
| 8 | Conclusion | 6:10–6:40 | Ahmed in mission control · final statement · title · fade to black |

## Where the content comes from

Every value or term on screen is taken from the repository (branch `feature/engine-v4-mcas-integration`):

- Instrument, platform, launcher and orbit values: `data/equipment_v5.json` (HyperScape100, Caiman Imager,
  TriScape100, GSAT-50, Electron, `sso_500`).
- Mission and requirements: `data/scenarios_v4/earth_observation_v4.json` (vegetation health monitoring,
  10 m / 15 km / SSO, score weights 35 / 25 / 20 / 20, 20 % margin target).
- Constraint names, FEASIBLE / INFEASIBLE / CONDITIONAL, score categories: `simulation/engine_v4/results.py`,
  `simulation/engine_v4/mission/scoring.py`.
- Debrief text in scene 6 and the PASS / NOT EVALUATED rows: output of `run_simulation()` on
  `simulation/engine_v4/examples/example_mission.json`, seed 42.
- Mission stages, the power-shortage anomaly and its three responses: `simulation/engine_v4/mission/operations.py`
  and `simulation/engine_v4/mission/mcas/anomaly_catalog.py`.

What is illustration, and labelled as such on screen:

- Scene 3 is a concept of the player flow, not a screenshot (the frontend is still being rebuilt).
- Scenes 2, 4 and 8 use a spacecraft drawn in code for the presentation, not the game’s 3D workshop.
- The scene 6 Stage 1 check sequence illustrates the CONDITIONAL case the engine produced before platform bus masses
  were added in `equipment_v5`.
- Scene 7 is an illustrative sequence of an anomaly modelled by MCAS.

“Measured” in scene 5 is the launcher flight record (successes / flights). In the dataset it is stored as a
published value, because the record comes from cited sources.

No NASA logo is used, and the presentation states that NASA has not reviewed or endorsed the project.
If any of these values change in `data/`, update the matching text in `index.html`.
