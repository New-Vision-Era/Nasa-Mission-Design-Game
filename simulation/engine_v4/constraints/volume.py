"""Payload volume compatibility (hard where evaluable).

Single item: sorted-dimension fit, rotation allowed (axis-aligned).
Several items: fitting individually does not prove they fit together, so a
conservative summed-volume rule with a gameplay packing factor is applied.
"""
from __future__ import annotations

from typing import Optional

from ..configuration import ScenarioParams, Selection
from ..results import (FAIL, GAMEPLAY, HARD, NOT_EVALUATED, PASS, PUBLISHED, ConstraintResult,
                       source_urls)


def fits_envelope(dimensions_mm: Optional[list], envelope_mm: Optional[list]) -> Optional[bool]:
    """True/False if both dimension triples are known, None if either is unknown."""
    if not _valid(dimensions_mm) or not _valid(envelope_mm):
        return None
    return all(d <= e for d, e in zip(sorted(dimensions_mm), sorted(envelope_mm)))


def _valid(dims) -> bool:
    return (isinstance(dims, (list, tuple)) and len(dims) == 3
            and all(isinstance(d, (int, float)) and not isinstance(d, bool) and d > 0 for d in dims))


def _volume(dims) -> float:
    return dims[0] * dims[1] * dims[2]


def check_volume(sel: Selection, params: ScenarioParams) -> ConstraintResult:
    envelope = sel.platform.get("payload_volume_mm")
    items = sel.carried(include_subsystems=(params.volume_scope == "all"))
    recs = [r for _, r in items]
    scope_note = ("Only instruments are checked against the payload bay; where subsystems sit is unknown."
                  if params.volume_scope == "instruments" else
                  "Instruments and all selected subsystems are checked against the payload bay.")
    base = dict(id="payload_volume", category="volume", title="Payload volume fit", severity=HARD,
                unit="mm3", source_urls=source_urls(sel.platform, *recs), related_step="instruments")
    if not recs:
        return ConstraintResult(status=PASS, message="No components to place in the payload bay.",
                                value_kind=PUBLISHED, assumptions=[scope_note], **base)
    if not _valid(envelope):
        return ConstraintResult(status=NOT_EVALUATED, message="The platform payload envelope is unknown.",
                                affected_component_ids=[sel.platform["id"]], assumptions=[scope_note], **base)

    too_big = [r["id"] for r in recs if fits_envelope(r.get("dimensions_mm"), envelope) is False]
    unknown = [r["id"] for r in recs if not _valid(r.get("dimensions_mm"))]
    env_txt = " x ".join(f"{e:g}" for e in envelope)
    if too_big:
        details = "; ".join(
            f"{r['id']} is {' x '.join(f'{d:g}' for d in r['dimensions_mm'])} mm"
            for r in recs if r["id"] in too_big)
        return ConstraintResult(
            status=FAIL, affected_component_ids=too_big, value_kind=PUBLISHED, assumptions=[scope_note],
            message=f"Does not fit the {sel.platform['name']} payload bay ({env_txt} mm) in any orientation: {details}.",
            **base)
    if unknown:
        return ConstraintResult(
            status=NOT_EVALUATED, affected_component_ids=unknown, value_kind=PUBLISHED, assumptions=[scope_note],
            message=(f"Dimensions of {', '.join(unknown)} are not published, so fit in the {env_txt} mm bay "
                     "cannot be confirmed. Unknown dimensions are not treated as zero."),
            **base)
    if len(recs) == 1:
        return ConstraintResult(
            status=PASS, value_kind=PUBLISHED, assumptions=[scope_note],
            actual_value=_volume(recs[0]["dimensions_mm"]), limit_value=_volume(envelope),
            message=f"{recs[0]['id']} fits the {env_txt} mm payload bay.", **base)

    total = sum(_volume(r["dimensions_mm"]) for r in recs)
    bay = _volume(envelope)
    limit = bay * params.packing_factor
    packing_note = (f"Combined fit uses a conservative rule: summed component volume must stay below "
                    f"{params.packing_factor:g} x bay volume. The packing factor is a GAMEPLAY ASSUMPTION; "
                    "this is not a geometric packing proof.")
    common = dict(actual_value=total, limit_value=limit, value_kind=GAMEPLAY,
                  assumptions=[scope_note, packing_note], **base)
    if total > limit:
        biggest = sorted(recs, key=lambda r: -_volume(r["dimensions_mm"]))[:2]
        why = ("exceeds the bay volume itself" if total > bay else
               f"exceeds the conservative packing limit ({params.packing_factor:g} of the bay)")
        return ConstraintResult(
            status=FAIL, affected_component_ids=[r["id"] for r in biggest],
            message=f"Each item fits alone, but the summed volume {why}. Largest items: "
                    + ", ".join(r["id"] for r in biggest) + ".", **common)
    return ConstraintResult(
        status=PASS, message=f"All {len(recs)} items fit individually and their summed volume is "
                             f"{total / bay * 100:.0f}% of the bay (limit {params.packing_factor * 100:.0f}%).",
        **common)
