"""
Twilio webhook handler for incoming SMS replies from leads.
"""
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import Response
from sqlmodel import Session, select
from app.core.database import get_session
from app.models.lead import Lead
from app.models.follow_up import FollowUp, FollowUpStatus
from datetime import datetime
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

POSITIVE_REPLIES = {"yes", "y", "yeah", "yep", "sure", "ok", "okay", "call me", "call"}
HELP_REPLIES = {"help", "info", "information"}
STOP_REPLIES = {"stop", "unsubscribe", "quit", "cancel"}


@router.post("/webhooks/twilio/sms")
async def twilio_sms_webhook(
    request: Request,
    From: str = Form(...),
    Body: str = Form(...),
    MessageSid: str = Form(...),
    session: Session = Depends(get_session),
):
    """Handle incoming SMS replies from leads."""
    phone = From.strip()
    message_body = Body.strip()
    reply_lower = message_body.lower()

    logger.info(f"Incoming SMS from {phone}: {message_body}")

    # Find lead by phone
    lead = session.exec(
        select(Lead).where(Lead.phone == phone)
    ).first()

    if not lead:
        # Unknown number — log but don't respond with firm details
        return Response(content="<?xml version='1.0'?><Response></Response>", media_type="text/xml")

    # Mark most recent pending follow-up as replied
    follow_ups = session.exec(
        select(FollowUp)
        .where(FollowUp.lead_id == lead.id, FollowUp.status == FollowUpStatus.SENT)
        .order_by(FollowUp.sent_at.desc())
    ).all()

    if follow_ups:
        latest = follow_ups[0]
        latest.reply_received = True
        latest.reply_content = message_body
        latest.replied_at = datetime.utcnow()
        latest.status = FollowUpStatus.REPLIED
        session.add(latest)

    lead.updated_at = datetime.utcnow()
    session.add(lead)
    session.commit()

    # Determine auto-response
    if any(kw in reply_lower for kw in STOP_REPLIES):
        response_text = (
            f"You've been unsubscribed from {_firm_short()} messages. "
            "Reply START to re-subscribe. You may still call us directly."
        )
    elif any(kw in reply_lower for kw in POSITIVE_REPLIES):
        response_text = (
            "Thank you! One of our team members will call you shortly. "
            "If urgent, please call us directly."
        )
        # Trigger priority callback task
        from app.tasks.follow_up_tasks import send_follow_up_sms
    elif any(kw in reply_lower for kw in HELP_REPLIES):
        response_text = (
            "We're here to help! Please call us or a team member will reach out soon. "
            "To upload documents, reply with the word DOCS."
        )
    else:
        response_text = (
            "Thank you for your message. A team member will follow up with you shortly."
        )

    twiml = f"""<?xml version="1.0"?>
<Response>
    <Message>{response_text}</Message>
</Response>"""

    return Response(content=twiml, media_type="text/xml")


def _firm_short() -> str:
    from app.core.config import settings
    return settings.FIRM_NAME
