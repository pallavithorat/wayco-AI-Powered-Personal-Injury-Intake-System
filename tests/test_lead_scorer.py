"""Unit tests for the lead scoring engine — no external dependencies required."""
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ai.lead_scorer import score_lead


def test_hot_lead_clear_liability_serious_injury():
    data = {
        "liability_clarity": "clear",
        "police_report_filed": True,
        "witnesses_present": True,
        "injury_severity": "serious",
        "received_medical_treatment": True,
        "still_treating": True,
        "estimated_medical_bills": 50000,
        "estimated_policy_limit": 100000,
        "at_fault_insurance": "State Farm",
        "prior_attorney": False,
        "state": "CA",
        "accident_date": "2025-01-15",
    }
    result = score_lead(data)
    assert result["score"] >= 80
    assert result["priority"] == "hot"
    assert result["disqualification_reason"] is None


def test_disqualified_expired_sol():
    data = {
        "liability_clarity": "clear",
        "injury_severity": "moderate",
        "state": "CA",
        "accident_date": "2020-01-01",  # > 2 years ago in CA
        "prior_attorney": False,
    }
    result = score_lead(data)
    assert result["priority"] == "disqualified"
    assert "expired" in (result["disqualification_reason"] or "").lower()


def test_cold_lead_disputed_liability_minor_injury():
    data = {
        "liability_clarity": "disputed",
        "injury_severity": "minor",
        "received_medical_treatment": False,
        "prior_attorney": False,
    }
    result = score_lead(data)
    assert result["score"] < 60
    assert result["priority"] in ("cold", "warm")


def test_prior_attorney_penalty():
    data_no_prior = {
        "liability_clarity": "clear",
        "injury_severity": "moderate",
        "at_fault_insurance": "Allstate",
        "prior_attorney": False,
    }
    data_with_prior = {**data_no_prior, "prior_attorney": True}

    score_no_prior = score_lead(data_no_prior)["score"]
    score_with_prior = score_lead(data_with_prior)["score"]
    assert score_no_prior > score_with_prior


def test_score_breakdown_has_four_components():
    import json
    data = {"liability_clarity": "clear", "injury_severity": "moderate"}
    result = score_lead(data)
    breakdown = json.loads(result["score_breakdown"])
    assert "liability" in breakdown
    assert "injury" in breakdown
    assert "damages" in breakdown
    assert "viability" in breakdown


def test_catastrophic_injury_score():
    data = {
        "liability_clarity": "clear",
        "injury_severity": "catastrophic",
        "received_medical_treatment": True,
        "still_treating": True,
        "at_fault_insurance": "Progressive",
        "prior_attorney": False,
    }
    result = score_lead(data)
    assert result["score"] >= 60
