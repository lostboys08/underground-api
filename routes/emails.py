"""
Email routes for sending emails using Resend API.
"""
import logging
from typing import Dict, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from services.email_service import EmailService
from config.supabase_client import get_service_client
import urllib.parse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/emails", tags=["emails"])


class TicketEmailRequest(BaseModel):
    to_emails: List[str]
    ticket_number: str
    ticket_details: Dict
    email_type: str = "notification"


class InvitationEmailRequest(BaseModel):
    email: EmailStr
    name: str
    role: str
    companyId: int


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
    
    Requires API key authentication (X-API-Key header).
    Validates all required fields, looks up company information,
    generates invitation URL, and sends professional invitation email.
    """
    try:
        # Validate required fields
        if not request.email or not request.name or not request.role or not request.companyId:
            logger.warning(f"Missing required fields in invitation request: email={bool(request.email)}, name={bool(request.name)}, role={bool(request.role)}, companyId={bool(request.companyId)}")
            raise HTTPException(
                status_code=400,
                detail="All fields are required: email, name, role, companyId"
            )
        
        # Email format is automatically validated by Pydantic EmailStr
        
        # Validate role
        valid_roles = ["user", "admin", "manager"]
        if request.role not in valid_roles:
            logger.warning(f"Invalid role provided: {request.role}. Valid roles: {valid_roles}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}"
            )
        
        # Look up company information
        try:
            logger.info(f"Looking up company with ID: {request.companyId}")
            company_result = get_service_client().table("companies").select("name").eq("id", request.companyId).execute()
            
            if not company_result.data:
                logger.warning(f"Company with ID {request.companyId} not found")
                raise HTTPException(
                    status_code=404,
                    detail=f"Company with ID {request.companyId} not found"
                )
            
            company_name = company_result.data[0]["name"]
            logger.info(f"Found company: {company_name}")
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error looking up company {request.companyId}: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Failed to lookup company information"
            )
        
        # Generate invitation URL with proper URL encoding
        base_url = "https://app.underground-iq.com/signup"
        params = {
            "company_id": str(request.companyId),
            "email": request.email,
            "role": request.role
        }
        
        # URL encode parameters
        query_string = urllib.parse.urlencode(params)
        invite_url = f"{base_url}?{query_string}"
        logger.info(f"Generated invitation URL: {invite_url}")
        
        # Send invitation email
        result = await EmailService.send_invitation_email(
            email=request.email,
            name=request.name,
            company_name=company_name,
            role=request.role,
            invite_url=invite_url
        )
        
        logger.info(f"Successfully sent invitation email to {request.email} for {company_name} with role {request.role}")
        
        return {
            "success": True,
            "message": "Invitation sent successfully",
            "email_sent": True,
            "invite_url": invite_url
        }
        
    except HTTPException:
        raise
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
