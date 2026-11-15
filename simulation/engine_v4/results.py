"""Shared result structure for every engineering check."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

PASS = "PASS"
FAIL = "FAIL"
NOT_EVALUATED = "NOT_EVALUATED"
WARNING = "WARNING"

HARD = "hard"
SOFT = "soft"

FEASIBLE = "FEASIBLE"
INFEASIBLE = "INFEASIBLE"
CONDITIONAL = "CONDITIONAL"

# value kinds, as defined in equipment_v4.json "value_kinds"
PUBLISHED = "published"
DERIVED = "derived"
ESTIMATE = "estimate"
GAMEPLAY = "gameplay_assumption"
MIXED = "mixed"


@dataclass
class ConstraintResult:
    id: str
    category: str
    status: str
    title: str
    message: str
    severity: str = HARD
    actual_value: Optional[float] = None
    limit_value: Optional[float] = None
    unit: Optional[str] = None
    affected_component_ids: list[str] = field(default_factory=list)
    value_kind: str = PUBLISHED
    source_urls: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    related_step: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def overall_feasibility(results: list[ConstraintResult]) -> dict[str, Any]:
    """FEASIBLE / INFEASIBLE / CONDITIONAL from the hard constraints only.

    A hard constraint that is NOT_EVALUATED never counts as a pass.
    Soft results (any status) never make a design infeasible.
    """
    hard = [r for r in results if r.severity == HARD]
    failed = [r.id for r in hard if r.status == FAIL]
    unknown = [r.id for r in hard if r.status == NOT_EVALUATED]
    warnings = [r.id for r in results if r.status == WARNING]
    if failed:
        status = INFEASIBLE
    elif unknown:
        status = CONDITIONAL
    else:
        status = FEASIBLE
    return {
        "status": status,
        "hard_failed": failed,
        "hard_not_evaluated": unknown,
        "warnings": warnings,
    }


def source_urls(*records: Optional[dict]) -> list[str]:
    """Unique source URLs of the given component records, order preserved."""
    out: list[str] = []
    for rec in records:
        if not rec:
            continue
        for url in rec.get("source_urls") or []:
            if url not in out:
                out.append(url)
    return out
