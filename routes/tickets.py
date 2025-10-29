from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
import httpx
import asyncio
import os
from config.supabase_client import get_service_client

import logging

# Import ticket updater service with graceful error handling
try:
    from services.ticket_updater_service import update_single_ticket, TicketUpdateResult
    TICKET_UPDATE_AVAILABLE = True
    logging.info("Ticket update service loaded successfully")
except ImportError as e:
    logging.warning(f"Ticket update service unavailable: {e}")
    TICKET_UPDATE_AVAILABLE = False
    
    # Create dummy class for graceful handling when service unavailable
    class TicketUpdateResult:
        def __init__(self, success: bool, message: str, details: str = None):
            self.success = success
            self.message = message
            self.details = details
            self.updated_at = datetime.now()
    
    async def update_single_ticket(username: str, password: str, ticket_number: str):
        return TicketUpdateResult(
            success=False,
            message="Ticket update service unavailable",
            details="Service import failed"
        )

router = APIRouter(prefix="/tickets", tags=["Tickets"])


@router.post("/store-credentials/{company_id}")
async def store_bluestakes_credentials(
    company_id: int,
    username: str = Query(..., description="BlueStakes username"),
    password: str = Query(..., description="BlueStakes password")
):
    """
    Store BlueStakes credentials for a company
    """
    try:
        # Update the company with the credentials
        result = (get_service_client().table("companies")
                 .update({
                     "bluestakes_username": username,
                     "bluestakes_password": password
                 })
                 .eq("id", company_id)
                 .execute())
        
        if not result.data:
            raise HTTPException(
                status_code=404,
                detail=f"Company {company_id} not found"
            )
        
        return {
            "success": True,
            "message": f"BlueStakes credentials stored for company {company_id}",
            "company_id": company_id,
            "username": username
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error storing credentials for company {company_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error storing credentials: {str(e)}"
        )

# Pydantic models for request/response

class TicketUpdateRequest(BaseModel):
    username: str
    password: str
    ticket_number: str

class TicketUpdateResponse(BaseModel):
    success: bool
    message: str
    ticket_number: str
    updated_at: datetime
    details: Optional[str] = None

class ProjectTicketCreate(BaseModel):
    project_id: Optional[int] = None
    ticket_number: str
    replace_by_date: datetime
    old_ticket: Optional[str] = None
    is_continue_update: bool = True
    legal_date: Optional[datetime] = None
    company_id: int = 1  # Default to 1 for now


# BlueStakes API helper functions moved to utils/bluestakes.py to avoid circular imports




@router.post("/update", response_model=TicketUpdateResponse)
async def update_ticket(request: TicketUpdateRequest):
    """
    Update a single BlueStakes ticket using browser automation.
    
    Args:
        request: TicketUpdateRequest containing username, password, and ticket_number
        
    Returns:
        TicketUpdateResponse with success status and details
    """
    # Log incoming request details (without sensitive password)
    logging.info(f"=== TICKET UPDATE REQUEST START ===")
    logging.info(f"Ticket number: {request.ticket_number}")
    logging.info(f"Username: {request.username}")
    logging.info(f"Password provided: {'Yes' if request.password else 'No'}")
    logging.info(f"Request timestamp: {datetime.now().isoformat()}")
    
    try:
        # Log service availability check
        logging.info(f"Checking ticket update service availability...")
        logging.info(f"TICKET_UPDATE_AVAILABLE: {TICKET_UPDATE_AVAILABLE}")
        
        if not TICKET_UPDATE_AVAILABLE:
            logging.warning("Ticket update service is not available - returning failure response")
            response = TicketUpdateResponse(
                success=False,
                message="Ticket update service is currently unavailable",
                ticket_number=request.ticket_number,
                updated_at=datetime.now(),
                details="The ticket update service failed to initialize on this deployment"
            )
            logging.info(f"Returning unavailable service response: {response.dict()}")
            return response
        
        logging.info("Ticket update service is available - proceeding with validation")
        
        # Validate input with detailed logging
        logging.info("Validating input parameters...")
        validation_errors = []
        if not request.username:
            validation_errors.append("username is empty or None")
        if not request.password:
            validation_errors.append("password is empty or None")
        if not request.ticket_number:
            validation_errors.append("ticket_number is empty or None")
            
        if validation_errors:
            error_detail = f"Validation failed: {', '.join(validation_errors)}"
            logging.error(f"Input validation failed: {error_detail}")
            raise HTTPException(
                status_code=400,
                detail="Username, password, and ticket_number are all required"
            )
        
        logging.info("Input validation passed - calling ticket updater service")
        
        # Call the ticket updater service with detailed logging
        logging.info(f"Calling update_single_ticket for ticket: {request.ticket_number}")
        service_call_start = datetime.now()
        
        result = await update_single_ticket(
            username=request.username,
            password=request.password,
            ticket_number=request.ticket_number
        )
        
        service_call_duration = (datetime.now() - service_call_start).total_seconds()
        logging.info(f"update_single_ticket completed in {service_call_duration:.2f} seconds")
        
        # Log service result details
        logging.info(f"Service result received:")
        logging.info(f"  - Success: {result.success}")
        logging.info(f"  - Message: {result.message}")
        logging.info(f"  - Details: {result.details}")
        logging.info(f"  - Updated at: {result.updated_at}")
        
        # Construct response with logging
        logging.info("Constructing response object...")
        response = TicketUpdateResponse(
            success=result.success,
            message=result.message,
            ticket_number=request.ticket_number,
            updated_at=result.updated_at,
            details=result.details
        )
        
        # Log final response
        logging.info(f"Final response constructed:")
        logging.info(f"  - HTTP Status: 200")
        logging.info(f"  - Response body: {response.dict()}")
        logging.info(f"=== TICKET UPDATE REQUEST END ===")
        
        return response
        
    except HTTPException as http_exc:
        logging.error(f"HTTPException caught: Status {http_exc.status_code}, Detail: {http_exc.detail}")
        logging.info(f"=== TICKET UPDATE REQUEST END (HTTP ERROR) ===")
        raise
    except Exception as e:
        error_msg = f"Unexpected error updating ticket {request.ticket_number}: {str(e)}"
        logging.error(f"Unexpected exception: {error_msg}")
        logging.error(f"Exception type: {type(e).__name__}")
        logging.error(f"Exception args: {e.args}")
        logging.info(f"=== TICKET UPDATE REQUEST END (EXCEPTION) ===")
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )





