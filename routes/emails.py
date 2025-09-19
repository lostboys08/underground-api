"""
Email routes for sending emails using Resend API.
"""
import logging
from typing import Dict, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.email_service import EmailService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/emails", tags=["emails"])


class TicketEmailRequest(BaseModel):
    to_emails: List[str]
    ticket_number: str
    ticket_details: Dict
    email_type: str = "notification"


class InvitationEmailRequest(BaseModel):
    email: str
    company_name: str


@router.post("/test")
async def send_test_email() -> Dict:
    """
    Send a basic test email using Resend.
    This endpoint sends a simple "Hello World" email for testing purposes.
    """
    try:
        result = await EmailService.send_test_email()
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Error sending test email: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send test email: {str(e)}"
        )


@router.post("/ticket")
async def send_ticket_email(request: TicketEmailRequest) -> Dict:
    """
    Send a ticket-related notification email.
    """
    try:
        result = await EmailService.send_ticket_notification_email(
            to_emails=request.to_emails,
            ticket_number=request.ticket_number,
            ticket_details=request.ticket_details,
            email_type=request.email_type
        )
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Error sending ticket email: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send ticket email: {str(e)}"
        )


@router.post("/invitation")
async def send_invitation_email(request: InvitationEmailRequest) -> Dict:
    """
    Send an invitation email to a user to join Underground IQ.
    """
    try:
        result = await EmailService.send_invitation_email(
            email=request.email,
            company_name=request.company_name
        )
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Error sending invitation email: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send invitation email: {str(e)}"
        )


@router.get("/status")
async def email_service_status() -> Dict:
    """
    Check the status of the email service configuration.
    """
    status = EmailService.get_service_status()
    status["test_endpoint"] = "/emails/test"
    status["ticket_endpoint"] = "/emails/ticket"
    status["invitation_endpoint"] = "/emails/invitation"
    return status
