"""
Lead scoring engine for personal injury cases.

Score is 0-100 across 4 components (25 pts each):
  1. Liability score      — clarity of fault
  2. Injury score         — severity and documentation
  3. Damages score        — economic and non-economic damages potential
  4. Viability score      — SOL, insurance, no prior attorney, jurisdiction

Priority tiers:
  80-100 → HOT   (call back within 1 hour)
  60-79  → WARM  (call back within 24 hours)
  40-59  → COOL  (follow-up within 72 hours)
  <40    → COLD  (disqualify or low-priority drip)
"""
import json
from typing import Optional


def _get_client():
    from anthropic import Anthropic
    from app.core.config import settings
    return Anthropic(api_key=settings.ANTHROPIC_API_KEY)

# Statute of limitations by state (years, auto/general PI)
STATE_SOL = {
    "CA": 2, "NY": 3, "TX": 2, "FL": 4, "IL": 2, "PA": 2, "OH": 2, "GA": 2,
    "NC": 3, "MI": 3, "NJ": 2, "VA": 2, "WA": 3, "AZ": 2, "MA": 3, "TN": 1,
    "IN": 2, "MO": 5, "MD": 3, "WI": 3, "MN": 2, "CO": 3, "AL": 2, "SC": 3,
    "LA": 1, "KY": 1, "OR": 2, "OK": 2, "CT": 2, "UT": 4, "NV": 2, "AR": 3,
    "MS": 3, "KS": 2, "NM": 3, "NE": 4, "WV": 2, "ID": 2, "HI": 2, "NH": 3,
    "ME": 6, "MT": 3, "RI": 3, "DE": 2, "SD": 3, "ND": 6, "AK": 2, "VT": 3,
    "WY": 4, "DC": 3,
}


def score_lead(lead_data: dict) -> dict:
    """
    Returns a dict with: score (0-100), breakdown, priority, disqualification_reason
    """
    breakdown = {}
    disqualification_reason = None

    # ─── 1. LIABILITY SCORE (0-25) ───────────────────────────────────────────
    liability_score = 0
    liability_clarity = lead_data.get("liability_clarity")
    police_report = lead_data.get("police_report_filed")
    witnesses = lead_data.get("witnesses_present")

    if liability_clarity == "clear":
        liability_score = 20
    elif liability_clarity == "disputed":
        liability_score = 10
    elif liability_clarity == "unknown":
        liability_score = 5

    if police_report:
        liability_score += 3
    if witnesses:
        liability_score += 2

    liability_score = min(liability_score, 25)
    breakdown["liability"] = liability_score

    # ─── 2. INJURY SCORE (0-25) ──────────────────────────────────────────────
    injury_score = 0
    severity = lead_data.get("injury_severity")

    severity_points = {
        "catastrophic": 20,
        "serious": 16,
        "moderate": 10,
        "minor": 5,
    }
    injury_score += severity_points.get(severity, 0)

    if lead_data.get("received_medical_treatment"):
        injury_score += 3
    if lead_data.get("still_treating"):
        injury_score += 2

    injury_score = min(injury_score, 25)
    breakdown["injury"] = injury_score

    # ─── 3. DAMAGES SCORE (0-25) ─────────────────────────────────────────────
    damages_score = 0
    med_bills = lead_data.get("estimated_medical_bills") or 0
    policy_limit = lead_data.get("estimated_policy_limit") or 0

    if med_bills >= 50000:
        damages_score += 15
    elif med_bills >= 20000:
        damages_score += 10
    elif med_bills >= 5000:
        damages_score += 6
    elif med_bills > 0:
        damages_score += 3

    # High policy limit = more recovery potential
    if policy_limit >= 100000:
        damages_score += 7
    elif policy_limit >= 50000:
        damages_score += 4
    elif policy_limit > 0:
        damages_score += 2

    # Unknown policy limit with serious injury still promising
    if not policy_limit and severity in ("serious", "catastrophic"):
        damages_score += 3

    damages_score = min(damages_score, 25)
    breakdown["damages"] = damages_score

    # ─── 4. VIABILITY SCORE (0-25) ───────────────────────────────────────────
    viability_score = 15  # base

    # Prior attorney = red flag (conflict, case issues, lower settlement)
    if lead_data.get("prior_attorney"):
        viability_score -= 8
        disqualification_reason = "Prior attorney involved — needs conflict check"

    # Insurance coverage
    if lead_data.get("at_fault_insurance"):
        viability_score += 5
    if lead_data.get("has_health_insurance"):
        viability_score += 2

    # SOL check
    state = lead_data.get("state", "").upper()
    accident_date_str = lead_data.get("accident_date")
    if state and accident_date_str:
        from datetime import datetime, date
        try:
            accident_date = date.fromisoformat(accident_date_str[:10])
            sol_years = STATE_SOL.get(state, 2)
            days_elapsed = (date.today() - accident_date).days
            sol_days = sol_years * 365
            days_remaining = sol_days - days_elapsed

            if days_remaining < 0:
                viability_score = 0
                disqualification_reason = f"Statute of limitations likely expired ({state}: {sol_years} years)"
            elif days_remaining < 60:
                viability_score -= 5  # urgent — needs fast action
            elif days_remaining < 180:
                viability_score += 0  # neutral
            else:
                viability_score += 3  # plenty of time
        except (ValueError, TypeError):
            pass

    viability_score = max(0, min(viability_score, 25))
    breakdown["viability"] = viability_score

    # ─── TOTAL ───────────────────────────────────────────────────────────────
    total = liability_score + injury_score + damages_score + viability_score

    # Hard disqualifiers
    if disqualification_reason and "expired" in disqualification_reason:
        priority = "disqualified"
    elif total >= 80:
        priority = "hot"
    elif total >= 60:
        priority = "warm"
    elif total >= 40:
        priority = "cold"
    else:
        priority = "cold"
        if not disqualification_reason:
            disqualification_reason = "Score too low to pursue"

    return {
        "score": total,
        "score_breakdown": json.dumps(breakdown),
        "priority": priority,
        "disqualification_reason": disqualification_reason,
    }


def ai_enhance_score(lead_data: dict, base_score: dict, transcript: str) -> dict:
    """
    Uses Claude to review the base score and provide a final adjusted recommendation.
    Only runs for borderline cases (score 45-75) to save cost.
    """
    score = base_score["score"]
    if not (45 <= score <= 75):
        return base_score

    prompt = f"""You are a personal injury case intake specialist reviewing a potential client.

Base algorithmic score: {score}/100
Score breakdown: {base_score['score_breakdown']}

Case details:
{json.dumps(lead_data, indent=2)}

Transcript snippet:
{transcript[:1500] if transcript else "Not available"}

Review this case and provide:
1. An adjusted score (within ±10 of the base score of {score}) if warranted
2. A brief reason for any adjustment
3. Any red flags or green flags not captured by the algorithm

Respond in JSON:
{{"adjusted_score": number, "reason": "string", "flags": ["string"]}}"""

    message = _get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        ai_result = json.loads(raw)
        adjusted = max(0, min(100, int(ai_result.get("adjusted_score", score))))
        base_score["score"] = adjusted

        if adjusted >= 80:
            base_score["priority"] = "hot"
        elif adjusted >= 60:
            base_score["priority"] = "warm"
        elif adjusted >= 40:
            base_score["priority"] = "cold"

        breakdown = json.loads(base_score["score_breakdown"])
        breakdown["ai_flags"] = ai_result.get("flags", [])
        breakdown["ai_adjustment_reason"] = ai_result.get("reason", "")
        base_score["score_breakdown"] = json.dumps(breakdown)
    except Exception:
        pass

    return base_score
