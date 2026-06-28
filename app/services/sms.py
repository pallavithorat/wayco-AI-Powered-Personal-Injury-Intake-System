"""
Twilio SMS service for follow-ups and document collection.
"""
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


def _get_twilio():
    return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

DOC_REQUEST_MESSAGES = {
    "police_report": (
        "Hi {name}, this is {firm} following up on your case. "
        "To move forward, we need a copy of the police report from your accident. "
        "Please upload it here: {upload_link} "
        "Questions? Reply to this message."
    ),
    "medical_records": (
        "Hi {name}, we need your medical records related to your {accident_type} accident "
        "to assess your case. Please upload them here: {upload_link} "
        "If you don't have them yet, reply 'HELP' and we'll guide you."
    ),
    "medical_bills": (
        "Hi {name}, to estimate the value of your case we need copies of your medical bills. "
        "Please upload them here: {upload_link}"
    ),
    "insurance_card": (
        "Hi {name}, please upload a photo of your insurance card here: {upload_link} "
        "This helps us communicate with the insurance company on your behalf."
    ),
    "accident_photos": (
        "Hi {name}, photos of the accident scene and damage are very helpful for your case. "
        "Please upload them here: {upload_link}"
    ),
    "injury_photos": (
        "Hi {name}, photos of your injuries (taken close to the time of accident) "
        "can significantly help your case. Upload them here: {upload_link}"
    ),
}

FOLLOW_UP_SEQUENCES = {
    "hot": [
        {
            "delay_hours": 0,
            "message": (
                "Hi {name}, thank you for speaking with us about your {accident_type} accident. "
                "An attorney will call you within the hour to discuss your case. "
                "– {firm}"
            ),
        },
        {
            "delay_hours": 2,
            "message": (
                "Hi {name}, we want to make sure you get the help you need. "
                "Reply YES if you'd like us to call you back, or call us at {firm_phone}."
            ),
        },
    ],
    "warm": [
        {
            "delay_hours": 1,
            "message": (
                "Hi {name}, thank you for contacting {firm} about your accident. "
                "We're reviewing your case and an attorney will reach out within 24 hours. "
                "In the meantime, reply if you have any questions."
            ),
        },
        {
            "delay_hours": 24,
            "message": (
                "Hi {name}, just checking in on your case. "
                "Are you available for a quick call today? Reply YES and we'll call you right away."
            ),
        },
        {
            "delay_hours": 72,
            "message": (
                "Hi {name}, we don't want you to miss out on the compensation you deserve. "
                "Please call us at {firm_phone} or reply to schedule a consultation."
            ),
        },
    ],
    "cold": [
        {
            "delay_hours": 24,
            "message": (
                "Hi {name}, this is {firm}. We reviewed your inquiry and want to learn more "
                "about your situation. Please call us at {firm_phone} at your convenience."
            ),
        },
        {
            "delay_hours": 168,  # 1 week
            "message": (
                "Hi {name}, just a friendly reminder that you may have legal options "
                "after your accident. Time limits apply. Call {firm_phone} for a free consultation."
            ),
        },
    ],
}

LOR_MESSAGE = (
    "Hi {name}, great news — {firm} would like to represent you in your personal injury case! "
    "Please review and sign your retainer agreement (Letter of Representation) here: {signing_url} "
    "This is a secure link. Questions? Call us at {firm_phone}."
)


def send_sms(to: str, body: str) -> str:
    """Send SMS. Returns Twilio message SID."""
    try:
        message = _get_twilio().messages.create(
            body=body,
            from_=settings.TWILIO_PHONE_NUMBER,
            to=to,
        )
        logger.info(f"SMS sent to {to}: SID={message.sid}")
        return message.sid
    except TwilioRestException as e:
        logger.error(f"Twilio error sending to {to}: {e}")
        raise


def send_document_request(
    phone: str,
    name: str,
    doc_type: str,
    upload_link: str,
    accident_type: str = "accident",
) -> str:
    template = DOC_REQUEST_MESSAGES.get(doc_type, DOC_REQUEST_MESSAGES["medical_records"])
    body = template.format(
        name=name or "there",
        firm=settings.FIRM_NAME,
        upload_link=upload_link,
        accident_type=accident_type,
    )
    return send_sms(phone, body)


def send_lor_link(phone: str, name: str, signing_url: str) -> str:
    body = LOR_MESSAGE.format(
        name=name or "there",
        firm=settings.FIRM_NAME,
        signing_url=signing_url,
        firm_phone=settings.FIRM_PHONE,
    )
    return send_sms(phone, body)


def get_follow_up_sequence(priority: str) -> list[dict]:
    return FOLLOW_UP_SEQUENCES.get(priority, FOLLOW_UP_SEQUENCES["cold"])
