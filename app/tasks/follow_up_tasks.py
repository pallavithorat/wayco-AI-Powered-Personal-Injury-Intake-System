"""
Celery tasks for scheduling and sending lead follow-ups.
"""
from datetime import datetime, timedelta
from sqlmodel import Session, select
from app.tasks.celery_app import celery_app
from app.core.database import engine
import app.models  # ensures all models are registered with SQLAlchemy before mapper config
from app.models.lead import Lead, LeadStatus
from app.models.follow_up import FollowUp, FollowUpChannel, FollowUpStatus, FollowUpType
from app.services.sms import send_sms, get_follow_up_sequence
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_follow_up_sms(self, follow_up_id: str):
    """Send a scheduled SMS follow-up."""
    with Session(engine) as session:
        follow_up = session.get(FollowUp, follow_up_id)
        if not follow_up:
            logger.error(f"FollowUp {follow_up_id} not found")
            return

        if follow_up.status != FollowUpStatus.PENDING:
            return

        lead = session.get(Lead, follow_up.lead_id)
        if not lead:
            return

        try:
            sid = send_sms(lead.phone, follow_up.message)
            follow_up.status = FollowUpStatus.SENT
            follow_up.sent_at = datetime.utcnow()
            follow_up.twilio_message_sid = sid
            session.add(follow_up)

            lead.updated_at = datetime.utcnow()
            session.add(lead)
            session.commit()

            logger.info(f"Follow-up sent to lead {lead.id}: {sid}")
        except Exception as exc:
            follow_up.status = FollowUpStatus.FAILED
            session.add(follow_up)
            session.commit()
            raise self.retry(exc=exc)


@celery_app.task
def schedule_follow_up_sequence(lead_id: str):
    """
    Create and schedule all follow-up messages for a lead based on their priority.
    Called immediately after a lead is created/scored.
    """
    with Session(engine) as session:
        lead = session.get(Lead, lead_id)
        if not lead or not lead.phone:
            return

        priority = lead.priority or "cold"
        sequence = get_follow_up_sequence(priority)

        name = lead.first_name or "there"
        accident_type = (lead.accident_type or "accident").replace("_", " ")

        for step in sequence:
            delay_hours = step["delay_hours"]
            message = step["message"].format(
                name=name,
                firm=settings.FIRM_NAME,
                firm_phone=settings.FIRM_PHONE,
                accident_type=accident_type,
            )
            scheduled_at = datetime.utcnow() + timedelta(hours=delay_hours)

            follow_up = FollowUp(
                lead_id=lead_id,
                channel=FollowUpChannel.SMS,
                follow_up_type=FollowUpType.INITIAL_OUTREACH,
                status=FollowUpStatus.PENDING,
                message=message,
                scheduled_at=scheduled_at,
            )
            session.add(follow_up)
            session.commit()
            session.refresh(follow_up)

            # Schedule the Celery task
            send_follow_up_sms.apply_async(
                args=[follow_up.id],
                countdown=int(delay_hours * 3600),
            )

        logger.info(f"Scheduled {len(sequence)} follow-ups for lead {lead_id} ({priority})")


@celery_app.task
def send_document_reminder(lead_id: str, document_id: str):
    """Remind a lead to upload a pending document."""
    from app.models.document import Document, DocumentStatus
    from app.services.document_service import get_document_upload_page_url

    with Session(engine) as session:
        doc = session.get(Document, document_id)
        lead = session.get(Lead, lead_id)

        if not doc or not lead:
            return

        if doc.status in (DocumentStatus.UPLOADED, DocumentStatus.VERIFIED):
            return

        name = lead.first_name or "there"
        upload_url = get_document_upload_page_url(doc.upload_token)
        message = (
            f"Hi {name}, we're still waiting on your {doc.doc_type.replace('_', ' ')}. "
            f"Please upload it here when you get a chance: {upload_url} — {settings.FIRM_NAME}"
        )

        try:
            sid = send_sms(lead.phone, message)
            follow_up = FollowUp(
                lead_id=lead_id,
                channel=FollowUpChannel.SMS,
                follow_up_type=FollowUpType.DOC_REMINDER,
                status=FollowUpStatus.SENT,
                message=message,
                sent_at=datetime.utcnow(),
                twilio_message_sid=sid,
            )
            session.add(follow_up)
            session.commit()
        except Exception as e:
            logger.error(f"Failed to send doc reminder for lead {lead_id}: {e}")
