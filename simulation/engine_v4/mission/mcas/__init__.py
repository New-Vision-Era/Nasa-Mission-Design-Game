"""MCAS: Mission Consequence & Anomaly System.

Detects, explains and resolves engineering problems and external events during a mission, from the
results of the existing engineering evaluation. A simplified educational game model.

Player-facing entry points are in `simulation.engine_v4.interactive`.
"""
from .anomaly_catalog import CATALOG, MISSION_TYPES, SCOPE_LEGACY, SCOPE_MVP
from .models import DecisionError, RunContext
from .risk_assessment import assess_risk
from .state_manager import Progress, advance

__all__ = ["CATALOG", "MISSION_TYPES", "SCOPE_LEGACY", "SCOPE_MVP", "DecisionError", "RunContext",
           "assess_risk", "advance", "Progress"]
