"""
Lead management API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlmodel import Session, select
from typing import Optional
from datetime import datetime
from pydantic import BaseModel
from app.core.database import get_session
from app.models.lead import Lead, LeadStatus
from app.tasks.follow_up_tasks import schedule_follow_up_sequence
import json

router = APIRouter(prefix="/leads", tags=["leads"])


class LeadResponse(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    first_name: Optional[str]
    last_name: Optional[str]
    phone: str
    email: Optional[str]
    state: Optional[str]
    status: str
    score: Optional[int]
    priority: Optional[str]
    estimated_settlement_min: Optional[float]
    estimated_settlement_max: Optional[float]
    accident_type: Optional[str]
    accident_date: Optional[datetime]
    injury_severity: Optional[str]
    ai_summary: Optional[str]
    disqualification_reason: Optional[str]
    source: Optional[str]

    class Config:
        from_attributes = True


class LeadDetailResponse(LeadResponse):
    score_breakdown: Optional[dict]
    settlement_notes: Optional[str]
    accident_description: Optional[str]
    at_fault_party: Optional[str]
    liability_clarity: Optional[str]
    police_report_filed: Optional[bool]
    injury_description: Optional[str]
    received_medical_treatment: Optional[bool]
    still_treating: Optional[bool]
    estimated_medical_bills: Optional[float]
    at_fault_insurance: Optional[str]
    prior_attorney: Optional[bool]


class LeadUpdateRequest(BaseModel):
    status: Optional[LeadStatus] = None
    score: Optional[int] = None
    priority: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None


class LeadCreateRequest(BaseModel):
    phone: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    status: Optional[LeadStatus] = LeadStatus.NEW
    source: Optional[str] = "manual"


@router.post("/", response_model=LeadResponse)
def create_lead(body: LeadCreateRequest, session: Session = Depends(get_session)):
    existing = session.exec(select(Lead).where(Lead.phone == body.phone)).first()
    if existing:
        return existing
    lead = Lead(**body.dict())
    lead.updated_at = datetime.utcnow()
    session.add(lead)
    session.commit()
    session.refresh(lead)
    return lead


@router.get("/", response_model=list[LeadResponse])
def list_leads(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    session: Session = Depends(get_session),
):
    query = select(Lead)
    if status:
        query = query.where(Lead.status == status)
    if priority:
        query = query.where(Lead.priority == priority)
    query = query.order_by(Lead.score.desc()).offset(offset).limit(limit)
    leads = session.exec(query).all()
    return leads


@router.get("/hot", response_model=list[LeadResponse])
def get_hot_leads(session: Session = Depends(get_session)):
    leads = session.exec(
        select(Lead)
        .where(Lead.priority == "hot", Lead.status != LeadStatus.DISQUALIFIED)
        .order_by(Lead.score.desc())
        .limit(50)
    ).all()
    return leads


@router.get("/{lead_id}", response_model=LeadDetailResponse)
def get_lead(lead_id: str, session: Session = Depends(get_session)):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    data = lead.dict()
    if data.get("score_breakdown"):
        try:
            data["score_breakdown"] = json.loads(data["score_breakdown"])
        except (json.JSONDecodeError, TypeError):
            pass
    return data


@router.patch("/{lead_id}", response_model=LeadResponse)
def update_lead(
    lead_id: str,
    update: LeadUpdateRequest,
    session: Session = Depends(get_session),
):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    update_data = update.dict(exclude_none=True)
    for k, v in update_data.items():
        setattr(lead, k, v)
    lead.updated_at = datetime.utcnow()

    session.add(lead)
    session.commit()
    session.refresh(lead)
    return lead


@router.post("/{lead_id}/trigger-followup")
def trigger_follow_up(
    lead_id: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    background_tasks.add_task(schedule_follow_up_sequence.delay, lead_id)
    return {"status": "scheduled", "lead_id": lead_id}


@router.post("/{lead_id}/disqualify")
def disqualify_lead(
    lead_id: str,
    reason: str = Query(...),
    session: Session = Depends(get_session),
):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.status = LeadStatus.DISQUALIFIED
    lead.disqualification_reason = reason
    lead.updated_at = datetime.utcnow()
    session.add(lead)
    session.commit()
    return {"status": "disqualified", "lead_id": lead_id}
