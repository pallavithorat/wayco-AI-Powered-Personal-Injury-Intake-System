"""
Letter of Representation (LOR) — generation, sending, and signature tracking.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlmodel import Session, select
from datetime import datetime
from app.core.database import get_session
from app.models.lead import Lead, LeadStatus
from app.models.lor import LOR, LORStatus
from app.services.lor_service import generate_lor_pdf, send_lor_for_signature
from app.services.sms import send_lor_link
from app.services.document_service import upload_file_to_s3, generate_presigned_download_url
from app.core.config import settings
import logging

router = APIRouter(prefix="/lors", tags=["lors"])
logger = logging.getLogger(__name__)


@router.post("/{lead_id}/generate")
def generate_and_send_lor(
    lead_id: str,
    background_tasks: BackgroundTasks,
    send_sms_notification: bool = Query(True),
    session: Session = Depends(get_session),
):
    """
    Generate LOR PDF, upload to S3, send via Dropbox Sign for e-signature,
    and send SMS to lead with signing link.
    """
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if not lead.email and not lead.phone:
        raise HTTPException(status_code=422, detail="Lead must have email or phone to send LOR")

    lead_dict = {
        "first_name": lead.first_name,
        "last_name": lead.last_name,
        "accident_type": lead.accident_type.value if lead.accident_type else None,
        "accident_date": lead.accident_date.isoformat() if lead.accident_date else None,
        "state": lead.state,
    }

    # Generate PDF
    pdf_bytes = generate_lor_pdf(lead_dict)

    # Store in S3
    client_name = f"{lead.first_name or ''} {lead.last_name or ''}".strip() or "Client"
    s3_key = f"lors/{lead_id}/lor_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf_url = upload_file_to_s3(pdf_bytes, s3_key, "application/pdf")

    lor = LOR(
        lead_id=lead_id,
        status=LORStatus.GENERATED,
        pdf_s3_key=s3_key,
        pdf_url=pdf_url,
    )

    # Send for e-signature if email available
    dropbox_error = None
    if lead.email:
        try:
            sig_data = send_lor_for_signature(
                lead=lead_dict,
                pdf_bytes=pdf_bytes,
                client_email=lead.email,
                client_name=client_name,
            )
            lor.dropbox_sign_request_id = sig_data["dropbox_sign_request_id"]
            lor.signing_url = sig_data.get("signing_url")
            lor.expires_at = datetime.fromisoformat(sig_data["expires_at"])
            lor.status = LORStatus.SENT
            lor.sent_at = datetime.utcnow()
            lor.email_sent = True
        except Exception as e:
            dropbox_error = str(e)
            logger.error(f"Dropbox Sign failed for lead {lead_id}: {e}", exc_info=True)

    session.add(lor)
    session.commit()
    session.refresh(lor)

    # Update lead status
    lead.status = LeadStatus.RETAINER_SENT
    lead.updated_at = datetime.utcnow()
    session.add(lead)
    session.commit()

    # Send SMS with signing link
    if send_sms_notification and lead.phone and (lor.signing_url or lor.pdf_url):
        try:
            send_lor_link(
                phone=lead.phone,
                name=lead.first_name or "there",
                signing_url=lor.signing_url or lor.pdf_url,
            )
            lor.sms_sent = True
            session.add(lor)
            session.commit()
        except Exception as e:
            logger.error(f"Failed to send LOR SMS for lead {lead_id}: {e}")

    return {
        "lor_id": lor.id,
        "status": lor.status,
        "pdf_url": generate_presigned_download_url(s3_key),
        "signing_url": lor.signing_url,
        "sms_sent": lor.sms_sent,
        "email_sent": lor.email_sent,
        "dropbox_error": dropbox_error,
    }


@router.post("/webhooks/dropbox-sign")
async def dropbox_sign_webhook(
    request_from_api: dict,
    session: Session = Depends(get_session),
):
    """Handle Dropbox Sign signature events."""
    event = request_from_api.get("event", {})
    event_type = event.get("event_type")
    metadata = request_from_api.get("signature_request", {})
    request_id = metadata.get("signature_request_id")

    if not request_id:
        return {"status": "ok"}

    lor = session.exec(
        select(LOR).where(LOR.dropbox_sign_request_id == request_id)
    ).first()

    if not lor:
        return {"status": "ok"}

    if event_type == "signature_request_viewed":
        lor.status = LORStatus.VIEWED
        lor.viewed_at = datetime.utcnow()

    elif event_type == "signature_request_signed":
        lor.status = LORStatus.SIGNED
        lor.signed_at = datetime.utcnow()
        lor.signed_pdf_url = metadata.get("final_copy_uri")

        # Upgrade lead to signed
        lead = session.get(Lead, lor.lead_id)
        if lead:
            lead.status = LeadStatus.SIGNED
            lead.updated_at = datetime.utcnow()
            session.add(lead)

    elif event_type == "signature_request_declined":
        lor.status = LORStatus.DECLINED

    session.add(lor)
    session.commit()
    return {"status": "ok"}


@router.get("/{lead_id}")
def get_lors(lead_id: str, session: Session = Depends(get_session)):
    lors = session.exec(select(LOR).where(LOR.lead_id == lead_id)).all()
    return lors
