"""Unit tests for settlement estimator — no external dependencies."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ai.settlement_estimator import estimate_settlement


def test_catastrophic_injury_high_estimate():
    data = {
        "injury_severity": "catastrophic",
        "liability_clarity": "clear",
        "estimated_medical_bills": 200000,
        "accident_type": "truck",
    }
    result = estimate_settlement(data)
    assert result["estimated_settlement_min"] > 100000
    assert result["estimated_settlement_max"] > result["estimated_settlement_min"]


def test_policy_limit_caps_estimate():
    data = {
        "injury_severity": "serious",
        "liability_clarity": "clear",
        "estimated_medical_bills": 100000,
        "estimated_policy_limit": 50000,
        "accident_type": "auto",
    }
    result = estimate_settlement(data)
    assert result["estimated_settlement_max"] <= 50000


def test_disputed_liability_lowers_estimate():
    base = {
        "injury_severity": "moderate",
        "estimated_medical_bills": 20000,
        "accident_type": "auto",
    }
    clear = estimate_settlement({**base, "liability_clarity": "clear"})
    disputed = estimate_settlement({**base, "liability_clarity": "disputed"})
    assert clear["estimated_settlement_max"] > disputed["estimated_settlement_max"]


def test_minor_injury_low_estimate():
    data = {
        "injury_severity": "minor",
        "liability_clarity": "disputed",
        "accident_type": "slip_and_fall",
    }
    result = estimate_settlement(data)
    assert result["estimated_settlement_max"] < 20000


def test_notes_included():
    data = {"injury_severity": "moderate", "liability_clarity": "clear"}
    result = estimate_settlement(data)
    assert result["settlement_notes"]
    assert len(result["settlement_notes"]) > 10
