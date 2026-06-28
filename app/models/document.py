from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, TYPE_CHECKING
from datetime import datetime
from enum import Enum
import uuid

if TYPE_CHECKING:
    from app.models.lead import Lead


class DocumentType(str, Enum):
    POLICE_REPORT = "police_report"
    MEDICAL_RECORDS = "medical_records"
    MEDICAL_BILLS = "medical_bills"
    INSURANCE_CARD = "insurance_card"
    ACCIDENT_PHOTOS = "accident_photos"
    INJURY_PHOTOS = "injury_photos"
    WITNESS_STATEMENT = "witness_statement"
    EMPLOYMENT_RECORDS = "employment_records"  # lost wages
    OTHER = "other"


class DocumentStatus(str, Enum):
    REQUESTED = "requested"
    LINK_SENT = "link_sent"
    UPLOADED = "uploaded"
    VERIFIED = "verified"
    REJECTED = "rejected"


class Document(SQLModel, table=True):
    __tablename__ = "documents"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    lead_id: str = Field(foreign_key="leads.id", index=True)
    lead: Optional["Lead"] = Relationship(back_populates="documents")

    doc_type: DocumentType
    status: DocumentStatus = Field(default=DocumentStatus.REQUESTED)

    # Upload link (pre-signed S3 URL sent via SMS)
    upload_token: Optional[str] = Field(default=None, index=True)
    upload_token_expires: Optional[datetime] = None

    # Storage
    s3_key: Optional[str] = None
    s3_url: Optional[str] = None
    file_name: Optional[str] = None
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None

    requested_at: Optional[datetime] = None
    uploaded_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    verified_by: Optional[str] = None
    rejection_reason: Optional[str] = None
