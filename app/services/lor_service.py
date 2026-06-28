"""
Letter of Representation (LOR) generation and e-signature via Dropbox Sign.
"""
import io
import tempfile
import os
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib import colors
import dropbox_sign
from dropbox_sign.api import signature_request_api
from dropbox_sign.models import (
    SignatureRequestSendRequest,
    SubSignatureRequestSigner,
    SubSigningOptions,
)
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


def generate_lor_pdf(lead: dict) -> bytes:
    """
    Generate a Letter of Representation PDF for the lead.
    Returns the PDF as bytes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=inch,
        leftMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        alignment=TA_CENTER,
        fontSize=16,
        spaceAfter=6,
    )
    header_style = ParagraphStyle(
        "Header",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=11,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=10.5,
        leading=16,
        alignment=TA_JUSTIFY,
        spaceAfter=12,
    )
    signature_style = ParagraphStyle(
        "Sig",
        parent=styles["Normal"],
        fontSize=10.5,
        spaceAfter=6,
    )

    client_name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip() or "Client"
    accident_date = lead.get("accident_date", "the date of accident")
    if accident_date and len(str(accident_date)) >= 10:
        try:
            accident_date = datetime.fromisoformat(str(accident_date)[:10]).strftime("%B %d, %Y")
        except ValueError:
            pass

    accident_type_map = {
        "auto": "motor vehicle accident",
        "slip_and_fall": "slip and fall accident",
        "workplace": "workplace accident",
        "medical_malpractice": "medical malpractice",
        "truck": "commercial truck accident",
        "motorcycle": "motorcycle accident",
        "pedestrian": "pedestrian accident",
        "dog_bite": "dog bite incident",
        "product_liability": "product liability claim",
        "other": "personal injury accident",
    }
    acc_type = accident_type_map.get(lead.get("accident_type", "other"), "personal injury accident")
    today = datetime.utcnow().strftime("%B %d, %Y")

    story = [
        Paragraph(settings.FIRM_NAME.upper(), title_style),
        Paragraph(settings.FIRM_ADDRESS, header_style),
        Paragraph(f"Tel: {settings.FIRM_PHONE} | Email: {settings.FIRM_EMAIL}", header_style),
        Paragraph(f"State Bar No.: {settings.FIRM_BAR_NUMBER}", header_style),
        Spacer(1, 0.3 * inch),
        HRFlowable(width="100%", thickness=1, color=colors.black),
        Spacer(1, 0.2 * inch),
        Paragraph("LETTER OF REPRESENTATION / RETAINER AGREEMENT", title_style),
        Spacer(1, 0.2 * inch),
        Paragraph(f"Date: {today}", body_style),
        Paragraph(f"Client: {client_name}", body_style),
        Spacer(1, 0.1 * inch),
        Paragraph(
            f"Dear {client_name},",
            body_style,
        ),
        Paragraph(
            f'This letter confirms that <b>{settings.FIRM_NAME}</b> ("the Firm") agrees to represent '
            f"you in connection with your personal injury claim arising from the {acc_type} "
            f"that occurred on or about <b>{accident_date}</b>.",
            body_style,
        ),
        Paragraph("<b>SCOPE OF REPRESENTATION</b>", body_style),
        Paragraph(
            "The Firm will represent you in pursuing all available legal remedies for injuries, "
            "damages, and losses you sustained as a result of the above-referenced incident, "
            "including but not limited to negotiations with insurance companies, filing of legal "
            "proceedings, and trial if necessary.",
            body_style,
        ),
        Paragraph("<b>CONTINGENCY FEE AGREEMENT</b>", body_style),
        Paragraph(
            "You agree to pay the Firm a contingency fee of <b>33.33%</b> of any recovery obtained "
            "on your behalf before filing of a lawsuit, and <b>40%</b> if a lawsuit is filed. "
            "If there is no recovery, you owe no attorney fees. You remain responsible for "
            "case costs and expenses regardless of outcome.",
            body_style,
        ),
        Paragraph("<b>CLIENT OBLIGATIONS</b>", body_style),
        Paragraph(
            "You agree to: (1) cooperate fully with the Firm; (2) provide all requested documents "
            "and information promptly; (3) attend all required appointments and proceedings; "
            "(4) notify the Firm of any changes in contact information, medical treatment, or "
            "employment; and (5) not discuss your case with anyone other than the Firm without consent.",
            body_style,
        ),
        Paragraph("<b>MEDICAL AUTHORIZATION</b>", body_style),
        Paragraph(
            "By signing this agreement, you authorize the Firm to obtain your medical records, "
            "bills, and other records relevant to your injuries from any healthcare provider.",
            body_style,
        ),
        Paragraph("<b>LIEN ACKNOWLEDGMENT</b>", body_style),
        Paragraph(
            "You acknowledge that medical providers, insurers, and government agencies may assert "
            "liens against your recovery. The Firm will work to negotiate such liens on your behalf.",
            body_style,
        ),
        Spacer(1, 0.3 * inch),
        Paragraph(
            "By signing below, you confirm that you have read, understood, and agree to the terms "
            "of this Letter of Representation and Retainer Agreement.",
            body_style,
        ),
        Spacer(1, 0.4 * inch),
        Paragraph("CLIENT SIGNATURE:", signature_style),
        Spacer(1, 0.5 * inch),
        HRFlowable(width="60%", thickness=1, color=colors.black),
        Paragraph(f"{client_name}", signature_style),
        Paragraph("Date: ___________________________", signature_style),
        Spacer(1, 0.4 * inch),
        Paragraph(f"FOR {settings.FIRM_NAME.upper()}:", signature_style),
        Spacer(1, 0.5 * inch),
        HRFlowable(width="60%", thickness=1, color=colors.black),
        Paragraph("Authorized Attorney", signature_style),
        Paragraph(f"Date: {today}", signature_style),
    ]

    doc.build(story)
    return buffer.getvalue()


def send_lor_for_signature(
    lead: dict,
    pdf_bytes: bytes,
    client_email: str,
    client_name: str,
) -> dict:
    """
    Send LOR PDF to client via Dropbox Sign for e-signature.
    Returns the signature request details including signing URL.
    """
    configuration = dropbox_sign.Configuration(username=settings.DROPBOX_SIGN_API_KEY)

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        with dropbox_sign.ApiClient(configuration) as api_client:
            sig_api = signature_request_api.SignatureRequestApi(api_client)

            with open(tmp_path, "rb") as pdf_file:
                data = SignatureRequestSendRequest(
                    title=f"Letter of Representation — {settings.FIRM_NAME}",
                    subject="Your Retainer Agreement is Ready to Sign",
                    message=(
                        f"Dear {client_name},\n\n"
                        f"Please review and sign your retainer agreement with {settings.FIRM_NAME}. "
                        "This document authorizes us to represent you in your personal injury case."
                    ),
                    signers=[
                        SubSignatureRequestSigner(
                            email_address=client_email,
                            name=client_name,
                            order=0,
                        )
                    ],
                    files=[pdf_file],
                    signing_options=SubSigningOptions(
                        draw=True,
                        type=True,
                        upload=True,
                        phone=False,
                        default_type="type",
                    ),
                    test_mode=settings.ENVIRONMENT != "production",
                )

                response = sig_api.signature_request_send(data)
                req = response.signature_request

                return {
                    "dropbox_sign_request_id": req.signature_request_id,
                    "signing_url": req.signing_url,
                    "details_url": req.details_url,
                    "expires_at": (datetime.utcnow() + timedelta(days=30)).isoformat(),
                }
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
