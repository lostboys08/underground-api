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

# Import job functions with graceful error handling
try:
    from tasks.jobs import sync_bluestakes_tickets as job_sync_bluestakes_tickets
    JOB_SYNC_AVAILABLE = True
    logging.info("Job sync function loaded successfully")
except ImportError as e:
    import_error_msg = str(e)
    logging.warning(f"Job sync function unavailable: {e}")
    JOB_SYNC_AVAILABLE = False
    
    # Create dummy classes and functions for graceful handling
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
            details=f"Service import failed: {import_error_msg}"
        )

router = APIRouter(prefix="/tickets", tags=["Tickets"])

# Import BlueStakes API utilities
from utils.bluestakes import (
    get_bluestakes_auth_token, 
    search_bluestakes_tickets, 
    transform_bluestakes_ticket_to_project_ticket,
    ProjectTicketCreate as BlueStakesProjectTicketCreate
)

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

class ProjectTicketResponse(BaseModel):
    id: int
    project_id: Optional[int]
    ticket_number: str
    replace_by_date: datetime
    old_ticket: Optional[str]
    is_continue_update: bool
    legal_date: Optional[datetime]
    company_id: int

class BlueStakesSearchRequest(BaseModel):
    company_id: Optional[int] = 1  # Default to company 1 for now
    limit: Optional[int] = 10  # Limit to first 10 tickets
    offset: Optional[int] = 0
    # Add search parameters from the image
    sort: Optional[str] = None
    start: Optional[str] = None  # Start date
    end: Optional[str] = None    # End date
    state: Optional[str] = None  # Work area state
    county: Optional[str] = None # Work area county

@router.delete("/{ticket_id}")
async def delete_ticket(ticket_id: int):
    """
    Delete a ticket by ID
    """
    try:
        result = get_service_client().table("tickets").delete().eq("id", ticket_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Ticket not found")
        
        return {"message": f"Ticket {ticket_id} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error deleting ticket {ticket_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# BlueStakes API helper functions moved to utils/bluestakes.py to avoid circular imports



@router.post("/sync", response_model=List[ProjectTicketResponse])
async def sync_bluestakes_tickets(
    search_request: BlueStakesSearchRequest,
    user_id: str = Query(..., description="User UUID for authentication")
):
    """
    Sync BlueStakes tickets and insert them into the project_tickets table
    Gets company BlueStakes credentials and fetches first 10 tickets by default
    """
    try:
        company_id = search_request.company_id or 1
        
        # Get company's BlueStakes credentials
        company_result = (get_service_client().table("companies")
                         .select("bluestakes_username, bluestakes_password")
                         .eq("id", company_id)
                         .execute())
        
        if not company_result.data:
            raise HTTPException(status_code=404, detail=f"Company {company_id} not found")
        
        company = company_result.data[0]
        username = company.get("bluestakes_username")
        password = company.get("bluestakes_password")
        
        if not username or not password:
            raise HTTPException(
                status_code=400, 
                detail="Company does not have BlueStakes credentials configured"
            )
        
        # Get BlueStakes auth token
        token = await get_bluestakes_auth_token(username, password)
        
        # Prepare search parameters
        search_params = {
            "limit": search_request.limit or 10,
            "start": search_request.start,
            "end": search_request.end
        }
        
        # Search tickets from BlueStakes
        bluestakes_response = await search_bluestakes_tickets(token, search_params)
        
        # Process the response - handle the nested structure shown in the example
        inserted_tickets = []
        
        if isinstance(bluestakes_response, list) and len(bluestakes_response) > 0:
            # Handle the structure: [{"count": 0, "total": 0, "data": [...]}]
            for response_item in bluestakes_response:
                if isinstance(response_item, dict) and "data" in response_item and isinstance(response_item.get("data"), list):
                    for ticket_data in response_item.get("data", []):
                        if isinstance(ticket_data, dict):
                            try:
                                # Transform BlueStakes ticket to project ticket
                                project_ticket = transform_bluestakes_ticket_to_project_ticket(
                                    ticket_data, company_id
                                )
                                
                                # Insert into database
                                insert_data = {
                                    "project_id": project_ticket.project_id,
                                    "ticket_number": project_ticket.ticket_number,
                                    "replace_by_date": project_ticket.replace_by_date.isoformat(),
                                    "old_ticket": project_ticket.old_ticket,
                                    "is_continue_update": project_ticket.is_continue_update,
                                    "legal_date": project_ticket.legal_date.isoformat() if project_ticket.legal_date else None,
                                    "company_id": project_ticket.company_id
                                }
                                
                                # Insert with conflict handling (upsert on ticket_number)
                                result = (get_service_client().table("project_tickets")
                                         .upsert(insert_data, on_conflict="ticket_number")
                                         .execute())
                                
                                if result.data:
                                    inserted_tickets.extend([ProjectTicketResponse(**ticket) for ticket in result.data])
                                    
                            except Exception as e:
                                logging.error(f"Error processing ticket {ticket_data.get('ticket', 'unknown')}: {str(e)}")
                                continue
        
        return inserted_tickets
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error in search_and_insert_bluestakes_tickets: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

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


class SyncStatsResponse(BaseModel):
    companies_processed: int
    companies_failed: int
    tickets_added: int
    tickets_skipped: int
    tickets_linked: Optional[int] = 0
    errors: List[str]

class UpdatableTicketCreate(BaseModel):
    ticket_number: str

class UpdatableTicketResponse(BaseModel):
    id: int
    ticket_number: str
    created_at: datetime

class UpdatableTicketsStatsResponse(BaseModel):
    companies_processed: int
    companies_failed: int
    tickets_processed: int
    tickets_checked: int
    tickets_added: int
    api_failures: int
    errors: List[str]


@router.post("/sync-job", response_model=SyncStatsResponse)
async def sync_bluestakes_tickets_job(
    company_id: Optional[int] = Query(default=None, description="Company ID to sync. If not provided, syncs all companies"),
    days_back: int = Query(default=28, description="Number of days to look back for tickets")
):
    """
    Sync BlueStakes tickets using the background job function.
    Can sync all companies or a specific company.
    Uses 28-day lookback by default for new company onboarding.
    """
    try:
        # Check if job sync function is available
        if not JOB_SYNC_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Job sync function is currently unavailable"
            )
        
        # Validate parameters
        if days_back < 1 or days_back > 365:
            raise HTTPException(
                status_code=400,
                detail="days_back must be between 1 and 365"
            )
        
        # Call the job function
        if company_id:
            logging.info(f"Starting sync for company {company_id} (last {days_back} days)")
        else:
            logging.info(f"Starting sync for all companies (last {days_back} days)")
        
        sync_stats = await job_sync_bluestakes_tickets(
            company_id=company_id,
            days_back=days_back
        )
        
        return SyncStatsResponse(**sync_stats)
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error in sync job: {str(e)}"
        logging.error(error_msg)
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )


@router.post("/sync-updatable-tickets", response_model=UpdatableTicketsStatsResponse)
async def sync_updateable_tickets_job(
    company_id: Optional[int] = Query(default=None, description="Company ID to sync. If not provided, syncs all companies")
):
    """
    Manually trigger updateable tickets sync job.
    
    This endpoint allows manual triggering of the updateable tickets sync process
    for testing or on-demand synchronization.
    
    Query Parameters:
        company_id: Optional company ID to sync (syncs all if not provided)
        
    Returns:
        UpdateableTicketsStatsResponse with sync statistics
    """
    try:
        # Import here to avoid circular imports
        from tasks.jobs import sync_updateable_tickets as job_sync_updateable_tickets
        
        if company_id:
            logging.info(f"Starting manual updateable tickets sync for company {company_id}")
        else:
            logging.info("Starting manual updateable tickets sync for all companies")
        
        sync_stats = await job_sync_updateable_tickets(company_id=company_id)
        
        return UpdatableTicketsStatsResponse(**sync_stats)
        
    except Exception as e:
        error_msg = f"Error in updateable tickets sync job: {str(e)}"
        logging.error(error_msg)
        raise HTTPException(
            status_code=500,
            detail=error_msg
        ) 