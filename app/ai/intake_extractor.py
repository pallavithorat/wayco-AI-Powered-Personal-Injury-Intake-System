"""
Extracts structured intake data from a voice call transcript using Claude.
"""
import json


def _get_client():
    from anthropic import Anthropic
    from app.core.config import settings
    return Anthropic(api_key=settings.ANTHROPIC_API_KEY)

EXTRACTION_SCHEMA = {
    "first_name": "string or null",
    "last_name": "string or null",
    "phone": "string or null",
    "email": "string or null",
    "state": "2-letter state code or null",
    "accident_type": "one of: auto, slip_and_fall, workplace, medical_malpractice, product_liability, dog_bite, pedestrian, motorcycle, truck, other — or null",
    "accident_date": "ISO date string YYYY-MM-DD or null",
    "accident_description": "brief description or null",
    "accident_location": "city/location or null",
    "at_fault_party": "who was at fault or null",
    "liability_clarity": "one of: clear, disputed, unknown — or null",
    "police_report_filed": "boolean or null",
    "witnesses_present": "boolean or null",
    "injury_severity": "one of: minor, moderate, serious, catastrophic — or null",
    "injury_description": "description of injuries or null",
    "injury_types": "list of injury types (strings) or null",
    "received_medical_treatment": "boolean or null",
    "still_treating": "boolean or null",
    "medical_provider": "provider name or null",
    "estimated_medical_bills": "number in dollars or null",
    "has_health_insurance": "boolean or null",
    "at_fault_insurance": "insurance company name or null",
    "own_insurance": "own insurance company name or null",
    "estimated_policy_limit": "number in dollars or null",
    "prior_attorney": "boolean — has the caller previously hired an attorney for this case",
    "prior_attorney_reason": "why they left prior attorney or null",
    "referral_source": "how they heard about the firm or null"
}

SYSTEM_PROMPT = """You are a legal intake specialist AI. Your job is to extract structured information
from personal injury case intake call transcripts. Extract only what was explicitly stated.
Return ONLY valid JSON with no markdown, no explanation, no preamble."""

USER_PROMPT_TEMPLATE = """Extract structured intake data from this personal injury call transcript.

Return a JSON object matching this schema:
{schema}

Rules:
- Use null for any field not mentioned in the transcript
- For injury_types, extract as a list e.g. ["whiplash", "back pain", "broken arm"]
- For estimated_medical_bills, only fill if a dollar amount was mentioned
- injury_severity: minor=soft tissue/bruises, moderate=fractures/whiplash, serious=surgery/long-term, catastrophic=TBI/spinal/amputation/death
- liability_clarity: clear=obvious who was at fault, disputed=unclear/shared fault, unknown=not discussed

TRANSCRIPT:
{transcript}"""


def extract_intake_from_transcript(transcript: str) -> dict:
    prompt = USER_PROMPT_TEMPLATE.format(
        schema=json.dumps(EXTRACTION_SCHEMA, indent=2),
        transcript=transcript
    )

    message = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    return json.loads(raw)


def generate_case_summary(extracted_data: dict, transcript: str) -> str:
    prompt = f"""Based on this personal injury intake call, write a 3-5 sentence attorney-facing case summary.
Be concise and factual. Include: accident type, liability, injuries, treatment status, and key flags.

Extracted data: {json.dumps(extracted_data, indent=2)}

Transcript excerpt: {transcript[:2000]}"""

    message = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text.strip()
