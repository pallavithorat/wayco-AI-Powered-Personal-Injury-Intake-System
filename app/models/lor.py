from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, TYPE_CHECKING
from datetime import datetime
from enum import Enum
import uuid

if TYPE_CHECKING:
    from app.models.lead import Lead


class LORStatus(str, Enum):
    GENERATED = "generated"
    SENT = "sent"
    VIEWED = "viewed"
    SIGNED = "signed"
    DECLINED = "declined"
    EXPIRED = "expired"


class LOR(SQLModel, table=True):
    __tablename__ = "lors"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    lead_id: str = Field(foreign_key="leads.id", index=True)
    lead: Optional["Lead"] = Relationship(back_populates="lors")

    status: LORStatus = Field(default=LORStatus.GENERATED)

    # PDF stored in S3
    pdf_s3_key: Optional[str] = None
    pdf_url: Optional[str] = None

    # Dropbox Sign
    dropbox_sign_request_id: Optional[str] = None
    signing_url: Optional[str] = None

    # Timestamps
    sent_at: Optional[datetime] = None
    viewed_at: Optional[datetime] = None
    signed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    # Signed document URL
    signed_pdf_url: Optional[str] = None

    # Notification
    sms_sent: bool = Field(default=False)
    email_sent: bool = Field(default=False)
