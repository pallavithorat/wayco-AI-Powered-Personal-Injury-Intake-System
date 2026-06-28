from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, TYPE_CHECKING
from datetime import datetime
from enum import Enum
import uuid

if TYPE_CHECKING:
    from app.models.lead import Lead


class CallDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CallStatus(str, Enum):
    INITIATED = "initiated"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NO_ANSWER = "no_answer"


class Call(SQLModel, table=True):
    __tablename__ = "calls"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    lead_id: Optional[str] = Field(default=None, foreign_key="leads.id", index=True)
    lead: Optional["Lead"] = Relationship(back_populates="calls")

    # Vapi fields
    vapi_call_id: Optional[str] = Field(default=None, index=True)
    direction: CallDirection = Field(default=CallDirection.INBOUND)
    status: CallStatus = Field(default=CallStatus.INITIATED)

    phone_number: str
    duration_seconds: Optional[int] = None
    recording_url: Optional[str] = None

    # Raw transcript from Vapi
    transcript: Optional[str] = None

    # Claude-extracted structured data (stored as JSON string)
    extracted_data: Optional[str] = None

    # Whether this call created/updated a lead record
    intake_completed: bool = Field(default=False)
    ended_at: Optional[datetime] = None
