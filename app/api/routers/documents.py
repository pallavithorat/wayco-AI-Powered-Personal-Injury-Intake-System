"""
Document collection API — request docs, handle uploads, manage status.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlmodel import Session, select
from datetime import datetime, timedelta
from app.core.database import get_session
from app.models.lead import Lead
from app.models.document import Document, DocumentType, DocumentStatus
from app.models.follow_up import FollowUp, FollowUpChannel, FollowUpStatus, FollowUpType
from app.services.document_service import (
    generate_upload_token,
    generate_s3_key,
    upload_file_to_s3,
    generate_presigned_download_url,
    get_document_upload_page_url,
    ALLOWED_MIME_TYPES,
    MAX_FILE_SIZE_MB,
)
from app.services.sms import send_document_request
from app.core.config import settings
import logging

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)


@router.post("/{lead_id}/request")
def request_document(
    lead_id: str,
    doc_type: DocumentType = Query(...),
    session: Session = Depends(get_session),
):
    """Create a document request and send SMS with upload link."""
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    upload_token = generate_upload_token()
    doc = Document(
        lead_id=lead_id,
        doc_type=doc_type,
        status=DocumentStatus.REQUESTED,
        upload_token=upload_token,
        upload_token_expires=datetime.utcnow() + timedelta(days=7),
        requested_at=datetime.utcnow(),
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)

    upload_page = get_document_upload_page_url(upload_token)
    name = lead.first_name or "there"
    accident_type = (lead.accident_type or "accident").replace("_", " ") if lead.accident_type else "accident"

    try:
        send_document_request(
            phone=lead.phone,
            name=name,
            doc_type=doc_type.value,
            upload_link=upload_page,
            accident_type=accident_type,
        )
        doc.status = DocumentStatus.LINK_SENT

        follow_up = FollowUp(
            lead_id=lead_id,
            channel=FollowUpChannel.SMS,
            follow_up_type=FollowUpType.DOC_REQUEST,
            status=FollowUpStatus.SENT,
            message=f"Document request sent: {doc_type.value}",
            sent_at=datetime.utcnow(),
        )
        session.add(follow_up)
        session.add(doc)
        session.commit()
    except Exception as e:
        logger.error(f"Failed to send doc request SMS: {e}")

    return {
        "document_id": doc.id,
        "upload_token": upload_token,
        "upload_page_url": upload_page,
        "expires_at": doc.upload_token_expires,
    }


@router.post("/upload/{upload_token}")
async def upload_document(
    upload_token: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """
    Public endpoint (no auth) for clients to upload documents via SMS link.
    """
    doc = session.exec(
        select(Document).where(Document.upload_token == upload_token)
    ).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Upload link not found or expired")

    if doc.upload_token_expires and datetime.utcnow() > doc.upload_token_expires:
        raise HTTPException(status_code=410, detail="Upload link has expired")

    if doc.status in (DocumentStatus.UPLOADED, DocumentStatus.VERIFIED):
        raise HTTPException(status_code=409, detail="Document already uploaded")

    # Validate file
    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"File type not allowed. Accepted: PDF, JPEG, PNG, TIFF, HEIC"
        )

    file_bytes = await file.read()
    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_FILE_SIZE_MB}MB)")

    # Upload to S3
    s3_key = generate_s3_key(doc.lead_id, doc.doc_type.value, file.filename or "upload")
    s3_url = upload_file_to_s3(file_bytes, s3_key, content_type)

    doc.s3_key = s3_key
    doc.s3_url = s3_url
    doc.file_name = file.filename
    doc.file_size_bytes = len(file_bytes)
    doc.mime_type = content_type
    doc.status = DocumentStatus.UPLOADED
    doc.uploaded_at = datetime.utcnow()
    session.add(doc)
    session.commit()

    logger.info(f"Document uploaded: {doc.id} for lead {doc.lead_id}")
    return {"status": "uploaded", "document_id": doc.id}


@router.get("/{lead_id}")
def list_documents(lead_id: str, session: Session = Depends(get_session)):
    docs = session.exec(
        select(Document).where(Document.lead_id == lead_id)
    ).all()
    return [
        {
            "id": d.id,
            "doc_type": d.doc_type,
            "status": d.status,
            "file_name": d.file_name,
            "uploaded_at": d.uploaded_at,
            "download_url": generate_presigned_download_url(d.s3_key) if d.s3_key else None,
        }
        for d in docs
    ]


@router.patch("/{document_id}/verify")
def verify_document(
    document_id: str,
    verified_by: str = Query(...),
    session: Session = Depends(get_session),
):
    doc = session.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.status = DocumentStatus.VERIFIED
    doc.verified_at = datetime.utcnow()
    doc.verified_by = verified_by
    session.add(doc)
    session.commit()
    return {"status": "verified", "document_id": document_id}
