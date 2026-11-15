"""Regenerate data/fixtures/*.json from the real code path.

    python -m scripts.make_fixtures

Run it after changing the models, the engine or the data, and commit the
result. The frontend mocks import these files, and a backend test checks
that they still match the models.
"""

from backend.app.config import REPO_ROOT, Settings
from backend.app.container import build_container
from backend.app.schemas import RunCreate
from simulation.models import Decision, Design


def main() -> None:
    c = build_container(Settings(database_path=":memory:"))
    fx = REPO_ROOT / "data" / "fixtures"
    design = Design.model_validate_json((fx / "design_example.json").read_text())

    def write(name: str, model) -> None:
        (fx / name).write_text(model.model_dump_json(indent=2) + "\n")
        print("wrote", name)

    write("evaluation_example.json", c.runs.evaluate(design))

    broken = design.model_copy(deep=True)
    broken.spacecraft.instrument_ids = ["hyperspectral_imager"]
    write("evaluation_failed_example.json", c.runs.evaluate(broken))

    run = None
    for seed in range(500):
        run = c.runs.start(None, RunCreate(design=design, seed=seed))
        if run.status == "awaiting_decision":
            write("run_awaiting_decision_example.json", run)
            break
    while run.status == "awaiting_decision":
        event = run.pending_event
        run = c.runs.decide(None, run.run_id, Decision(event_id=event.event_id, option_id=event.options[0].option_id))
    write("run_completed_example.json", run)


if __name__ == "__main__":
    main()
