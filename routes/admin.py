"""
Admin endpoints for administrative tasks.
These routes are protected by API key authentication.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional
import logging
from services.email_service import EmailService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


class ContactFormSubmission(BaseModel):
    """Contact form submission data model"""
    name: str
    email: EmailStr
    phone: Optional[str] = None
    company: Optional[str] = None
    message: str


@router.post("/contact-submit")
async def contact_submit(form_data: ContactFormSubmission):
    """
    Contact form submission endpoint.
    Sends the form data via email to the admin team.

    Args:
        form_data: Contact form submission data

    Returns:
        dict: Success message with email status
    """
    try:
        # Prepare email content
        template_props = {
            "name": form_data.name,
            "email": form_data.email,
            "phone": form_data.phone or "Not provided",
            "company": form_data.company or "Not provided",
            "message": form_data.message
        }

        # Send email to admin team
        result = await EmailService._send_email_via_nextjs(
            to=["kai.mitchell@underground-iq.com", "hunter.bostic@underground-iq.com"],
            subject=f"New Contact Form Submission from {form_data.name}",
            template="contactForm",
            template_props=template_props,
            from_email="UndergroundIQ <notifications@underground-iq.com>",
            reply_to=form_data.email
        )

        logger.info(f"Contact form submitted successfully from {form_data.email}")

        return {
            "message": "success from your API",
            "status": "sent",
            "email_id": result.get("email_id")
        }

    except ValueError as e:
        logger.error(f"Email service error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send contact form: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error processing contact form: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing your submission"
        )
