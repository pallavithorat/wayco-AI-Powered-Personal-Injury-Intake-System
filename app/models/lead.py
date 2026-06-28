from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List, TYPE_CHECKING
from datetime import datetime
from enum import Enum
import uuid

if TYPE_CHECKING:
    from app.models.call import Call
    from app.models.document import Document
    from app.models.follow_up import FollowUp
    from app.models.lor import LOR


class LeadStatus(str, Enum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    DISQUALIFIED = "disqualified"
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"
    RETAINER_SENT = "retainer_sent"
    SIGNED = "signed"


class AccidentType(str, Enum):
    AUTO = "auto"
    SLIP_AND_FALL = "slip_and_fall"
    WORKPLACE = "workplace"
    MEDICAL_MALPRACTICE = "medical_malpractice"
    PRODUCT_LIABILITY = "product_liability"
    DOG_BITE = "dog_bite"
    PEDESTRIAN = "pedestrian"
    MOTORCYCLE = "motorcycle"
    TRUCK = "truck"
    OTHER = "other"


class InjurySeverity(str, Enum):
    MINOR = "minor"           # Soft tissue, bruises
    MODERATE = "moderate"     # Fractures, whiplash
    SERIOUS = "serious"       # Surgery required, long-term tx
    CATASTROPHIC = "catastrophic"  # TBI, spinal, amputation, death


class Lead(SQLModel, table=True):
    __tablename__ = "leads"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Contact info
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: str = Field(index=True)
    email: Optional[str] = None
    state: Optional[str] = None  # jurisdiction

    # Lead status & scoring
    status: LeadStatus = Field(default=LeadStatus.NEW)
    score: Optional[int] = None          # 0-100
    score_breakdown: Optional[str] = None  # JSON string of scoring components
    priority: Optional[str] = None       # hot / warm / cold

    # Settlement estimation
    estimated_settlement_min: Optional[float] = None
    estimated_settlement_max: Optional[float] = None
    settlement_notes: Optional[str] = None

    # Accident details
    accident_type: Optional[AccidentType] = None
    accident_date: Optional[datetime] = None
    accident_description: Optional[str] = None
    accident_location: Optional[str] = None

    # Liability
    at_fault_party: Optional[str] = None
    liability_clarity: Optional[str] = None  # clear / disputed / unknown
    police_report_filed: Optional[bool] = None
    witnesses_present: Optional[bool] = None

    # Injuries
    injury_severity: Optional[InjurySeverity] = None
    injury_description: Optional[str] = None
    injury_types: Optional[str] = None  # JSON list

    # Medical treatment
    received_medical_treatment: Optional[bool] = None
    still_treating: Optional[bool] = None
    medical_provider: Optional[str] = None
    estimated_medical_bills: Optional[float] = None

    # Insurance
    has_health_insurance: Optional[bool] = None
    at_fault_insurance: Optional[str] = None
    own_insurance: Optional[str] = None
    policy_limit_known: Optional[bool] = None
    estimated_policy_limit: Optional[float] = None

    # Prior representation
    prior_attorney: Optional[bool] = None
    prior_attorney_reason: Optional[str] = None

    # Source
    source: Optional[str] = None  # inbound_call, web_form, referral
    referral_source: Optional[str] = None

    # AI notes
    ai_summary: Optional[str] = None
    disqualification_reason: Optional[str] = None

    # Relationships
    calls: List["Call"] = Relationship(back_populates="lead")
    documents: List["Document"] = Relationship(back_populates="lead")
    follow_ups: List["FollowUp"] = Relationship(back_populates="lead")
    lors: List["LOR"] = Relationship(back_populates="lead")
