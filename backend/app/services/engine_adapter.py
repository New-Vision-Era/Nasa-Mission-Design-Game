"""The ONLY backend file that imports the simulation engine.

If Person 2's functions end up with different names or arguments, change
this file and nothing else.
"""

from simulation import engine
from simulation.models import Catalog, Debrief, Decision, Design, Evaluation, RunState, Scenario


class EngineAdapter:
    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog

    def evaluate(self, design: Design, scenario: Scenario) -> Evaluation:
        return engine.evaluate_design(design, scenario, self.catalog)

    def start_run(self, design: Design, scenario: Scenario, seed: int) -> RunState:
        return engine.start_run(design, scenario, self.catalog, seed)

    def apply_decision(self, state: RunState, decision: Decision, scenario: Scenario) -> RunState:
        """Raises ValueError when the decision does not match the pending event."""
        return engine.apply_decision(state, decision, scenario, self.catalog)

    def build_debrief(self, state: RunState, scenario: Scenario) -> Debrief:
        return engine.build_debrief(state, scenario, self.catalog)
