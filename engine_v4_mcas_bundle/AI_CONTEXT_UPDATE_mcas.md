# AI_CONTEXT.md update: MCAS on engine v4 (2026-11-15)

Merge into `AI_CONTEXT.md`. Details and the full contract are in `README_MCAS.md`.

## Section 7, add under the v4 structure

``` text
simulation/engine_v4/interactive.py     # evaluate_design, start_run, apply_decision, build_debrief (v4 + MCAS)
simulation/engine_v4/mission/mcas/      # models, anomaly_catalog, trigger_engine, anomaly_generator,
                                        # decision_manager, anomaly_resolver, state_manager,
                                        # risk_assessment, history
simulation/engine_v4/tests/test_mcas.py
```

The v4 engine now has a step-by-step mission with player decisions. A run state is a JSON dict holding
configuration, scenario overrides, seed and decisions; every call replays from those. Runs are also kept
in process memory by `mission_id`. `run_simulation()` is unchanged.

## Section 13

### Implemented (add)

- MCAS foundation for Earth observation: risk assessment (LOW / MEDIUM / HIGH / UNKNOWN), six anomalies
  (communication outage, power shortage, data backlog, instrument unavailable, pointing instability,
  optical downlink cloud), two or three responses each, mission history, explainable debrief with a
  no-anomaly reference score.
- Framework-free handlers: `handle_evaluate_request`, `handle_start_request`, `handle_decision_request`,
  `handle_debrief_request`.
- `mission/operations.py` refactored to run through MCAS; `Scenario.mission_type` added.

### Test status (add)

- **Run and passing:** 125 tests (`python -m pytest simulation/engine_v4 -q`): the 93 existing plus 32 in
  `test_mcas.py`. The original and refactored `simulate_mission` gave identical JSON on 5,440 runs.
- **Not run:** backend, FastAPI layer. No router exists for the new handlers.

### Not implemented (add)

- Moon and Mars landing (declared in the MCAS catalogue as not implemented, and refused).
- Thermal, propulsion and attitude anomalies; response deadlines; battery state of charge; propellant use.
- MCAS behind the backend's `engine_adapter.py`; persistence of v4 runs.

### Decision log (add rows)

| Date/time | Decision or change | Reason | Affected areas |
| --- | --- | --- | --- |
| 2026-11-15 | MCAS added under `simulation/engine_v4/mission/mcas/`; a run is replayed from configuration, seed and decisions | Reproducible, and the state stores as JSON with no schema change | Simulation, backend |
| 2026-11-15 | `run_simulation()` keeps the original four events with default responses | Existing tests and the non-interactive example must not change | Simulation |
| 2026-11-15 | Risk level `UNKNOWN` added beside LOW / MEDIUM / HIGH | A missing value must not read as low risk | Simulation, frontend |
| 2026-11-15 | Anomalies never subtract fixed points; the score changes only through the mission result | Scoring weights and rules stay as they are | Scoring |

### Needs team approval (add)

6. Whether `run_simulation()` should apply the full MCAS scope (data backlog, pointing instability), which
   would change scores for designs with a pointing warning.
7. Operational availability as a reliability factor (reported in the debrief, not scored).
8. MCAS gameplay rules: missed targets = pointing error / swath; recovery_period_fraction 0.5; safe mode
   when operations continue through a power shortage.
9. Mapping of `pending_decision {anomaly_id, responses[]}` to the backend's `pending_event {event_id, options[]}`.
