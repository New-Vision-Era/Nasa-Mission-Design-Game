"""Tests for the v4 MVP engine. Run from the repository root: python -m pytest simulation/engine_v4 -q"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from simulation.engine_v4 import api, run_simulation
from simulation.engine_v4.configuration import ConfigError, load_scenario, parse_config, resolve_selection
from simulation.engine_v4.constraints import launch, mass, orbit, pointing, power, propulsion, volume
from simulation.engine_v4.data_loader import CATEGORIES, DEFAULT_PATH, Catalog, CatalogError, load_catalog
from simulation.engine_v4.mission.events import generate_events
from simulation.engine_v4.optimizer.recommend import dominates, pareto_front, recommend
from simulation.engine_v4.results import (CONDITIONAL, FAIL, FEASIBLE, HARD, INFEASIBLE, NOT_EVALUATED, PASS,
                                          SOFT, WARNING, ConstraintResult, overall_feasibility)

SCENARIO = "earth_observation_v4"
ENGINE_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return load_catalog()


@pytest.fixture(scope="module")
def raw() -> dict:
    with open(DEFAULT_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def config(**overrides) -> dict:
    base = {
        "scenario_id": SCENARIO,
        "platform_id": "gsat_50",
        "instrument_ids": ["hyperscape100"],
        "power": {"mode": "platform_payload_budget"},
        "communication_system_ids": ["endurosat_s_band_transceiver", "endurosat_x_band_transmitter"],
        "adcs_system_id": "cubespace_cubeadcs_3axis_small_star",
        "propulsion_system_id": None,
        "orbit_id": "sso_500",
        "launch_vehicle_id": "rocket_lab_electron",
    }
    base.update(overrides)
    return base


def run(cfg=None, seed=0, **params):
    return run_simulation(cfg or config(), params or None, seed)


def constraint(result: dict, cid: str) -> dict:
    found = [c for c in result["constraints"] if c["id"] == cid]
    assert found, f"constraint {cid} missing; have {[c['id'] for c in result['constraints']]}"
    return found[0]


def selection(catalog, cfg=None, **params):
    c = parse_config(cfg or config())
    return resolve_selection(c, catalog), load_scenario(SCENARIO, params or None).params


# ---------------------------------------------------------------- data
def test_dataset_loads_with_expected_counts(catalog):
    counts = {c: len(catalog.all(c)) for c in CATEGORIES}
    assert counts == {"platforms": 3, "instruments": 21, "power_systems": 17, "communication_systems": 8,
                      "propulsion_systems": 9, "adcs_systems": 7, "orbits": 5, "launch_vehicles": 7}
    assert catalog.dataset_id == "equipment_v4"
    assert catalog.issues == []


def test_component_ids_unique_within_category(raw):
    for category in CATEGORIES:
        ids = [r["id"] for r in raw[category]]
        assert len(ids) == len(set(ids)), category


def test_missing_values_remain_none(catalog):
    assert catalog.get("platforms", "gsat_20")["bus_mass_kg"] is None
    assert catalog.get("platforms", "gsat_20")["includes_power_hardware"] is None
    assert catalog.get("instruments", "argus_1000")["power_operating_w"] is None
    assert catalog.get("instruments", "tropics_tms")["mass_kg"] is None
    assert catalog.get("orbits", "sso_500")["orbital_lifetime_years"] is None


def test_source_metadata_and_v4_fields_preserved(catalog, raw):
    for category in CATEGORIES:
        for rec in raw[category]:
            assert catalog.get(category, rec["id"]) == rec  # every original field, unchanged
    adcs = catalog.get("adcs_systems", "kuleuven_kuladcs")
    assert adcs["pointing_metric"] == "one_sigma" and adcs["source_urls"]
    lv = catalog.get("launch_vehicles", "rocket_lab_electron")
    assert lv["orbit_support_basis"]["sso_500"] == "published_capacity_point" and lv["capacity_rule"]
    assert catalog.get("communication_systems", "endurosat_x_band_transmitter")["can_receive_commands"] is False


def test_invalid_records_are_skipped_not_guessed(raw):
    broken = copy.deepcopy(raw)
    broken["instruments"].append({"name": "no id"})
    broken["instruments"].append(copy.deepcopy(broken["instruments"][0]))  # duplicate id
    broken["instruments"].append({"id": "bad_mass", "mass_kg": "heavy"})
    cat = Catalog(broken)
    assert len(cat.all("instruments")) == 21
    assert cat.get("instruments", "bad_mass") is None
    assert len(cat.issues) == 3


def test_missing_category_is_an_error(raw):
    broken = copy.deepcopy(raw)
    del broken["orbits"]
    with pytest.raises(CatalogError):
        Catalog(broken)


def test_catalog_records_cannot_be_mutated_through_results(catalog):
    result = run()
    result["provenance"]["components"]["gsat_50"]["source_urls"].append("x")
    assert "x" not in catalog.get("platforms", "gsat_50")["source_urls"]


# ---------------------------------------------------------------- configuration
def test_every_selected_id_resolves(catalog):
    sel, _ = selection(catalog)
    assert sel.platform["id"] == "gsat_50" and sel.instruments[0]["id"] == "hyperscape100"


@pytest.mark.parametrize("override,field", [
    ({"platform_id": "gsat_999"}, "platform_id"),
    ({"instrument_ids": ["xray_cam"]}, "instrument_ids[0]"),
    ({"adcs_system_id": "hyperscape100"}, "adcs_system_id"),           # right id, wrong slot
    ({"instrument_ids": ["gecko", "gecko"]}, "instrument_ids[1]"),     # duplicate
    ({"power": {"mode": "platform_payload_budget", "solar_array_ids": ["gomspace_bp4"]}},
     "power.solar_array_ids[0]"),                                      # battery in a solar-array slot
    ({"power": {"mode": "player_built_power_system"}}, "power.solar_array_ids"),
])
def test_invalid_selection_rejected_with_field(catalog, override, field):
    with pytest.raises(ConfigError) as exc:
        resolve_selection(parse_config(config(**override)), catalog)
    assert field in [e["field"] for e in exc.value.errors]
    assert all(e["message"] for e in exc.value.errors)


def test_missing_required_slot_and_unknown_field_rejected():
    bad = config()
    del bad["orbit_id"]
    with pytest.raises(ConfigError):
        parse_config(bad)
    with pytest.raises(ConfigError):
        parse_config(config(budget_limit=1))


def test_zero_instruments_is_a_valid_configuration():
    result = run(config(instrument_ids=[]))
    assert result["mission"]["outcome"] == "FAILURE"
    assert result["feasibility"]["status"] != INFEASIBLE


# ---------------------------------------------------------------- mass and volume
def test_mass_passes_and_is_payload_only():
    result = run()
    c = constraint(result, "payload_mass")
    assert c["status"] == PASS
    assert c["actual_value"] == pytest.approx(1.1 + 0.61 + 0.246 + 0.396)
    assert result["resources"]["total_spacecraft_mass_kg"]["value"] is None  # bus mass unknown


def test_mass_limit_exceeded():
    c = constraint(run(config(platform_id="gsat_50", instrument_ids=["dragoneye"])), "payload_mass")
    assert c["status"] == FAIL and "dragoneye" in c["affected_component_ids"]


def test_unknown_mass_is_not_evaluated_and_not_zero():
    result = run(config(instrument_ids=["hyperscape100", "tropics_tms"]))
    c = constraint(result, "payload_mass")
    assert c["status"] == NOT_EVALUATED and c["affected_component_ids"] == ["tropics_tms"]
    assert result["margins"]["mass_margin_fraction"] is None
    assert result["feasibility"]["status"] == CONDITIONAL
    assert "payload_mass" in result["feasibility"]["hard_not_evaluated"]


def test_known_overload_fails_even_with_unknown_mass():
    c = constraint(run(config(instrument_ids=["dragoneye", "tropics_tms"])), "payload_mass")
    assert c["status"] == FAIL


def test_propulsion_mass_rule_uses_wet_mass_once(catalog):
    sel, params = selection(catalog, config(propulsion_system_id="busek_bgt_x5"))
    budget = mass.payload_mass(sel, params)
    assert {i["id"]: i["mass_kg"] for i in budget.items}["busek_bgt_x5"] == 1.5  # not 1.5 + propellant
    sel2, _ = selection(catalog, config(propulsion_system_id="vacco_puc_1u"))
    assert "vacco_puc_1u" in mass.payload_mass(sel2, params).unknown_ids  # dry mass is not a substitute


def test_unknown_dimensions_not_evaluated():
    c = constraint(run(config(instrument_ids=["multiscape100_cis"])), "payload_volume")
    assert c["status"] == NOT_EVALUATED and c["affected_component_ids"] == ["multiscape100_cis"]


def test_component_does_not_fit_envelope():
    c = constraint(run(config(platform_id="gsat_20", instrument_ids=["chameleon"])), "payload_volume")
    assert c["status"] == FAIL and c["affected_component_ids"] == ["chameleon"]


def test_fit_allows_rotation_and_handles_unknown():
    assert volume.fits_envelope([300, 100, 100], [100, 100, 300]) is True
    assert volume.fits_envelope([301, 100, 100], [100, 100, 300]) is False
    assert volume.fits_envelope(None, [100, 100, 300]) is None


def test_multiple_items_use_conservative_packing_rule():
    c = constraint(run(config(platform_id="gsat_20", instrument_ids=["gecko", "hyperscape100"])), "payload_volume")
    assert c["status"] == PASS and c["value_kind"] == "gameplay_assumption"
    tight = constraint(run(config(platform_id="gsat_20", instrument_ids=["gecko", "hyperscape100"]),
                           packing_factor=0.1), "payload_volume")
    assert tight["status"] == FAIL


def test_engine_fit_agrees_with_dataset_platform_fit(catalog):
    """Where the dataset's derived platform_fit is known and our inputs are complete, they must agree."""
    for inst in catalog.all("instruments"):
        for platform in catalog.all("platforms"):
            expected = (inst.get("platform_fit") or {}).get(platform["id"])
            fit = volume.fits_envelope(inst.get("dimensions_mm"), platform["payload_volume_mm"])
            if expected is None or fit is None or inst.get("mass_kg") is None:
                continue
            ours = fit and inst["mass_kg"] <= platform["payload_mass_capacity_kg"]
            assert ours == expected, (inst["id"], platform["id"])


# ---------------------------------------------------------------- power
def test_power_mode_a_passes():
    result = run()
    c = constraint(result, "power_budget")
    assert c["status"] == PASS and c["limit_value"] == 150
    # hyperscape 0.2*7+0.8*2.7, ADCS family max 2.3, S-band averaged over passes, X-band tx as upper bound
    tx_duty = 4 * 7.4 * 60 * 0.6 / 86400
    expected = (0.2 * 7 + 0.8 * 2.7) + 2.3 + (tx_duty * 12 + (1 - tx_duty) * 1.2) + 12
    assert c["actual_value"] == pytest.approx(expected, rel=1e-6)


def test_power_mode_a_fails():
    cfg = config(platform_id="gsat_20", propulsion_system_id="enpulsion_micro")
    c = constraint(run(cfg, propulsion_firing_duty_cycle=1.0), "power_budget")
    assert c["status"] == FAIL and c["actual_value"] > 100


def test_unknown_power_demand_is_partial_evaluation():
    result = run(config(instrument_ids=["hyperscape100", "argus_1000"]))
    c = constraint(result, "power_budget")
    assert c["status"] == NOT_EVALUATED and "argus_1000" in c["affected_component_ids"]
    assert result["margins"]["power_margin_fraction"] is None


def test_unknown_standby_uses_operating_power_never_zero(catalog):
    sel, params = selection(catalog, config(instrument_ids=["chameleon"]))
    item = [i for i in power.demand_items(sel, params) if i["id"] == "chameleon"][0]
    assert item["avg_w"] == 10 and item["upper_bound"] is True


MODE_B = {"mode": "player_built_power_system", "solar_array_ids": ["dcubed_origami_100w"],
          "battery_ids": ["space_inventor_bat28_p4"], "eps_id": "endurosat_eps_i"}


def test_mode_b_sufficient_generation():
    result = run(config(power=MODE_B))
    gen = constraint(result, "power_generation")
    assert gen["status"] == PASS
    assert gen["limit_value"] == pytest.approx(100 * (1 - 0.378) * 0.65)
    assert constraint(result, "battery_eclipse")["status"] == PASS
    assert constraint(result, "eps_output")["status"] == PASS
    assert constraint(result, "platform_power_cap")["status"] == PASS


def test_mode_b_insufficient_generation():
    cfg = config(power=dict(MODE_B, solar_array_ids=["endurosat_3u_solar_panel"]))
    c = constraint(run(cfg), "power_generation")
    assert c["status"] == FAIL and c["limit_value"] == pytest.approx(8.4 * 0.622 * 0.65)


def test_mode_b_battery_eclipse_failure():
    cfg = config(power={"mode": "player_built_power_system", "solar_array_ids": ["dcubed_origami_100w"],
                        "battery_ids": ["exa_1u_battery_22wh"], "eps_id": None})
    result = run(cfg)
    c = constraint(result, "battery_eclipse")
    assert c["status"] == FAIL and c["limit_value"] == pytest.approx(22.2 * 0.3)
    assert constraint(result, "eps_output")["status"] == WARNING  # soft: no EPS selected
    assert result["feasibility"]["status"] == INFEASIBLE


def test_no_double_counting_of_power_hardware():
    a_plain = constraint(run(), "power_budget")
    a_arrays = constraint(run(config(power={"mode": "platform_payload_budget",
                                            "solar_array_ids": ["dhv_dsa_889w"]})), "power_budget")
    # Mode A: selected arrays never raise the budget, and are not consumers
    assert a_arrays["limit_value"] == a_plain["limit_value"] == 150
    assert a_arrays["actual_value"] == a_plain["actual_value"]
    b = run(config(power=MODE_B))
    # Mode B: the platform figure is a cap, not added to generation
    assert constraint(b, "platform_power_cap")["limit_value"] == 150
    assert constraint(b, "power_generation")["limit_value"] < 100
    # the EPS's own 99 Wh pack is counted exactly once with the 100 Wh battery
    assert constraint(b, "battery_eclipse")["limit_value"] == pytest.approx((100 + 99) * 0.3)


# ---------------------------------------------------------------- communications
def test_command_capable_radio_passes():
    assert constraint(run(), "command_link")["status"] == PASS


def test_downlink_only_radio_fails_command_link():
    result = run(config(communication_system_ids=["endurosat_x_band_transmitter"]))
    assert constraint(result, "command_link")["status"] == FAIL
    assert result["feasibility"]["status"] == INFEASIBLE


def test_unknown_command_capability_is_not_evaluated():
    result = run(config(communication_system_ids=["osiris4cubesat"]), ground_station_types=["optical"])
    assert constraint(result, "command_link")["status"] == NOT_EVALUATED


def test_incompatible_ground_station():
    result = run(config(communication_system_ids=["endurosat_uhf_transceiver_ii"]),
                 ground_station_types=["x_band"])
    assert constraint(result, "ground_station_compatibility")["status"] == FAIL
    assert constraint(result, "command_link")["status"] == FAIL


def test_optical_link_needs_optical_ground_station():
    without = run(config(communication_system_ids=["cubecat"]))
    assert constraint(without, "ground_station_compatibility")["status"] == FAIL
    with_gs = run(config(communication_system_ids=["cubecat"]), ground_station_types=["optical"])
    assert constraint(with_gs, "ground_station_compatibility")["status"] == PASS
    cap = constraint(with_gs, "downlink_capacity")
    pass_s = 4 * 7.4 * 60 * 0.6
    assert cap["actual_value"] == pytest.approx(1_000_000 * 1000 * pass_s * 0.9 * 0.5)  # cloud factor applied


def test_partly_incompatible_radios_warn_only():
    result = run(config(communication_system_ids=["endurosat_s_band_transceiver", "cubecat"]))
    assert constraint(result, "ground_station_compatibility")["status"] == WARNING
    assert "ground_station_compatibility" not in result["feasibility"]["hard_failed"]


def test_downlink_capacity_formula():
    cap = constraint(run(), "downlink_capacity")
    assert cap["actual_value"] == pytest.approx(150000 * 1000 * (4 * 7.4 * 60 * 0.6) * 0.9)
    explicit = constraint(run(average_usable_pass_duration_s=300, passes_per_day=2, link_availability=1.0),
                          "downlink_capacity")
    assert explicit["actual_value"] == pytest.approx(150000 * 1000 * 600)


def test_unknown_data_generation_not_evaluated_but_capacity_known():
    result = run()
    assert constraint(result, "data_balance")["status"] == NOT_EVALUATED
    assert constraint(result, "downlink_capacity")["status"] == PASS
    assert result["resources"]["data_generated_bits_per_day"]["value"] is None


def test_gameplay_data_rate_is_used_and_labelled():
    result = run(data_generation_kbps={"hyperscape100": 20000})
    c = constraint(result, "data_balance")
    assert c["status"] == WARNING and c["value_kind"] == "gameplay_assumption"
    assert c["actual_value"] == pytest.approx(20000 * 1000 * 0.2 * 86400)
    assert result["mission"]["objectives"][1]["achieved_fraction"] < 1


def test_published_data_rate_is_used(catalog):
    result = run(config(instrument_ids=["tempest_d_radiometer"]))
    c = constraint(result, "data_balance")
    assert c["status"] == PASS and c["actual_value"] == pytest.approx(10 * 1000 * 0.2 * 86400)


# ---------------------------------------------------------------- orbit, pointing, propulsion
def test_orbit_scaling_applies_to_optical_only(catalog):
    sel, _ = selection(catalog, config(instrument_ids=["hyperscape100", "tempest_d_radiometer"],
                                       orbit_id="sso_700", launch_vehicle_id="vega_c"))
    rows = {r["id"]: r for r in orbit.instruments_at_orbit(sel)}
    assert rows["hyperscape100"]["gsd_m_at_orbit"] == pytest.approx(4.75 * 1.4)
    assert rows["hyperscape100"]["swath_km_at_orbit"] == pytest.approx(19.4 * 1.4)
    assert rows["hyperscape100"]["coverage_rate_km2_s"] == pytest.approx(19.4 * 1.4 * 6.765, rel=1e-4)
    assert rows["tempest_d_radiometer"]["scaled_with_altitude"] is False
    assert rows["tempest_d_radiometer"]["swath_km_at_orbit"] == 825


def test_orbit_summary_reports_dataset_values_and_no_lifetime():
    o = run()["orbit"]
    assert (o["altitude_km"], o["period_min"], o["max_eclipse_min"]) == (500, 94.47, 35.7)
    assert o["orbital_lifetime_years"] is None and o["value_kind"] == "derived"


def test_pointing_offset_formula():
    assert pointing.pointing_offset_m(500, 1.0) == pytest.approx(500000 * math.tan(math.radians(1.0)))
    assert pointing.pointing_offset_m(500, None) is None


def test_pointing_warning_against_swath():
    result = run(config(adcs_system_id="cubespace_cubeadcs_3axis_small"))  # 1 deg: 8.7 km vs 19.4 km swath
    c = constraint(result, "pointing_vs_swath")
    assert c["status"] == WARNING and c["severity"] == SOFT
    assert result["feasibility"]["status"] != INFEASIBLE


@pytest.mark.parametrize("adcs,expected", [
    ("bct_xact_15", PASS),                           # per_axis_worst 0.007
    ("cubespace_cubeadcs_3axis_small", FAIL),        # upper_bound 1.0
    ("kuleuven_kuladcs", NOT_EVALUATED),             # one_sigma: not comparable
    ("arcsec_arcus_adc", NOT_EVALUATED),             # unspecified: not comparable
])
def test_hard_pointing_requirement_respects_metric(adcs, expected):
    c = constraint(run(config(adcs_system_id=adcs), hard_pointing_requirement_deg=0.2), "pointing_requirement")
    assert c["status"] == expected and c["severity"] == HARD


def test_propulsion_burn_time_and_delta_v():
    assert propulsion.burn_time_s(5300, 0.00035) == pytest.approx(5300 / 0.00035)
    assert propulsion.delta_v_m_s(565, 4) == pytest.approx(141.25)
    assert propulsion.delta_v_m_s(565, None) is None
    no_mass = run(config(propulsion_system_id="busek_bgt_x5"))
    assert constraint(no_mass, "delta_v")["status"] == NOT_EVALUATED
    assert no_mass["propulsion"]["burn_time_s"] == pytest.approx(1130)
    with_mass = run(config(propulsion_system_id="busek_bgt_x5"), bus_mass_kg_assumption=40)
    total = 40 + 1.1 + 0.61 + 0.246 + 0.396 + 1.5
    assert with_mass["propulsion"]["delta_v_m_s"] == pytest.approx(565 / total, abs=1e-3)
    need = run(config(), min_delta_v_m_s=10)
    assert constraint(need, "delta_v")["status"] == FAIL


# ---------------------------------------------------------------- launch
def test_capacity_point_for_matching_orbit_and_altitude():
    c = constraint(run(bus_mass_kg_assumption=40), "launch_mass")
    assert c["status"] == PASS and c["limit_value"] == 200
    assert c["actual_value"] == pytest.approx(40 + 2.352)
    assert c["value_kind"] == "gameplay_assumption"  # rests on the bus-mass assumption


def test_launch_mass_exceeded():
    assert constraint(run(bus_mass_kg_assumption=250), "launch_mass")["status"] == FAIL


def test_unsupported_orbit_fails():
    result = run(config(launch_vehicle_id="vega_c", orbit_id="sso_500"))
    assert constraint(result, "launch_orbit_support")["status"] == FAIL
    assert result["feasibility"]["status"] == INFEASIBLE


def test_wrong_altitude_capacity_is_never_used():
    # Electron publishes SSO 500 km only; at SSO 600 km support is a gameplay assumption and no capacity applies
    result = run(config(orbit_id="sso_600"), bus_mass_kg_assumption=40)
    support = constraint(result, "launch_orbit_support")
    assert support["status"] == PASS and support["value_kind"] == "gameplay_assumption"
    c = constraint(result, "launch_mass")
    assert c["status"] == NOT_EVALUATED and c["limit_value"] is None


def test_leo_capacity_is_never_used_for_sso_or_other_altitude(catalog):
    sslv, f9 = catalog.get("launch_vehicles", "isro_sslv"), catalog.get("launch_vehicles", "spacex_falcon9_dedicated")
    sso500, leo550 = catalog.get("orbits", "sso_500"), catalog.get("orbits", "leo_mid_inclination_550")
    assert launch.matching_capacity_point(sslv, sso500)["mass_kg"] == 300   # the SSO point, not LEO 500
    assert launch.matching_capacity_point(sslv, leo550) is None            # LEO point is at 500 km, not 550
    assert launch.matching_capacity_point(f9, sso500) is None              # LEO figure never an SSO capacity
    assert launch.matching_capacity_point(f9, leo550) is None              # LEO point has no altitude


def test_missing_capacity_point_not_evaluated():
    result = run(config(launch_vehicle_id="spacex_transporter_rideshare"), bus_mass_kg_assumption=40)
    assert constraint(result, "launch_mass")["status"] == NOT_EVALUATED
    capped = run(config(launch_vehicle_id="spacex_transporter_rideshare"), bus_mass_kg_assumption=40,
                 rideshare_mass_cap_kg_assumption=100)
    assert constraint(capped, "launch_mass")["status"] == PASS


def test_unknown_total_mass_not_evaluated():
    c = constraint(run(), "launch_mass")
    assert c["status"] == NOT_EVALUATED and c["actual_value"] is None and c["limit_value"] == 200


def test_rideshare_price_model():
    unknown = run(config(launch_vehicle_id="spacex_transporter_rideshare"))
    assert unknown["resources"]["launch_price_usd"]["value"] is None
    assert constraint(unknown, "budget")["status"] == NOT_EVALUATED
    known = run(config(launch_vehicle_id="spacex_transporter_rideshare"), bus_mass_kg_assumption=60)
    mass_kg = 60 + 2.352
    assert known["resources"]["launch_price_usd"]["value"] == pytest.approx(350000 + 7000 * (mass_kg - 50))
    light = run(config(launch_vehicle_id="spacex_transporter_rideshare"), bus_mass_kg_assumption=20)
    assert light["resources"]["launch_price_usd"]["value"] == 350000


def test_unpublished_launch_price_is_not_zero():
    result = run(config(launch_vehicle_id="isro_pslv_xl"))
    assert result["resources"]["known_cost_usd"]["value"] is None
    assert constraint(result, "budget")["status"] == NOT_EVALUATED


def test_budget_exceeded():
    result = run(config(launch_vehicle_id="firefly_alpha"))
    assert constraint(result, "budget")["status"] == FAIL


# ---------------------------------------------------------------- overall
def test_feasible_configuration():
    result = run(bus_mass_kg_assumption=40)
    assert result["feasibility"] == {"status": FEASIBLE, "hard_failed": [], "hard_not_evaluated": [],
                                     "warnings": []}
    assert result["mission"]["outcome"] == "SUCCESS"


def test_infeasible_configuration_is_not_flown_and_is_flagged():
    result = run(config(instrument_ids=["dragoneye"]))
    assert result["feasibility"]["status"] == INFEASIBLE
    assert result["mission"]["launched"] is False and result["mission"]["outcome"] == "FAILURE"
    assert result["score"]["valid_for_ranking"] is False
    assert any("INFEASIBLE" in n for n in result["score"]["notes"])
    assert result["score"]["total"] < 60  # objectives and efficiency are zero


def test_conditional_configuration():
    result = run()
    assert result["feasibility"]["status"] == CONDITIONAL
    assert result["feasibility"]["hard_not_evaluated"] == ["launch_mass"]
    assert result["mission"]["conditional_launch"] is True


def test_unevaluated_hard_constraint_never_counts_as_pass():
    def r(status, severity=HARD):
        return ConstraintResult(id=status + severity, category="x", status=status, title="t", message="m",
                                severity=severity)
    assert overall_feasibility([r(PASS), r(NOT_EVALUATED)])["status"] == CONDITIONAL
    assert overall_feasibility([r(PASS), r(NOT_EVALUATED), r(FAIL)])["status"] == INFEASIBLE
    assert overall_feasibility([r(PASS), r(WARNING), r(FAIL, SOFT), r(NOT_EVALUATED, SOFT)])["status"] == FEASIBLE


@pytest.mark.parametrize("cfg", [
    config(), config(instrument_ids=[]), config(instrument_ids=["dragoneye"]),
    config(instrument_ids=["gecko"]), config(launch_vehicle_id="isro_pslv_xl", instrument_ids=["tropics_tms"]),
    config(power=MODE_B), config(orbit_id="leo_iss_400", launch_vehicle_id="spacex_falcon9_dedicated"),
])
def test_score_is_bounded(cfg):
    score = run(cfg)["score"]
    assert score["total"] is None or 0 <= score["total"] <= 100
    assert 0 <= score["completeness"] <= 1
    for cat in score["categories"]:
        assert cat["reasons"]
        if cat["evaluable"]:
            assert 0 <= cat["points"] <= cat["weight"]


def test_unevaluable_category_lowers_completeness_not_score():
    result = run(config(launch_vehicle_id="isro_pslv_xl", orbit_id="sso_600", instrument_ids=["multiscape100_cis", "tropics_tms"]))
    eff = [c for c in result["score"]["categories"] if c["id"] == "efficiency"][0]
    assert eff["evaluable"] is False and eff["points"] is None
    assert result["score"]["completeness"] == pytest.approx(0.8)


def test_efficiency_is_not_rewarded_when_objective_fails():
    result = run(config(instrument_ids=["gecko"]), bus_mass_kg_assumption=40)  # RGB only: wrong family
    eff = [c for c in result["score"]["categories"] if c["id"] == "efficiency"][0]
    assert result["mission"]["outcome"] == "FAILURE"
    assert eff["points"] == 0


def test_weights_are_configurable():
    result = run(scoring_weights={"science": 100, "objectives": 0, "reliability": 0, "efficiency": 0})
    assert result["score"]["total"] == pytest.approx(100.0)


def test_same_input_and_seed_give_same_output():
    a, b = run(seed=7, data_generation_kbps={"hyperscape100": 2000}), run(seed=7, data_generation_kbps={"hyperscape100": 2000})
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_events_are_seeded_and_explained(catalog):
    sel, params = selection(catalog)
    assert generate_events(sel, params, 3) == generate_events(sel, params, 3)
    assert any(generate_events(sel, params, s) != generate_events(sel, params, 3) for s in range(4, 10))
    off = run(events={"enabled": False})
    assert off["mission"]["events"] == []
    on = run(seed=1, events={"comm_outage_probability": 1.0}, data_generation_kbps={"hyperscape100": 2000})
    outages = [e for e in on["mission"]["events"] if e["type"] == "comm_outage"]
    assert len(outages) == 12 and all(e["value_kind"] == "gameplay_assumption" for e in outages)
    assert on["mission"]["totals"]["data_downlinked_bits"] == 0
    assert on["mission"]["outcome"] != "SUCCESS"


def test_result_is_json_serialisable_and_carries_provenance():
    result = run()
    json.dumps(result)
    prov = result["provenance"]["components"]
    assert prov["hyperscape100"]["source_urls"] and prov["hyperscape100"]["value_notes"]
    assert all(a["value_kind"] == "gameplay_assumption" for a in result["assumptions"])
    assert result["limitations"]


# ---------------------------------------------------------------- recommendations
def test_dominance_treats_unknown_as_worst():
    def c(science, cost):
        return {"objectives": {"science": science, "reliability": 1, "known_cost_usd": cost,
                               "mass_margin": 0.5, "power_margin": 0.5}}
    assert dominates(c(1.0, 5), c(0.5, 9))
    assert not dominates(c(1.0, 9), c(0.5, 5))
    assert dominates(c(1.0, 5), c(1.0, None))        # unknown cost is never as good as a known one
    assert not dominates(c(1.0, None), c(1.0, 5))
    front = pareto_front([c(1.0, 5), c(0.5, 9), c(0.5, 3)])
    assert len(front) == 2


def test_recommendations_are_non_dominated_and_not_infeasible():
    out = recommend(config(), {"bus_mass_kg_assumption": 40})
    assert 1 <= len(out["alternatives"]) <= 5
    assert out["candidates_generated"] < 20000
    for alt in out["alternatives"]:
        assert alt["feasibility"] != INFEASIBLE and alt["label"]
        run_simulation(alt["configuration"], {"bus_mass_kg_assumption": 40})  # every alternative is runnable
    for a in out["alternatives"]:
        assert not any(dominates(b, a) for b in out["alternatives"] if b is not a)


# ---------------------------------------------------------------- API layer
def test_api_run_ok_with_example_file():
    with open(ENGINE_DIR / "examples" / "example_mission.json", "r", encoding="utf-8") as fh:
        body = json.load(fh)
    status, result = api.handle_run_request(body)
    assert status == 200 and result["feasibility"]["status"] == CONDITIONAL
    for key in ("configuration", "feasibility", "resources", "constraints", "performance", "score", "mission",
                "explanations", "assumptions", "limitations", "provenance"):
        assert key in result
    for c in result["constraints"]:
        for field in ("id", "category", "status", "title", "message", "actual_value", "limit_value", "unit",
                      "affected_component_ids", "value_kind", "source_urls", "assumptions"):
            assert field in c


@pytest.mark.parametrize("body,status,code", [
    ("nope", 422, "invalid_request"),
    ({"configuration": {"scenario_id": SCENARIO}}, 422, "invalid_request"),
    ({"configuration": config(platform_id="gsat_999")}, 422, "unknown_component"),
    ({"configuration": config(scenario_id="no_such_scenario")}, 404, "not_found"),
    ({"configuration": config(scenario_id="../../etc/passwd")}, 404, "not_found"),
    ({"configuration": config(), "seed": "abc"}, 422, "invalid_request"),
    ({"configuration": config(), "scenario_parameters": {"passes_per_day": -1}}, 422, "invalid_request"),
    ({"configuration": config(), "scenario_parameters": {"not_a_parameter": 1}}, 422, "invalid_request"),
])
def test_api_errors_are_structured(body, status, code):
    got_status, got = api.handle_run_request(body)
    assert got_status == status and got["error"]["code"] == code and got["error"]["message"]


def test_api_never_exposes_internal_exceptions(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("secret stack detail")
    monkeypatch.setattr(api, "run_simulation", boom)
    status, body = api.handle_run_request({"configuration": config()})
    assert status == 500 and body["error"]["code"] == "internal_error"
    assert "secret" not in json.dumps(body)


def test_api_scenarios_lists_the_v4_scenario():
    status, body = api.handle_scenarios_request()
    assert status == 200 and [s["id"] for s in body["scenarios"]] == [SCENARIO]
    assert body["scenarios"][0]["parameters"]["bus_mass_kg_assumption"] is None


def test_api_respects_custom_data_paths(tmp_path):
    status, body = api.handle_run_request({"configuration": config()}, catalog_path=tmp_path / "missing.json")
    assert status == 500 and body["error"]["code"] == "internal_error"
    status, body = api.handle_run_request({"configuration": config()}, scenario_dir=tmp_path)
    assert status == 404 and body["error"]["code"] == "not_found"
    assert api.handle_scenarios_request(tmp_path) == (200, {"scenarios": []})


def test_api_catalog_returns_all_categories():
    status, body = api.handle_catalog_request()
    assert status == 200 and set(body["categories"]) == set(CATEGORIES)
    assert len(body["categories"]["instruments"]) == 21


# ---------------------------------------------------------------- local test page
def test_devui_serves_page_catalog_and_run():
    import threading
    import urllib.error
    import urllib.request

    from simulation.engine_v4 import devui

    server = devui.make_server(0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def post(path, payload):
        req = urllib.request.Request(base + path, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read())

    try:
        with urllib.request.urlopen(base + "/") as resp:
            assert resp.status == 200 and b"Engine v4 test bench" in resp.read()
        with urllib.request.urlopen(base + "/api/catalog") as resp:
            assert len(json.loads(resp.read())["categories"]["instruments"]) == 21
        with urllib.request.urlopen(base + "/api/scenarios") as resp:
            assert json.loads(resp.read())["scenarios"][0]["id"] == SCENARIO
        status, body = post("/api/run", {"configuration": config(), "seed": 1})
        assert status == 200 and body["feasibility"]["status"] == CONDITIONAL
        status, body = post("/api/run", {"configuration": config(platform_id="nope")})
        assert status == 422 and body["error"]["code"] == "unknown_component"
    finally:
        server.shutdown()
        server.server_close()
