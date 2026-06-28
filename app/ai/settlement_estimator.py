"""
Settlement range estimator for personal injury cases.

Method: Modified multiplier method
  Economic damages = medical_bills + estimated_lost_wages
  Non-economic = economic × severity_multiplier
  Gross settlement range = (economic + non-economic) × liability_factor
  Net to client ≈ gross × 0.67 (after ~33% attorney fee)
"""
import json


def _get_client():
    from anthropic import Anthropic
    from app.core.config import settings
    return Anthropic(api_key=settings.ANTHROPIC_API_KEY)

SEVERITY_MULTIPLIER = {
    "minor": (1.0, 1.5),
    "moderate": (1.5, 3.0),
    "serious": (3.0, 5.0),
    "catastrophic": (5.0, 10.0),
}

LIABILITY_FACTOR = {
    "clear": (0.85, 1.0),
    "disputed": (0.4, 0.7),
    "unknown": (0.3, 0.6),
}

ACCIDENT_TYPE_MODIFIER = {
    "auto": 1.0,
    "truck": 1.3,       # higher damages, commercial insurance
    "motorcycle": 1.2,
    "slip_and_fall": 0.8,
    "workplace": 0.9,
    "medical_malpractice": 1.5,
    "pedestrian": 1.2,
    "dog_bite": 0.9,
    "product_liability": 1.1,
    "other": 1.0,
}


def estimate_settlement(lead_data: dict) -> dict:
    severity = lead_data.get("injury_severity")
    liability = lead_data.get("liability_clarity", "unknown")
    accident_type = lead_data.get("accident_type", "other")

    med_bills = lead_data.get("estimated_medical_bills") or 0
    policy_limit = lead_data.get("estimated_policy_limit")

    # If no medical bills, estimate based on severity
    if med_bills == 0:
        severity_bill_estimate = {
            "minor": 3000,
            "moderate": 15000,
            "serious": 50000,
            "catastrophic": 150000,
        }
        med_bills = severity_bill_estimate.get(severity, 5000)

    # Lost wages (rough estimate: 3 months @ $4k/mo for serious+)
    lost_wages = 0
    if severity in ("serious", "catastrophic"):
        lost_wages = 12000
    elif severity == "moderate":
        lost_wages = 3000

    economic = med_bills + lost_wages

    mult_low, mult_high = SEVERITY_MULTIPLIER.get(severity, (1.0, 2.0))
    liab_low, liab_high = LIABILITY_FACTOR.get(liability, (0.4, 0.7))
    type_mod = ACCIDENT_TYPE_MODIFIER.get(accident_type, 1.0)

    non_econ_low = economic * mult_low
    non_econ_high = economic * mult_high

    gross_low = (economic + non_econ_low) * liab_low * type_mod
    gross_high = (economic + non_econ_high) * liab_high * type_mod

    # Cap at policy limit if known
    if policy_limit and policy_limit > 0:
        gross_high = min(gross_high, policy_limit)
        gross_low = min(gross_low, policy_limit * 0.7)

    # Round to nearest $1k
    settlement_min = round(gross_low / 1000) * 1000
    settlement_max = round(gross_high / 1000) * 1000

    if settlement_min < 0:
        settlement_min = 0
    if settlement_max < settlement_min:
        settlement_max = settlement_min

    notes = (
        f"Based on {severity or 'unspecified'} injuries, "
        f"{liability} liability, "
        f"~${med_bills:,.0f} medical bills. "
        f"Estimate is pre-attorney-fee gross range."
    )

    return {
        "estimated_settlement_min": float(settlement_min),
        "estimated_settlement_max": float(settlement_max),
        "settlement_notes": notes,
    }


def ai_estimate_settlement(lead_data: dict) -> dict:
    """
    Use Claude for a richer settlement estimate, especially for complex cases.
    Falls back to algorithmic estimate on error.
    """
    algo = estimate_settlement(lead_data)

    # Only use AI for cases with settlement > $25k (worth the API call)
    if algo["estimated_settlement_max"] < 25000:
        return algo

    prompt = f"""You are a personal injury attorney estimating the likely settlement range for a case.

Case details:
{json.dumps(lead_data, indent=2)}

Algorithmic estimate: ${algo['estimated_settlement_min']:,.0f} – ${algo['estimated_settlement_max']:,.0f}

Consider:
- Jurisdiction and local jury verdict trends
- Injury type and long-term prognosis
- Liability clarity and comparative fault risk
- Insurance availability
- Similar case precedents

Provide a refined settlement range and brief reasoning.
Respond in JSON only:
{{"min": number, "max": number, "reasoning": "string (2-3 sentences)"}}"""

    try:
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
        result = json.loads(raw.strip())
        return {
            "estimated_settlement_min": float(result.get("min", algo["estimated_settlement_min"])),
            "estimated_settlement_max": float(result.get("max", algo["estimated_settlement_max"])),
            "settlement_notes": result.get("reasoning", algo["settlement_notes"]),
        }
    except Exception:
        return algo
