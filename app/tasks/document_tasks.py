"""
Document-related Celery tasks.
"""
from app.tasks.celery_app import celery_app
from datetime import datetime, timedelta
import app.models  # ensures all models are registered with SQLAlchemy before mapper config
import logging

logger = logging.getLogger(__name__)


@celery_app.task
def schedule_document_reminders(lead_id: str):
    """
    Schedule reminders for all pending document requests for a lead.
    Sends a reminder 48 hours after initial request if still not uploaded.
    """
    from sqlmodel import Session, select
    from app.core.database import engine
    from app.models.document import Document, DocumentStatus
    from app.tasks.follow_up_tasks import send_document_reminder

    with Session(engine) as session:
        pending_docs = session.exec(
            select(Document).where(
                Document.lead_id == lead_id,
                Document.status.in_([DocumentStatus.REQUESTED, DocumentStatus.LINK_SENT]),
            )
        ).all()

        for doc in pending_docs:
            send_document_reminder.apply_async(
                args=[lead_id, doc.id],
                countdown=48 * 3600,
            )

        logger.info(f"Scheduled reminders for {len(pending_docs)} pending docs for lead {lead_id}")


@celery_app.task
def expire_old_upload_tokens():
    """
    Periodic task: mark upload tokens as expired if past their expiry date.
    Run this via celery beat or a cron.
    """
    from sqlmodel import Session, select
    from app.core.database import engine
    from app.models.document import Document, DocumentStatus

    with Session(engine) as session:
        expired = session.exec(
            select(Document).where(
                Document.status == DocumentStatus.LINK_SENT,
                Document.upload_token_expires < datetime.utcnow(),
            )
        ).all()

        for doc in expired:
            doc.status = DocumentStatus.REQUESTED
            session.add(doc)

        session.commit()
        logger.info(f"Expired {len(expired)} upload tokens")
