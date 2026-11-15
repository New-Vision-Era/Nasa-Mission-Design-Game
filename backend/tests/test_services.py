"""Service-level tests. They need no web framework, only pydantic and pytest."""

import json
import shutil

import pytest

from backend.app.config import REPO_ROOT
from backend.app.errors import ApiError
from backend.app.schemas import MissionCreate, MissionUpdate, RunCreate, RunView
from backend.app.services.catalog_loader import CatalogError, load_catalog
from backend.tests.conftest import play_to_end
from simulation.models import Decision, Design, Evaluation

SCENARIO = "earth_observation_01"


# --- catalog ---------------------------------------------------------------


def test_real_data_folder_loads(container):
    assert container.catalog.scenarios[SCENARIO].budget_usd > 0
    assert container.catalog.data_status in ("mock", "reviewed")


def test_number_without_provenance_is_rejected(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(REPO_ROOT / "data", data)
    path = data / "components" / "power.json"
    items = json.loads(path.read_text())
    del items[0]["provenance"]["mass_kg"]
    items[1]["provenance"]["mass_kg"] = {"kind": "published", "source_id": "does_not_exist"}
    path.write_text(json.dumps(items))
    with pytest.raises(CatalogError) as exc:
        load_catalog(data)
    text = "\n".join(exc.value.problems)
    assert "no provenance entry" in text and "does_not_exist" in text


def test_fixtures_match_the_models():
    fixtures = REPO_ROOT / "data" / "fixtures"
    Design.model_validate_json((fixtures / "design_example.json").read_text())
    for name, model in (
        ("evaluation_example.json", Evaluation),
        ("evaluation_failed_example.json", Evaluation),
        ("run_awaiting_decision_example.json", RunView),
        ("run_completed_example.json", RunView),
    ):
        model.model_validate_json((fixtures / name).read_text())


# --- evaluate ----------------------------------------------------------------


def test_partial_design_is_evaluated_not_rejected(container):
    ev = container.runs.evaluate(Design(scenario_id=SCENARIO))
    assert ev.complete is False and ev.launchable is False
    assert "orbit_id" in ev.missing
    assert {c.status for c in ev.constraints} <= {"not_evaluated", "passed"}


def test_infeasible_design_reports_failed_hard_constraint(container, bad_design):
    ev = container.runs.evaluate(bad_design)
    power = next(c for c in ev.constraints if c.id == "power_balance")
    assert power.status == "failed" and power.severity == "hard" and power.related_step == "power"
    assert ev.launchable is False


def test_good_design_is_launchable(container, good_design):
    ev = container.runs.evaluate(good_design)
    assert ev.complete and ev.launchable
    assert ev.resources["cost_usd"] <= ev.resources["budget_usd"]


def test_unknown_or_misplaced_component_is_422(container, good_design):
    good_design.orbit_id = "optical_camera"  # an instrument in the orbit slot
    with pytest.raises(ApiError) as exc:
        container.runs.evaluate(good_design)
    assert exc.value.status == 422 and exc.value.code == "unknown_component" and exc.value.field == "orbit_id"

    with pytest.raises(ApiError) as exc:
        container.runs.evaluate(Design(scenario_id="nope"))
    assert exc.value.status == 404


# --- accounts ----------------------------------------------------------------


def test_register_login_logout(container):
    auth = container.auth
    session = auth.register("Ada_L", "correct horse")
    assert session.user.username == "ada_l"
    assert auth.user_for_token(session.token).id == session.user.id

    with pytest.raises(ApiError) as exc:
        auth.register("ada_l", "another password")
    assert exc.value.status == 409 and exc.value.code == "username_taken"

    for name, pw in (("ada_l", "wrong password"), ("nobody", "correct horse")):
        with pytest.raises(ApiError) as exc:
            auth.login(name, pw)
        assert exc.value.status == 401 and exc.value.code == "invalid_credentials"

    second = auth.login("ADA_L", "correct horse")
    auth.logout(second.token)
    assert auth.user_for_token(second.token) is None
    assert auth.user_for_token(session.token) is not None  # other session untouched
    assert auth.user_for_token("garbage") is None


def test_passwords_and_tokens_are_not_stored_in_clear(container):
    session = container.auth.register("grace", "correct horse")
    dump = "\n".join(str(tuple(r)) for t in ("users", "sessions") for r in container.db.query(f"SELECT * FROM {t}"))
    assert "correct horse" not in dump and session.token not in dump


def test_expired_session_is_rejected(container):
    container.auth.ttl = container.auth.ttl * 0 - container.auth.ttl  # negative: already expired
    session = container.auth.register("old_timer", "correct horse")
    assert container.auth.user_for_token(session.token) is None


# --- saved missions ----------------------------------------------------------


def test_missions_are_private_to_their_owner(container, good_design):
    ada = container.auth.register("ada", "correct horse").user
    bob = container.auth.register("bob", "correct horse").user
    m = container.missions.create(ada, MissionCreate(name="First try", design=good_design))

    assert [x.mission_id for x in container.missions.list(ada)] == [m.mission_id]
    assert container.missions.list(bob) == []
    for call in (
        lambda: container.missions.get(bob, m.mission_id),
        lambda: container.missions.update(bob, m.mission_id, MissionUpdate(name="mine now")),
        lambda: container.missions.delete(bob, m.mission_id),
    ):
        with pytest.raises(ApiError) as exc:
            call()
        assert exc.value.status == 404

    renamed = container.missions.update(ada, m.mission_id, MissionUpdate(name="Second try"))
    assert renamed.name == "Second try" and renamed.design == good_design
    container.missions.delete(ada, m.mission_id)
    assert container.missions.list(ada) == []


# --- runs and history --------------------------------------------------------


def test_golden_path_fail_fix_launch_debrief(container, good_design, bad_design):
    ada = container.auth.register("ada", "correct horse").user

    with pytest.raises(ApiError) as exc:
        container.runs.start(ada, RunCreate(design=bad_design))
    assert exc.value.status == 409 and exc.value.code == "not_launchable"
    assert exc.value.body()["error"]["evaluation"]["launchable"] is False

    run = container.runs.start(ada, RunCreate(design=good_design, seed=7))
    run = play_to_end(container.runs, ada, run)
    assert run.status == "completed" and run.pending_event is None
    assert run.progress.step == run.progress.total_steps
    assert run.debrief is not None and 0 <= run.debrief.score["total"] <= 100
    assert run.debrief.outcome in ("success", "partial_success", "failure")
    assert run.design == good_design  # snapshot of what was flown


def test_same_seed_and_choices_give_the_same_run(container, good_design):
    results = []
    for _ in range(2):
        run = play_to_end(container.runs, None, container.runs.start(None, RunCreate(design=good_design, seed=1234)))
        results.append((run.telemetry, run.debrief.score, [e.message for e in run.log]))
    assert results[0] == results[1]


def test_events_occur_and_double_answers_are_refused(container, good_design):
    # Find a seed that produces an event at launch (deterministic search).
    for seed in range(200):
        run = container.runs.start(None, RunCreate(design=good_design, seed=seed))
        if run.status == "awaiting_decision":
            break
    else:
        pytest.fail("no seed in 0..199 produced an event")
    event = run.pending_event
    decision = Decision(event_id=event.event_id, option_id=event.options[0].option_id)

    with pytest.raises(ApiError) as exc:
        container.runs.decide(None, run.run_id, Decision(event_id=event.event_id, option_id="nope"))
    assert exc.value.status == 422

    after = container.runs.decide(None, run.run_id, decision)
    assert after.progress.step > run.progress.step
    with pytest.raises(ApiError) as exc:
        container.runs.decide(None, run.run_id, decision)  # same answer again
    assert exc.value.status == 409 and exc.value.code == "no_pending_event"


def test_history_lists_only_my_runs_newest_first(container, good_design):
    ada = container.auth.register("ada", "correct horse").user
    bob = container.auth.register("bob", "correct horse").user
    mission = container.missions.create(ada, MissionCreate(name="Earth Watch A", design=good_design))

    first = play_to_end(container.runs, ada, container.runs.start(ada, RunCreate(design=good_design, mission_id=mission.mission_id, seed=1)))
    second = play_to_end(container.runs, ada, container.runs.start(ada, RunCreate(design=good_design, seed=2)))
    guest = container.runs.start(None, RunCreate(design=good_design, seed=3))

    history = container.runs.history(ada)
    assert [h.run_id for h in history] == [second.run_id, first.run_id]
    assert history[1].mission_name == "Earth Watch A" and history[1].score_total == first.debrief.score["total"]
    assert container.runs.history(bob) == []
    assert [h.run_id for h in container.runs.history(ada, mission_id=mission.mission_id)] == [first.run_id]

    saved = container.missions.get(ada, mission.mission_id)
    assert saved.run_count == 1 and saved.best_score == first.debrief.score["total"]

    # Reviewing an old mission: the owner can, another player and a guest cannot.
    assert container.runs.get(ada, first.run_id).debrief is not None
    for other in (bob, None):
        with pytest.raises(ApiError) as exc:
            container.runs.get(other, first.run_id)
        assert exc.value.status == 404
    assert container.runs.get(None, guest.run_id).run_id == guest.run_id  # guest run: by id

    # Launching someone else's saved mission is refused.
    with pytest.raises(ApiError) as exc:
        container.runs.start(bob, RunCreate(design=good_design, mission_id=mission.mission_id))
    assert exc.value.status == 404

    # Deleting the saved design keeps the run in the history.
    container.missions.delete(ada, mission.mission_id)
    assert len(container.runs.history(ada)) == 2


def test_launch_vehicle_orbit_references_are_validated(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(REPO_ROOT / "data", data)
    path = data / "components" / "launch_vehicles.json"
    items = json.loads(path.read_text())
    items[0]["supported_orbit_ids"] = ["not_an_orbit"]
    path.write_text(json.dumps(items))
    with pytest.raises(CatalogError) as exc:
        load_catalog(data)
    assert "supported orbit 'not_an_orbit'" in "\n".join(exc.value.problems)
