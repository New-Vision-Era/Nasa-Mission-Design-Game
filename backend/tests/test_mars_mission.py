"""Regression tests for the separate Mars rover mission engine."""
import pytest
from backend.app.services.mars_mission import calculate, simulate

VALID={"launch":"lv-standard","power":"pw-nuclear","comm":"cm-advanced",
       "landing":"ld-advanced","instruments":["ins-camera","ins-spectro","ins-drill"]}

def test_full_design_is_feasible():
    result=calculate(VALID)
    assert result["valid"] is True
    assert result["resources"]["cost"] == 97
    assert result["resources"]["mass"] == 1010
    assert result["resources"]["required"] == 550

def test_simulation_returns_four_mars_stages():
    result=simulate(VALID)
    assert [s["id"] for s in result["stages"]] == ["launch","cruise","landing","surface"]
    assert result["outcome"] == "SUCCESS"
    assert result["metrics"]["transmitted"] == 95

def test_incomplete_design_is_blocked():
    result=calculate({"instruments":[]})
    assert result["valid"] is False
    assert len(result["missing"]) == 5

def test_unknown_component_is_rejected():
    with pytest.raises(ValueError,match="Unknown launch option"):
        calculate({"launch":"not-a-rocket"})

def test_duplicate_instrument_is_rejected():
    with pytest.raises(ValueError,match="only be selected once"):
        calculate({"instruments":["ins-camera","ins-camera"]})

def test_power_shortfall_is_detected():
    design={**VALID,"power":"pw-solar"}
    result=calculate(design)
    assert result["valid"] is False
    assert next(c for c in result["checks"] if c["id"]=="power")["pass"] is False
