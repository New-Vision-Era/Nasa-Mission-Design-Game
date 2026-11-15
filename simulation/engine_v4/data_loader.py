"""Single loading layer for the canonical equipment dataset (currently equipment_v5.json).

Rules enforced here:
- null stays None. Nothing is defaulted or converted.
- Records are indexed by their stable `id`; ids are never renamed.
- Original fields and metadata (value_notes, source_urls, ...) are preserved.
- Invalid records are skipped and reported in `Catalog.issues`, never guessed.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Optional

CATEGORIES = (
    "platforms",
    "instruments",
    "power_systems",
    "communication_systems",
    "propulsion_systems",
    "adcs_systems",
    "orbits",
    "launch_vehicles",
)

_NUMERIC_SUFFIXES = ("_kg", "_w", "_wh", "_kbps", "_usd", "_ns", "_n", "_km", "_deg", "_min")

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "equipment_v5.json"


class CatalogError(Exception):
    """The dataset file is missing or structurally unusable."""


class Catalog:
    def __init__(self, raw: dict[str, Any]):
        if not isinstance(raw, dict):
            raise CatalogError("Dataset root must be a JSON object.")
        self.dataset_id: Optional[str] = raw.get("dataset_id")
        self.constants: dict = copy.deepcopy(raw.get("constants") or {})
        self.units: dict = copy.deepcopy(raw.get("units") or {})
        self.value_kinds: dict = copy.deepcopy(raw.get("value_kinds") or {})
        self.notes: list = copy.deepcopy(raw.get("notes") or [])
        self.reference_altitude_km = raw.get("reference_altitude_km")
        self.issues: list[str] = []
        self._index: dict[str, dict[str, dict]] = {}
        for category in CATEGORIES:
            records = raw.get(category)
            if not isinstance(records, list):
                raise CatalogError(f"Dataset is missing the '{category}' list.")
            self._index[category] = self._index_category(category, records)

    def _index_category(self, category: str, records: list) -> dict[str, dict]:
        index: dict[str, dict] = {}
        for pos, rec in enumerate(records):
            if not isinstance(rec, dict):
                self.issues.append(f"{category}[{pos}]: not an object, skipped.")
                continue
            rid = rec.get("id")
            if not isinstance(rid, str) or not rid:
                self.issues.append(f"{category}[{pos}]: missing or invalid id, skipped.")
                continue
            if rid in index:
                self.issues.append(f"{category}: duplicate id '{rid}', later record skipped.")
                continue
            bad = _invalid_numeric_fields(rec)
            if bad:
                self.issues.append(f"{category}/{rid}: invalid numeric field(s) {bad}, record skipped.")
                continue
            index[rid] = copy.deepcopy(rec)
        return index

    # --- lookup -----------------------------------------------------------
    def get(self, category: str, component_id: str) -> Optional[dict]:
        return self._index.get(category, {}).get(component_id)

    def all(self, category: str) -> list[dict]:
        return list(self._index.get(category, {}).values())

    def ids(self, category: str) -> list[str]:
        return list(self._index.get(category, {}).keys())

    def find(self, component_id: str) -> Optional[tuple[str, dict]]:
        for category in CATEGORIES:
            rec = self.get(category, component_id)
            if rec is not None:
                return category, rec
        return None

    def to_public_dict(self) -> dict[str, Any]:
        """Catalog for the frontend: every record with its original fields."""
        return {
            "dataset_id": self.dataset_id,
            "units": self.units,
            "value_kinds": self.value_kinds,
            "notes": self.notes,
            "load_issues": list(self.issues),
            "categories": {c: copy.deepcopy(self.all(c)) for c in CATEGORIES},
        }


def _invalid_numeric_fields(rec: dict) -> list[str]:
    bad = []
    for key, value in rec.items():
        if not key.endswith(_NUMERIC_SUFFIXES) or value is None:
            continue
        if isinstance(value, (dict, list)):  # structured fields such as power_range_w
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            bad.append(key)
    return bad


_cache: dict[tuple[str, float], Catalog] = {}


def load_catalog(path: Optional[str | os.PathLike] = None) -> Catalog:
    """Load (and cache) the canonical dataset.

    Path order: explicit argument, EQUIPMENT_DATA_PATH, <repo>/data/equipment_v5.json.
    """
    p = Path(path or os.environ.get("EQUIPMENT_DATA_PATH") or DEFAULT_PATH)
    try:
        key = (str(p), p.stat().st_mtime)
    except OSError as exc:
        raise CatalogError(f"Dataset file not found: {p}") from exc
    if key not in _cache:
        try:
            with open(p, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except json.JSONDecodeError as exc:
            raise CatalogError(f"Dataset file is not valid JSON: {p}") from exc
        _cache[key] = Catalog(raw)
    return _cache[key]
