from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, TYPE_CHECKING
from datetime import datetime
from enum import Enum
import uuid

if TYPE_CHECKING:
    from app.models.lead import Lead


class FollowUpChannel(str, Enum):
    SMS = "sms"
    EMAIL = "email"
    CALL = "call"


class FollowUpStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    REPLIED = "replied"


class FollowUpType(str, Enum):
    INITIAL_OUTREACH = "initial_outreach"
    DOC_REQUEST = "doc_request"
    DOC_REMINDER = "doc_reminder"
    STATUS_UPDATE = "status_update"
    RETAINER_NUDGE = "retainer_nudge"
    GENERAL = "general"


class FollowUp(SQLModel, table=True):
    __tablename__ = "follow_ups"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    lead_id: str = Field(foreign_key="leads.id", index=True)
    lead: Optional["Lead"] = Relationship(back_populates="follow_ups")

    channel: FollowUpChannel
    follow_up_type: FollowUpType = Field(default=FollowUpType.GENERAL)
    status: FollowUpStatus = Field(default=FollowUpStatus.PENDING)

    message: str
    scheduled_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None

    # Twilio SID for SMS tracking
    twilio_message_sid: Optional[str] = None

    # Reply tracking
    reply_received: bool = Field(default=False)
    reply_content: Optional[str] = None
    replied_at: Optional[datetime] = None
