"""
Vapi.ai webhook handler.
Processes call events: call-started, call-ended, transcript.
"""
import json
import hmac
import hashlib
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Depends, BackgroundTasks
from sqlmodel import Session, select
from app.core.database import get_session
from app.core.config import settings
from app.models.call import Call, CallStatus, CallDirection
from app.models.lead import Lead, LeadStatus, AccidentType, InjurySeverity
from app.ai.intake_extractor import extract_intake_from_transcript, generate_case_summary
from app.ai.lead_scorer import score_lead, ai_enhance_score
from app.ai.settlement_estimator import ai_estimate_settlement
from app.tasks.follow_up_tasks import schedule_follow_up_sequence
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


def verify_vapi_signature(request_body: bytes, signature: str) -> bool:
    if not settings.VAPI_WEBHOOK_SECRET:
        return True  # Skip in dev if no secret configured
    expected = hmac.new(
        settings.VAPI_WEBHOOK_SECRET.encode(),
        request_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.get("/webhooks/vapi")
async def vapi_webhook_ping():
    """Vapi pings this with GET to verify the URL is reachable."""
    return {"status": "ok"}


@router.post("/webhooks/vapi")
async def vapi_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    body = await request.body()

    # Empty body = Vapi health check ping, just return ok
    if not body:
        return {"status": "ok"}

    signature = request.headers.get("x-vapi-signature", "")

    if not verify_vapi_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {"status": "ok"}  # Return 200 instead of 400 for malformed pings

    message = payload.get("message", {})
    event_type = message.get("type")
    call_data = message.get("call", {})

    vapi_call_id = call_data.get("id") or payload.get("call", {}).get("id")
    phone_number = (
        call_data.get("customer", {}).get("number")
        or payload.get("customer", {}).get("number", "")
    )

    logger.info(f"Vapi webhook received: type={event_type!r} call_id={vapi_call_id!r} phone={phone_number!r}")

    if event_type == "assistant-request":
        from app.services.voice_agent import create_inbound_call_config
        assistant_config = await create_inbound_call_config()
        return {"assistant": assistant_config}

    if event_type in ("call-started", "status-update"):
        status = call_data.get("status") or message.get("status", "")
        if event_type == "call-started" or status == "in-progress":
            existing = session.exec(
                select(Call).where(Call.vapi_call_id == vapi_call_id)
            ).first()
            if not existing and vapi_call_id:
                call = Call(
                    vapi_call_id=vapi_call_id,
                    direction=CallDirection.INBOUND,
                    status=CallStatus.IN_PROGRESS,
                    phone_number=phone_number,
                )
                session.add(call)
                session.commit()
        return {"status": "ok"}

    elif event_type in ("call-ended", "end-of-call-report"):
        # Vapi sends "end-of-call-report" (not "call-ended") when a call finishes
        artifact = message.get("artifact", {})
        recording_url = artifact.get("recordingUrl") or call_data.get("recordingUrl")

        call = session.exec(
            select(Call).where(Call.vapi_call_id == vapi_call_id)
        ).first()

        if not call:
            call = Call(
                vapi_call_id=vapi_call_id,
                direction=CallDirection.INBOUND,
                status=CallStatus.COMPLETED,
                phone_number=phone_number,
            )
            session.add(call)

        call.status = CallStatus.COMPLETED
        call.ended_at = datetime.utcnow()
        call.recording_url = recording_url

        transcript = _extract_transcript(message, call_data)
        logger.info(f"Transcript extracted ({len(transcript) if transcript else 0} chars) for call {vapi_call_id}")

        if transcript:
            call.transcript = transcript
            session.add(call)
            session.commit()
            session.refresh(call)
            background_tasks.add_task(
                process_call_intake, call.id, vapi_call_id, phone_number, transcript
            )
        else:
            logger.warning(f"No transcript found for call {vapi_call_id} — skipping intake")
            session.add(call)
            session.commit()

        return {"status": "ok"}

    elif event_type in ("transcript", "speech-update", "conversation-update", "hang"):
        return {"status": "ok"}

    else:
        logger.info(f"Unhandled Vapi event type: {event_type!r}")
        return {"status": "ok", "event": event_type}


def _extract_transcript(message: dict, call_data: dict) -> str | None:
    """Extract transcript text from various Vapi payload formats."""
    # end-of-call-report: transcript lives in artifact
    artifact = message.get("artifact", {})
    if transcript := artifact.get("transcript"):
        return transcript

    # Direct transcript string on message
    if transcript := message.get("transcript"):
        return transcript

    # Array of turns in artifact.messages or call_data.messages
    messages = artifact.get("messages") or call_data.get("messages") or message.get("messages", [])
    if messages:
        lines = []
        for m in messages:
            role = m.get("role", "unknown").capitalize()
            content = m.get("message") or m.get("content", "")
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines) if lines else None

    return None


def process_call_intake(
    call_id: str,
    vapi_call_id: str,
    phone_number: str,
    transcript: str,
):
    """
    Background task: extract intake data, score lead, estimate settlement,
    create lead record, schedule follow-ups.
    """
    from sqlmodel import Session as SyncSession
    from app.core.database import engine

    with SyncSession(engine) as db:
        call = db.get(Call, call_id)
        if not call:
            return

        # 1. Find or create lead by phone (always create, even if AI steps fail)
        lead = db.exec(
            select(Lead).where(Lead.phone == phone_number)
        ).first()
        if not lead:
            lead = Lead(phone=phone_number)
        lead.source = "inbound_call"
        lead.updated_at = datetime.utcnow()

        try:
            # 2. Extract structured data from transcript
            extracted = extract_intake_from_transcript(transcript)
            call.extracted_data = json.dumps(extracted)
            call.intake_completed = True
            _apply_extracted_to_lead(lead, extracted)
        except Exception as e:
            logger.error(f"AI extraction failed for {vapi_call_id}: {e}", exc_info=True)
            extracted = {}

        try:
            # 3. Score the lead
            scoring = score_lead(extracted)
            scoring = ai_enhance_score(extracted, scoring, transcript)
            lead.score = scoring["score"]
            lead.score_breakdown = scoring["score_breakdown"]
            lead.priority = scoring["priority"]
            lead.disqualification_reason = scoring["disqualification_reason"]

            if scoring["priority"] == "disqualified":
                lead.status = LeadStatus.DISQUALIFIED
            elif scoring["priority"] == "hot":
                lead.status = LeadStatus.HOT
            elif scoring["priority"] == "warm":
                lead.status = LeadStatus.WARM
            else:
                lead.status = LeadStatus.COLD
        except Exception as e:
            logger.error(f"Lead scoring failed for {vapi_call_id}: {e}", exc_info=True)

        try:
            # 4. Estimate settlement
            settlement = ai_estimate_settlement(extracted)
            lead.estimated_settlement_min = settlement["estimated_settlement_min"]
            lead.estimated_settlement_max = settlement["estimated_settlement_max"]
            lead.settlement_notes = settlement["settlement_notes"]
        except Exception as e:
            logger.error(f"Settlement estimation failed for {vapi_call_id}: {e}", exc_info=True)

        try:
            # 5. Generate AI summary
            lead.ai_summary = generate_case_summary(extracted, transcript)
        except Exception as e:
            logger.error(f"Case summary failed for {vapi_call_id}: {e}", exc_info=True)

        # 6. Always save the lead
        db.add(lead)
        db.commit()
        db.refresh(lead)

        # 7. Link call to lead
        call.lead_id = lead.id
        db.add(call)
        db.commit()

        logger.info(
            f"Intake processed: lead {lead.id}, score={lead.score}, priority={lead.priority}"
        )

        # 8. Schedule follow-up sequence (optional — requires Celery worker)
        try:
            if lead.status != LeadStatus.DISQUALIFIED:
                schedule_follow_up_sequence.delay(lead.id)
        except Exception as e:
            logger.warning(f"Could not queue follow-up sequence for lead {lead.id}: {e}")


def _apply_extracted_to_lead(lead: Lead, data: dict):
    """Apply extracted intake fields to the lead model."""
    field_map = {
        "first_name": "first_name",
        "last_name": "last_name",
        "email": "email",
        "state": "state",
        "accident_description": "accident_description",
        "accident_location": "accident_location",
        "at_fault_party": "at_fault_party",
        "liability_clarity": "liability_clarity",
        "police_report_filed": "police_report_filed",
        "witnesses_present": "witnesses_present",
        "injury_description": "injury_description",
        "received_medical_treatment": "received_medical_treatment",
        "still_treating": "still_treating",
        "medical_provider": "medical_provider",
        "estimated_medical_bills": "estimated_medical_bills",
        "has_health_insurance": "has_health_insurance",
        "at_fault_insurance": "at_fault_insurance",
        "own_insurance": "own_insurance",
        "estimated_policy_limit": "estimated_policy_limit",
        "prior_attorney": "prior_attorney",
        "prior_attorney_reason": "prior_attorney_reason",
        "referral_source": "referral_source",
    }

    for src, dst in field_map.items():
        val = data.get(src)
        if val is not None:
            setattr(lead, dst, val)

    # Enum fields
    if acc_type := data.get("accident_type"):
        try:
            lead.accident_type = AccidentType(acc_type)
        except ValueError:
            lead.accident_type = AccidentType.OTHER

    if severity := data.get("injury_severity"):
        try:
            lead.injury_severity = InjurySeverity(severity)
        except ValueError:
            pass

    if acc_date := data.get("accident_date"):
        try:
            lead.accident_date = datetime.fromisoformat(acc_date[:10])
        except (ValueError, TypeError):
            pass

    if injury_types := data.get("injury_types"):
        lead.injury_types = json.dumps(injury_types)
