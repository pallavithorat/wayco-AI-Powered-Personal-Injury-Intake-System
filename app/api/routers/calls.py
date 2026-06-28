"""
Call management — trigger outbound calls, view call history.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from app.core.database import get_session
from app.models.call import Call
from app.models.lead import Lead
from app.services.voice_agent import make_outbound_call
import asyncio

router = APIRouter(prefix="/calls", tags=["calls"])


@router.post("/{lead_id}/outbound")
async def trigger_outbound_call(
    lead_id: str,
    context: str = Query("", description="Context note for the call agent"),
    session: Session = Depends(get_session),
):
    """Trigger an outbound follow-up call to a lead."""
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    result = await make_outbound_call(
        phone_number=lead.phone,
        lead_id=lead_id,
        context=context,
    )
    return {
        "vapi_call_id": result.get("id"),
        "status": result.get("status"),
        "lead_id": lead_id,
    }


@router.get("/{lead_id}")
def get_lead_calls(lead_id: str, session: Session = Depends(get_session)):
    calls = session.exec(
        select(Call).where(Call.lead_id == lead_id).order_by(Call.created_at.desc())
    ).all()
    return [
        {
            "id": c.id,
            "vapi_call_id": c.vapi_call_id,
            "direction": c.direction,
            "status": c.status,
            "duration_seconds": c.duration_seconds,
            "intake_completed": c.intake_completed,
            "recording_url": c.recording_url,
            "created_at": c.created_at,
        }
        for c in calls
    ]


@router.get("/{lead_id}/transcript/{call_id}")
def get_call_transcript(lead_id: str, call_id: str, session: Session = Depends(get_session)):
    call = session.get(Call, call_id)
    if not call or call.lead_id != lead_id:
        raise HTTPException(status_code=404, detail="Call not found")
    return {"call_id": call_id, "transcript": call.transcript, "extracted_data": call.extracted_data}
