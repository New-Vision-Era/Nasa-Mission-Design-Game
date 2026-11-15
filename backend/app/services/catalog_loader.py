"""Read data/*.json once at startup, validate it, and build the Catalog.

A bad file stops the server from starting; every problem is listed with its
file and field so Person 1 can fix it without reading backend code.
"""

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from simulation.models import SLOT_CATEGORIES, Catalog, Component, Event, Scenario, Source


class CatalogError(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("Catalog data is invalid:\n- " + "\n- ".join(problems))
        self.problems = problems


def _read(path: Path, problems: list[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"{path.name}: cannot read JSON ({exc})")
        return None


def _numeric_fields(raw: dict[str, Any]) -> list[str]:
    return [k for k, v in raw.items() if isinstance(v, (int, float)) and not isinstance(v, bool)]


def _describe(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
    )


def load_catalog(data_dir: Path) -> Catalog:
    problems: list[str] = []
    data_dir = Path(data_dir)

    meta = _read(data_dir / "catalog_meta.json", problems) or {}

    sources: dict[str, Source] = {}
    for raw in _read(data_dir / "sources.json", problems) or []:
        try:
            source = Source.model_validate(raw)
            sources[source.id] = source
        except ValidationError as exc:
            problems.append(f"sources.json: {_describe(exc)}")

    components: dict[str, Component] = {}
    for path in sorted((data_dir / "components").glob("*.json")):
        for raw in _read(path, problems) or []:
            label = f"components/{path.name} [{raw.get('id', '?')}]"
            try:
                component = Component.model_validate(raw)
            except ValidationError as exc:
                problems.append(f"{label}: {_describe(exc)}")
                continue
            if component.id in components:
                problems.append(f"{label}: duplicate id")
            components[component.id] = component
            # Rule: every number says where it came from.
            for field in _numeric_fields(raw):
                prov = component.provenance.get(field)
                if prov is None:
                    problems.append(f"{label}: '{field}' has no provenance entry")
                elif prov.kind == "published" and prov.source_id not in sources:
                    problems.append(
                        f"{label}: '{field}' is 'published' but source_id "
                        f"'{prov.source_id}' is not in sources.json"
                    )

    # Validate launch vehicle -> orbit references after all component files load.
    for component in components.values():
        if component.category != "launch_vehicle":
            continue
        for orbit_id in component.supported_orbit_ids:
            orbit = components.get(orbit_id)
            if orbit is None or orbit.category != "orbit":
                problems.append(
                    f"components/launch_vehicles [{component.id}]: "
                    f"supported orbit '{orbit_id}' does not reference an orbit component"
                )

    scenarios: dict[str, Scenario] = {}
    for path in sorted((data_dir / "scenarios").glob("*.json")):
        raw = _read(path, problems)
        if raw is None:
            continue
        label = f"scenarios/{path.name}"
        try:
            scenario = Scenario.model_validate(raw)
        except ValidationError as exc:
            problems.append(f"{label}: {_describe(exc)}")
            continue
        if scenario.id in scenarios:
            problems.append(f"{label}: duplicate scenario id '{scenario.id}'")
        scenarios[scenario.id] = scenario
        for cid in scenario.allowed_component_ids or []:
            if cid not in components:
                problems.append(f"{label}: allowed component '{cid}' does not exist")
        for slot in scenario.required_slots:
            if slot not in SLOT_CATEGORIES:
                problems.append(f"{label}: unknown required slot '{slot}'")
        if scenario.operations_steps < 1:
            problems.append(f"{label}: operations_steps must be at least 1")

    events: list[Event] = []
    seen_events: set[str] = set()
    for path in sorted((data_dir / "events").glob("*.json")):
        for raw in _read(path, problems) or []:
            label = f"events/{path.name} [{raw.get('id', '?')}]"
            try:
                event = Event.model_validate(raw)
            except ValidationError as exc:
                problems.append(f"{label}: {_describe(exc)}")
                continue
            if event.id in seen_events:
                problems.append(f"{label}: duplicate id")
            if len(event.options) < 2:
                problems.append(f"{label}: an event needs at least two options")
            seen_events.add(event.id)
            events.append(event)

    if not scenarios:
        problems.append("scenarios/: no scenario found")
    if meta.get("data_status") not in ("mock", "reviewed"):
        problems.append("catalog_meta.json: data_status must be 'mock' or 'reviewed'")
    if not meta.get("catalog_version"):
        problems.append("catalog_meta.json: catalog_version is missing")

    if problems:
        raise CatalogError(problems)

    return Catalog(
        catalog_version=meta["catalog_version"],
        data_status=meta["data_status"],
        components=components,
        scenarios=scenarios,
        events=events,
        sources=sources,
    )
