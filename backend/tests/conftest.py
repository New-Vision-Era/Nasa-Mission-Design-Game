import copy
import json

import pytest

from backend.app.config import REPO_ROOT, Settings
from backend.app.container import build_container
from simulation.models import Design


@pytest.fixture()
def container():
    c = build_container(Settings(database_path=":memory:"))
    yield c
    c.db.close()


@pytest.fixture()
def good_design() -> Design:
    raw = json.loads((REPO_ROOT / "data" / "fixtures" / "design_example.json").read_text())
    return Design.model_validate(raw)


@pytest.fixture()
def bad_design(good_design) -> Design:
    """Hyperspectral imager on the small solar array: not enough power."""
    d = copy.deepcopy(good_design)
    d.spacecraft.instrument_ids = ["hyperspectral_imager"]
    return d


def play_to_end(runs, user, run):
    """Answer every event with its first option until the run completes."""
    guard = 0
    while run.status == "awaiting_decision":
        from simulation.models import Decision

        event = run.pending_event
        run = runs.decide(user, run.run_id, Decision(event_id=event.event_id, option_id=event.options[0].option_id))
        guard += 1
        assert guard < 50
    return run
