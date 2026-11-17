"""Communications: commandability, ground-station compatibility, downlink capacity, data balance."""
from __future__ import annotations

from typing import Optional

from ..configuration import ScenarioParams, Selection
from ..results import (DERIVED, FAIL, GAMEPLAY, HARD, MIXED, NOT_EVALUATED, PASS, PUBLISHED, SOFT,
                       WARNING, ConstraintResult, source_urls)

SECONDS_PER_DAY = 86400.0


def pass_seconds_per_day(orbit: dict, params: ScenarioParams) -> Optional[float]:
    """Usable ground contact per day. Pass count and usable duration are gameplay parameters."""
    if params.average_usable_pass_duration_s is not None:
        return params.passes_per_day * params.average_usable_pass_duration_s
    max_pass = orbit.get("max_pass_duration_min_10deg")
    if max_pass is None:
        return None
    return params.passes_per_day * max_pass * 60.0 * params.usable_pass_fraction


def radio_is_compatible(radio: dict, params: ScenarioParams) -> bool:
    return radio.get("ground_station_type") in params.ground_station_types


def radio_availability(radio: dict, params: ScenarioParams) -> float:
    availability = params.link_availability
    if radio.get("ground_station_type") == "optical" or radio.get("needs_optical_ground_station"):
        availability *= params.optical_cloud_availability
    return availability


def daily_capacity_bits(radio: dict, pass_s: Optional[float], params: ScenarioParams) -> Optional[float]:
    """daily_capacity_bits = downlink_kbps * 1000 * pass_seconds_per_day * availability."""
    rate = radio.get("downlink_kbps")
    if rate is None or pass_s is None:
        return None
    return rate * 1000.0 * pass_s * radio_availability(radio, params)


def best_downlink(sel: Selection, params: ScenarioParams) -> dict:
    """Highest daily capacity among compatible radios (one radio transmits per pass)."""
    pass_s = pass_seconds_per_day(sel.orbit, params)
    best = {"radio_id": None, "bits_per_day": None, "pass_seconds_per_day": pass_s}
    for radio in sel.comms:
        if not radio_is_compatible(radio, params):
            continue
        cap = daily_capacity_bits(radio, pass_s, params)
        if cap is not None and (best["bits_per_day"] is None or cap > best["bits_per_day"]):
            best.update(radio_id=radio["id"], bits_per_day=cap)
    return best


def check_command_link(sel: Selection, params: ScenarioParams) -> ConstraintResult:
    base = dict(id="command_link", category="communications", title="Command uplink", severity=HARD,
                value_kind=PUBLISHED, source_urls=source_urls(*sel.comms), related_step="communications")
    if not params.commandable_required:
        return ConstraintResult(status=PASS, message="This scenario does not require a command uplink.",
                                severity=SOFT, **{k: v for k, v in base.items() if k != "severity"})
    usable = [r for r in sel.comms if radio_is_compatible(r, params)]
    yes = [r["id"] for r in usable if r.get("can_receive_commands") is True]
    unknown = [r["id"] for r in usable if r.get("can_receive_commands") is None]
    if yes:
        return ConstraintResult(status=PASS, affected_component_ids=yes,
                                message=f"{', '.join(yes)} can receive commands from the ground.", **base)
    if unknown:
        return ConstraintResult(
            status=NOT_EVALUATED, affected_component_ids=unknown,
            message=f"Whether {', '.join(unknown)} can receive commands is not published, and no other "
                    "selected radio is confirmed to. Add a TT&C transceiver to be sure.", **base)
    ids = [r["id"] for r in sel.comms]
    why = ("No communication system is selected." if not ids else
           f"{', '.join(ids)} cannot receive commands with the scenario's ground stations "
           "(transmit-only radios or incompatible ground-station type).")
    return ConstraintResult(status=FAIL, affected_component_ids=ids,
                            message=why + " The spacecraft would not be commandable.", **base)


def check_ground_station(sel: Selection, params: ScenarioParams) -> ConstraintResult:
    stations = ", ".join(params.ground_station_types) or "none"
    base = dict(id="ground_station_compatibility", category="communications",
                title="Ground-station compatibility", severity=HARD, value_kind=MIXED,
                source_urls=source_urls(*sel.comms), related_step="communications",
                assumptions=[f"Scenario ground stations: {stations} (gameplay parameter)."])
    if not sel.comms:
        return ConstraintResult(status=FAIL, message="No communication system is selected, so no data or "
                                                     "commands can be exchanged.", **base)
    bad = [r for r in sel.comms if not radio_is_compatible(r, params)]
    details = "; ".join(f"{r['id']} needs a {r.get('ground_station_type') or 'unknown'} station" for r in bad)
    if len(bad) == len(sel.comms):
        return ConstraintResult(status=FAIL, affected_component_ids=[r["id"] for r in bad],
                                message=f"No selected radio matches the available ground stations ({stations}): "
                                        f"{details}.", **base)
    if bad:
        return ConstraintResult(status=WARNING, affected_component_ids=[r["id"] for r in bad],
                                message=f"Unusable with this scenario's ground stations ({stations}): {details}. "
                                        "They add mass and power for no benefit.", **base)
    return ConstraintResult(status=PASS, message=f"All selected radios match the available ground stations "
                                                 f"({stations}).", **base)


def check_downlink_capacity(sel: Selection, params: ScenarioParams) -> tuple[ConstraintResult, dict]:
    best = best_downlink(sel, params)
    assumptions = [
        f"Passes per day: {params.passes_per_day:g} (gameplay parameter).",
        (f"Usable pass duration: {params.average_usable_pass_duration_s:g} s (gameplay parameter)."
         if params.average_usable_pass_duration_s is not None else
         f"Usable pass duration: {params.usable_pass_fraction:g} x the orbit's maximum overhead pass "
         "(gameplay parameter; real passes are shorter than the maximum)."),
        f"Link availability: {params.link_availability:g} (gameplay parameter).",
        "Downlink rates are maximum gross rates (upper bounds).",
    ]
    if any(r.get("ground_station_type") == "optical" for r in sel.comms):
        assumptions.append(f"Optical link cloud availability: {params.optical_cloud_availability:g} "
                           "(gameplay parameter).")
    base = dict(id="downlink_capacity", category="communications", title="Daily downlink capacity",
                severity=SOFT, unit="bits/day", value_kind=MIXED, source_urls=source_urls(*sel.comms),
                assumptions=assumptions, related_step="communications")
    if best["bits_per_day"] is None:
        return ConstraintResult(status=NOT_EVALUATED,
                                message="No compatible radio with a known downlink rate, so daily downlink "
                                        "capacity cannot be computed.", **base), best
    gb = best["bits_per_day"] / 8e9
    return ConstraintResult(
        status=PASS, actual_value=best["bits_per_day"], affected_component_ids=[best["radio_id"]],
        message=f"{best['radio_id']} can return about {gb:.2f} GB per day over "
                f"{best['pass_seconds_per_day']:.0f} s of contact.", **base), best


def instrument_data_rate_kbps(inst: dict, params: ScenarioParams) -> tuple[Optional[float], Optional[str]]:
    """(rate, value_kind). Scenario gameplay rate wins if given; else the published rate; else unknown."""
    if inst["id"] in params.data_generation_kbps:
        return params.data_generation_kbps[inst["id"]], GAMEPLAY
    if inst.get("data_rate_kbps") is not None:
        return inst["data_rate_kbps"], PUBLISHED
    return None, None


def daily_data_generated_bits(sel: Selection, params: ScenarioParams) -> dict:
    total, unknown, kinds = 0.0, [], set()
    for inst in sel.instruments:
        rate, kind = instrument_data_rate_kbps(inst, params)
        if rate is None:
            unknown.append(inst["id"])
            continue
        duty = params.instrument_duty_cycle_overrides.get(inst["id"], params.instrument_duty_cycle)
        total += rate * 1000.0 * duty * SECONDS_PER_DAY
        kinds.add(kind)
    return {"bits_per_day": total if not unknown and sel.instruments else None,
            "unknown_ids": unknown, "value_kinds": sorted(kinds)}


def check_data_balance(sel: Selection, params: ScenarioParams, best: dict) -> tuple[ConstraintResult, dict]:
    gen = daily_data_generated_bits(sel, params)
    base = dict(id="data_balance", category="communications", title="Data generated vs downlinked",
                severity=SOFT, unit="bits/day", limit_value=best["bits_per_day"],
                source_urls=source_urls(*sel.instruments, *sel.comms), related_step="communications")
    info = {"generated_bits_per_day": gen["bits_per_day"], "downlink_bits_per_day": best["bits_per_day"],
            "downlink_fraction": None}
    if not sel.instruments:
        return ConstraintResult(status=NOT_EVALUATED, message="No instrument selected, so no science data "
                                                              "is generated.", value_kind=DERIVED, **base), info
    if gen["unknown_ids"]:
        return ConstraintResult(
            status=NOT_EVALUATED, affected_component_ids=gen["unknown_ids"], value_kind=DERIVED,
            message=f"Data-generation rate of {', '.join(gen['unknown_ids'])} is not published and the "
                    "scenario gives no gameplay rate, so the data balance is not evaluated. "
                    "No rate is invented.", **base), info
    if best["bits_per_day"] is None:
        return ConstraintResult(status=NOT_EVALUATED, actual_value=gen["bits_per_day"], value_kind=DERIVED,
                                message="Downlink capacity is unknown, so the data balance is not evaluated.",
                                **base), info
    kind = GAMEPLAY if GAMEPLAY in gen["value_kinds"] else MIXED
    assumptions = ["Instrument duty cycle is a gameplay parameter."]
    if GAMEPLAY in gen["value_kinds"]:
        assumptions.append("Instrument data-generation rates come from the scenario and are GAMEPLAY "
                           "ASSUMPTIONS, not published specifications.")
    generated = gen["bits_per_day"]
    fraction = 1.0 if generated <= 0 else min(1.0, best["bits_per_day"] / generated)
    info["downlink_fraction"] = round(fraction, 6)
    if fraction < 1.0:
        return ConstraintResult(
            status=WARNING, actual_value=generated, value_kind=kind, assumptions=assumptions,
            affected_component_ids=[best["radio_id"]],
            message=f"Instruments generate {generated / 8e9:.2f} GB/day but only "
                    f"{best['bits_per_day'] / 8e9:.2f} GB/day can be downlinked: about "
                    f"{(1 - fraction) * 100:.0f}% of the science data would be lost.", **base), info
    return ConstraintResult(
        status=PASS, actual_value=generated, value_kind=kind, assumptions=assumptions,
        message=f"All {generated / 8e9:.2f} GB/day of science data fits in the "
                f"{best['bits_per_day'] / 8e9:.2f} GB/day downlink.", **base), info
