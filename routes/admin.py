"""
Admin endpoints for administrative tasks.
These routes are protected by API key authentication.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional
import logging
from services.email_service import EmailService
from config.supabase_client import get_service_client

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
    Saves contact form data to CRM leads table.

    Args:
        form_data: Contact form submission data

    Returns:
        dict: Success message with lead ID
    """
    try:
        # Split name into first_name and last_name
        name_parts = form_data.name.strip().split(None, 1)  # Split on first whitespace
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else None

        # Save to CRM leads table
        insert_data = {
            "email": form_data.email,
            "first_name": first_name,
            "last_name": last_name,
            "company_name": form_data.company,
            "phone": form_data.phone,
            "message": form_data.message,
            "source": "website_contact_form",
            "status": "new"
        }

        db_result = (get_service_client()
                    .schema("crm")
                    .table("leads")
                    .insert(insert_data)
                    .execute())

        lead_id = None
        if db_result.data:
            lead_id = db_result.data[0].get("id")
            logger.info(f"Contact form data saved to CRM leads table with ID: {lead_id}")

        # TODO: Implement email notification functionality
        # This will send email notifications to the admin team when a new contact form is submitted
        # async def send_contact_form_email(form_data: ContactFormSubmission, lead_id: int):
        #     """
        #     Send email notification to admin team about new contact form submission.
        #
        #     Args:
        #         form_data: Contact form submission data
        #         lead_id: ID of the created lead in the database
        #     """
        #     template_props = {
        #         "name": form_data.name,
        #         "email": form_data.email,
        #         "phone": form_data.phone or "Not provided",
        #         "company": form_data.company or "Not provided",
        #         "message": form_data.message,
        #         "lead_id": lead_id
        #     }
        #
        #     result = await EmailService._send_email_via_nextjs(
        #         to=["kai.mitchell@underground-iq.com", "hunter.bostic@underground-iq.com"],
        #         subject=f"New Contact Form Submission from {form_data.name}",
        #         template="contactForm",
        #         template_props=template_props,
        #         from_email="UndergroundIQ <notifications@underground-iq.com>",
        #         reply_to=form_data.email
        #     )
        #     return result

        logger.info(f"Contact form submitted successfully from {form_data.email}")

        return {
            "message": "success from your API",
            "status": "saved",
            "lead_id": lead_id
        }

    except Exception as e:
        error_message = str(e)

        # Handle duplicate email constraint
        if "duplicate key value violates unique constraint" in error_message.lower():
            logger.warning(f"Lead already exists for email: {form_data.email}")
            raise HTTPException(
                status_code=409,
                detail=f"A contact with email {form_data.email} already exists in our system"
            )

        # Handle other database errors
        logger.error(f"Failed to save contact form submission: {error_message}")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing your submission"
        )
