"""Check that every id in a design exists and sits in the right slot.

The simulation engine may then assume ids are valid.
"""

from simulation.models import SLOT_CATEGORIES, Catalog, Design, Scenario

from backend.app.errors import ApiError, not_found


def get_scenario(catalog: Catalog, scenario_id: str) -> Scenario:
    scenario = catalog.scenarios.get(scenario_id)
    if scenario is None:
        raise not_found(f"Scenario '{scenario_id}'")
    return scenario


def validate_design(design: Design, catalog: Catalog) -> Scenario:
    scenario = get_scenario(catalog, design.scenario_id)
    allowed = set(scenario.allowed_component_ids) if scenario.allowed_component_ids else None

    for slot, ids in design.slot_values().items():
        expected = SLOT_CATEGORIES[slot]
        if len(set(ids)) != len(ids):
            raise ApiError(422, "invalid_request", "The same component is selected twice.", field=slot)
        for index, cid in enumerate(ids):
            field = f"{slot}[{index}]" if slot.endswith("_ids") else slot
            component = catalog.components.get(cid)
            if component is None:
                raise ApiError(422, "unknown_component", f"No component with id '{cid}'.", field=field)
            if component.category != expected:
                raise ApiError(
                    422,
                    "unknown_component",
                    f"'{cid}' is a {component.category} component; this slot needs {expected}.",
                    field=field,
                )
            if allowed is not None and cid not in allowed:
                raise ApiError(
                    422, "unknown_component", f"'{cid}' is not available in this scenario.", field=field
                )
    return scenario
