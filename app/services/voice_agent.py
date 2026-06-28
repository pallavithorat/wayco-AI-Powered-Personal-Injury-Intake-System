"""
Vapi.ai voice agent management.
Handles creating/configuring the PI intake assistant and outbound calls.
"""
import httpx
from app.core.config import settings

VAPI_BASE = "https://api.vapi.ai"

HEADERS = {
    "Authorization": f"Bearer {settings.VAPI_API_KEY}",
    "Content-Type": "application/json",
}

PI_INTAKE_PROMPT = """You are a warm, professional intake specialist at a personal injury law firm.
Your goal is to gather information about the caller's accident and injuries to determine if the firm can help.

Follow this interview flow naturally (not rigidly):

1. GREETING: Introduce yourself as the intake specialist. Ask how they heard about the firm.
2. ACCIDENT: Ask about what happened — type, when, where.
3. LIABILITY: Who was at fault? Was a police report filed? Any witnesses?
4. INJURIES: What injuries did they sustain? How severe?
5. MEDICAL: Have they seen a doctor? Are they still treating? Where?
6. MEDICAL BILLS: Do they have an estimate of medical expenses so far?
7. INSURANCE: Do they have health insurance? Do they know the at-fault party's insurance?
8. PRIOR ATTORNEY: Have they spoken with any other attorneys about this case?
9. CONTACT INFO: Get their name, best phone number, email, and state they live in.
10. CLOSE: Thank them, explain next steps (attorney will call within 24 hours for qualifying cases).

Rules:
- Be empathetic and supportive — they may be in pain or distress
- Never promise outcomes or give legal advice
- If statute of limitations may be expired (accident > 2 years ago in most states), still collect info but note urgency
- If they clearly have no case (no injury, no fault), politely explain you may not be able to help but collect info anyway
- Keep each question conversational, not interrogatory
- Target call length: 4-8 minutes"""

FIRST_MESSAGE = (
    "Thank you for calling. This is Alex, the intake specialist at the firm. "
    "I'm here to gather some information about your situation so our attorneys can review your case. "
    "To start, how did you hear about us today?"
)


async def create_inbound_call_config() -> dict:
    """Returns the Vapi assistant config for inbound PI intake calls."""
    return {
        "name": "PI Intake Agent",
        "model": {
            "provider": "anthropic",
            "model": "claude-haiku-4-5-20251001",
            "systemPrompt": PI_INTAKE_PROMPT,
            "temperature": 0.6,
        },
        "voice": {
            "provider": "11labs",
            "voiceId": "21m00Tcm4TlvDq8ikWAM",  # Rachel — warm, professional
        },
        "firstMessage": FIRST_MESSAGE,
        "endCallFunctionEnabled": True,
        "endCallMessage": (
            "Thank you so much for speaking with me today. "
            "One of our attorneys will review your information and reach out within 24 hours. "
            "Please don't hesitate to call back if you have any questions. Take care."
        ),
        "serverUrl": f"{settings.APP_URL}/webhooks/vapi",
        "serverUrlSecret": settings.VAPI_WEBHOOK_SECRET,
        "transcriber": {
            "provider": "deepgram",
            "model": "nova-2",
            "language": "en-US",
        },
        "recordingEnabled": True,
        "hipaaEnabled": True,
    }


async def make_outbound_call(phone_number: str, lead_id: str, context: str = "") -> dict:
    """
    Initiates an outbound follow-up call to a lead.
    """
    outbound_prompt = f"""{PI_INTAKE_PROMPT}

CONTEXT FOR THIS CALL:
This is a follow-up call. {context}
Lead ID for tracking: {lead_id}

Start by mentioning this is a follow-up from their earlier inquiry."""

    payload = {
        "phoneNumberId": settings.VAPI_PHONE_NUMBER_ID,
        "customer": {"number": phone_number},
        "assistant": {
            "model": {
                "provider": "anthropic",
                "model": "claude-haiku-4-5-20251001",
                "systemPrompt": outbound_prompt,
            },
            "voice": {
                "provider": "11labs",
                "voiceId": "21m00Tcm4TlvDq8ikWAM",
            },
            "firstMessage": (
                "Hi, this is Alex calling from the law firm following up on your inquiry. "
                "Is now a good time to chat for a few minutes?"
            ),
            "serverUrl": f"{settings.APP_URL}/webhooks/vapi",
            "serverUrlSecret": settings.VAPI_WEBHOOK_SECRET,
            "recordingEnabled": True,
        },
        "metadata": {"lead_id": lead_id},
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{VAPI_BASE}/call/phone",
            headers=HEADERS,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()


async def get_call_details(vapi_call_id: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{VAPI_BASE}/call/{vapi_call_id}",
            headers=HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
