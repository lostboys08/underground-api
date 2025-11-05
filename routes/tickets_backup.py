from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
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

# Import job management system
from services.job_manager import job_manager, JobStatus
from tasks.ticket_update_jobs import process_ticket_update_with_semaphore
from tasks.jobs import update_project_ticket_bluestakes_data, sync_existing_tickets_bluestakes_data

router = APIRouter(prefix="/tickets", tags=["Tickets"])


# Pydantic models for request/response



# Credential management endpoints moved to /tokens route
# async def store_bluestakes_credentials(
    company_id: int,
    username: str = Query(..., description="BlueStakes username"),
    password: str = Query(..., description="BlueStakes password")
):
    """
    Store BlueStakes credentials for a company after testing them.
    
    This endpoint:
    1. Tests credentials against BlueStakes API
    2. Encrypts password if credentials are valid
    3. Stores encrypted credentials in database
    4. Returns frontend-friendly response with validation results
    """
    # Initialize response structure for frontend
    response = {
        "success": False,
        "message": "",
        "data": {
            "company_id": company_id,
            "username": username,
            "credentials_tested": False,
            "credentials_valid": False,
            "credentials_stored": False,
            "test_error": None,
            "storage_error": None
        },
        "error": None
    }
    
    try:
        # Step 1: Validate input
        if not username or not password:
            response["error"] = "USERNAME_PASSWORD_REQUIRED"
            response["message"] = "Both username and password are required"
            raise HTTPException(status_code=400, detail=response)
        
        # Step 2: Verify company exists
        company_check = (get_service_client()
                        .table("companies")
                        .select("id, name")
                        .eq("id", company_id)
                        .execute())
        
        if not company_check.data:
            response["error"] = "COMPANY_NOT_FOUND"
            response["message"] = f"Company with ID {company_id} not found"
            raise HTTPException(status_code=404, detail=response)
        
        company_name = company_check.data[0]["name"]
        logging.info(f"Testing credentials for company {company_id} ({company_name})")
        
        # Step 3: Test credentials against BlueStakes API
        response["data"]["credentials_tested"] = True
        
        try:
            logging.info(f"Testing BlueStakes authentication for company {company_id}")
            token = await get_bluestakes_auth_token_raw(username, password)
            
            if token:
                response["data"]["credentials_valid"] = True
                logging.info(f"✓ Credentials valid for company {company_id}")
            else:
                response["data"]["credentials_valid"] = False
                response["data"]["test_error"] = "Authentication returned empty token"
                response["error"] = "INVALID_CREDENTIALS"
                response["message"] = "BlueStakes credentials are invalid - authentication failed"
                raise HTTPException(status_code=401, detail=response)
                
        except HTTPException as auth_error:
            # BlueStakes API returned an error (likely invalid credentials)
            response["data"]["credentials_valid"] = False
            response["data"]["test_error"] = str(auth_error.detail) if hasattr(auth_error, 'detail') else str(auth_error)
            response["error"] = "INVALID_CREDENTIALS"
            response["message"] = "BlueStakes credentials are invalid - please check username and password"
            logging.warning(f"❌ Invalid credentials for company {company_id}: {response['data']['test_error']}")
            raise HTTPException(status_code=401, detail=response)
            
        except Exception as auth_error:
            # Network or other error during authentication
            response["data"]["test_error"] = str(auth_error)
            response["error"] = "AUTHENTICATION_ERROR"
            response["message"] = "Unable to test credentials - BlueStakes API may be unavailable"
            logging.error(f"❌ Authentication error for company {company_id}: {str(auth_error)}")
            raise HTTPException(status_code=503, detail=response)
        
        # Step 4: Encrypt password (credentials are valid)
        try:
            encrypted_password = encrypt_password(password)
            logging.info(f"✓ Password encrypted successfully for company {company_id}")
        except EncryptionError as e:
            response["data"]["storage_error"] = str(e)
            response["error"] = "ENCRYPTION_ERROR"
            response["message"] = "Failed to encrypt password - server configuration issue"
            logging.error(f"❌ Password encryption failed for company {company_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=response)
        
        # Step 5: Store encrypted credentials in database
        try:
            result = (get_service_client().table("companies")
                     .update({
                         "bluestakes_username": username,
                         "bluestakes_password": encrypted_password
                     })
                     .eq("id", company_id)
                     .execute())
            
            if not result.data:
                response["data"]["storage_error"] = "Database update returned no data"
                response["error"] = "STORAGE_ERROR"
                response["message"] = "Failed to store credentials in database"
                raise HTTPException(status_code=500, detail=response)
            
            response["data"]["credentials_stored"] = True
            logging.info(f"✓ Encrypted credentials stored successfully for company {company_id}")
            
        except Exception as storage_error:
            response["data"]["storage_error"] = str(storage_error)
            response["error"] = "STORAGE_ERROR"
            response["message"] = "Failed to store credentials in database"
            logging.error(f"❌ Database storage failed for company {company_id}: {str(storage_error)}")
            raise HTTPException(status_code=500, detail=response)
        
        # Step 6: Success response
        response["success"] = True
        response["message"] = f"BlueStakes credentials successfully tested and stored for {company_name}"
        response["data"]["company_name"] = company_name
        
        logging.info(f"🎉 Complete success for company {company_id}: credentials tested, encrypted, and stored")
        return response
        
    except HTTPException:
        # Re-raise HTTP exceptions with our custom response format
        raise
    except Exception as e:
        # Catch any unexpected errors
        response["error"] = "UNEXPECTED_ERROR"
        response["message"] = "An unexpected error occurred while processing credentials"
        response["data"]["storage_error"] = str(e)
        logging.error(f"❌ Unexpected error for company {company_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=response)


# @router.post("/test-credentials", response_model=CredentialsStoreResponse)
# async def test_bluestakes_credentials(
    username: str = Query(..., description="BlueStakes username"),
    password: str = Query(..., description="BlueStakes password")
):
    """
    Test BlueStakes credentials without storing them.
    
    This endpoint only validates credentials against the BlueStakes API
    and returns the test results. Useful for frontend validation before
    actually storing credentials.
    """
    # Initialize response structure
    response = {
        "success": False,
        "message": "",
        "data": {
            "company_id": 0,  # Not applicable for test-only
            "username": username,
            "credentials_tested": False,
            "credentials_valid": False,
            "credentials_stored": False,  # Always false for test-only
            "test_error": None,
            "storage_error": None
        },
        "error": None
    }
    
    try:
        # Validate input
        if not username or not password:
            response["error"] = "USERNAME_PASSWORD_REQUIRED"
            response["message"] = "Both username and password are required"
            raise HTTPException(status_code=400, detail=response)
        
        # Test credentials against BlueStakes API
        response["data"]["credentials_tested"] = True
        
        try:
            logging.info(f"Testing BlueStakes authentication for username: {username}")
            token = await get_bluestakes_auth_token_raw(username, password)
            
            if token:
                response["data"]["credentials_valid"] = True
                response["success"] = True
                response["message"] = "BlueStakes credentials are valid"
                logging.info(f"✓ Credentials valid for username: {username}")
            else:
                response["data"]["credentials_valid"] = False
                response["data"]["test_error"] = "Authentication returned empty token"
                response["error"] = "INVALID_CREDENTIALS"
                response["message"] = "BlueStakes credentials are invalid - authentication failed"
                
        except HTTPException as auth_error:
            # BlueStakes API returned an error (likely invalid credentials)
            response["data"]["credentials_valid"] = False
            response["data"]["test_error"] = str(auth_error.detail) if hasattr(auth_error, 'detail') else str(auth_error)
            response["error"] = "INVALID_CREDENTIALS"
            response["message"] = "BlueStakes credentials are invalid - please check username and password"
            logging.warning(f"❌ Invalid credentials for username: {username}")
            
        except Exception as auth_error:
            # Network or other error during authentication
            response["data"]["test_error"] = str(auth_error)
            response["error"] = "AUTHENTICATION_ERROR"
            response["message"] = "Unable to test credentials - BlueStakes API may be unavailable"
            logging.error(f"❌ Authentication error for username {username}: {str(auth_error)}")
        
        return response
        
    except HTTPException:
        # Re-raise HTTP exceptions with our custom response format
        raise
    except Exception as e:
        # Catch any unexpected errors
        response["error"] = "UNEXPECTED_ERROR"
        response["message"] = "An unexpected error occurred while testing credentials"
        response["data"]["test_error"] = str(e)
        logging.error(f"❌ Unexpected error testing credentials for username {username}: {str(e)}")
        raise HTTPException(status_code=500, detail=response)


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

class TicketUpdateJobResponse(BaseModel):
    job_id: str
    status: str
    message: str
    ticket_number: str
    created_at: datetime

class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    ticket_number: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None

class ProjectTicketCreate(BaseModel):
    project_id: Optional[int] = None
    ticket_number: str
    replace_by_date: datetime
    old_ticket: Optional[str] = None
    is_continue_update: bool = True
    legal_date: Optional[datetime] = None
    company_id: int = 1  # Default to 1 for now


# BlueStakes API helper functions moved to utils/bluestakes.py to avoid circular imports




@router.post("/update", response_model=TicketUpdateJobResponse)
async def update_ticket(request: TicketUpdateRequest, background_tasks: BackgroundTasks):
    """
    Queue a ticket update job for background processing.
    
    Args:
        request: TicketUpdateRequest containing username, password, and ticket_number
        background_tasks: FastAPI background tasks for processing
        
    Returns:
        TicketUpdateJobResponse with job ID and queued status
    """
    # Log incoming request details (without sensitive password)
    logging.info(f"=== TICKET UPDATE QUEUE REQUEST START ===")
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
            raise HTTPException(
                status_code=503,
                detail="Ticket update service is currently unavailable"
            )
        
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
        
        logging.info("Input validation passed - creating job")
        
        # Create job in job manager for tracking
        job_id = job_manager.create_job(
            ticket_number=request.ticket_number,
            username=request.username
        )
        
        # Add background task with semaphore-controlled concurrency
        background_tasks.add_task(
            process_ticket_update_with_semaphore,
            job_id=job_id,
            username=request.username,
            password=request.password,
            ticket_number=request.ticket_number
        )
        
        logging.info(f"Job {job_id} created and queued for background processing")
        
        # Construct response
        response = TicketUpdateJobResponse(
            job_id=job_id,
            status="queued",
            message="Ticket update job has been queued for processing",
            ticket_number=request.ticket_number,
            created_at=datetime.now(timezone.utc)
        )
        
        logging.info(f"Returning job response: {response.dict()}")
        logging.info(f"=== TICKET UPDATE QUEUE REQUEST END ===")
        
        return response
        
    except HTTPException as http_exc:
        logging.error(f"HTTPException caught: Status {http_exc.status_code}, Detail: {http_exc.detail}")
        logging.info(f"=== TICKET UPDATE QUEUE REQUEST END (HTTP ERROR) ===")
        raise
    except Exception as e:
        error_msg = f"Unexpected error during ticket update job creation: {str(e)}"
        logging.error(f"Unexpected exception: {error_msg}")
        logging.info(f"=== TICKET UPDATE QUEUE REQUEST END (UNEXPECTED ERROR) ===")
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )


@router.get("/update/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """
    Get the status of a ticket update job.
    
    Args:
        job_id: The job ID to check
        
    Returns:
        JobStatusResponse with job status and results
    """
    logging.info(f"Job status request for job_id: {job_id}")
    
    try:
        # Get job from job manager
        job = job_manager.get_job(job_id)
        
        if not job:
            logging.warning(f"Job {job_id} not found")
            raise HTTPException(
                status_code=404,
                detail=f"Job {job_id} not found"
            )
        
        # Convert job to response format
        job_dict = job.to_dict()
        response = JobStatusResponse(
            job_id=job.id,
            status=job.status.value,
            ticket_number=job.ticket_number,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            result=job_dict.get('result')
        )
        
        logging.info(f"Returning job status for {job_id}: {job.status.value}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error retrieving job status for {job_id}: {str(e)}"
        logging.error(error_msg)
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )


@router.get("/queue/status")
async def get_queue_status():
    """
    Get the current status of the ticket update queue.
    
    Returns:
        Dictionary with queue statistics
    """
    logging.info("Queue status request received")
    
    try:
        status = job_manager.get_queue_status()
        logging.info(f"Queue status: {status}")
        return status
        
    except Exception as e:
        error_msg = f"Error retrieving queue status: {str(e)}"
        logging.error(error_msg)
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )


@router.post("/{ticket_number}/sync-bluestakes")
async def sync_ticket_bluestakes_data(
    ticket_number: str,
    background_tasks: BackgroundTasks
):
    """
    Manually sync a specific ticket with fresh Bluestakes data.
    
    This endpoint fetches comprehensive ticket data from the Bluestakes API
    and updates the project_tickets table with location, work_area (GeoJSON),
    dates, contact info, and other fields.
    
    Args:
        ticket_number: The ticket number to sync
        
    Returns:
        JSON response indicating the sync job was queued
    """
    try:
        # First, verify the ticket exists and get its company_id
        result = (get_service_client()
                 .table("project_tickets")
                 .select("company_id")
                 .eq("ticket_number", ticket_number)
                 .limit(1)
                 .execute())
        
        if not result.data:
            raise HTTPException(
                status_code=404,
                detail=f"Ticket {ticket_number} not found in database"
            )
        
        company_id = result.data[0]["company_id"]
        
        # Add the sync job to background tasks
        background_tasks.add_task(
            update_project_ticket_bluestakes_data,
            ticket_number,
            company_id
        )
        
        logging.info(f"Bluestakes data sync queued for ticket {ticket_number}")
        
        return {
            "status": "success",
            "message": f"Bluestakes data sync queued for ticket {ticket_number}",
            "ticket_number": ticket_number,
            "company_id": company_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error queueing sync for ticket {ticket_number}: {str(e)}"
        logging.error(error_msg)
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )


@router.post("/sync-all-bluestakes")
async def sync_all_tickets_bluestakes_data(
    background_tasks: BackgroundTasks,
    company_id: Optional[int] = Query(default=None, description="Company ID to sync. If not provided, syncs all companies"),
    max_age_hours: Optional[int] = Query(default=24, description="Only sync tickets older than this many hours"),
    batch_size: Optional[int] = Query(default=50, description="Number of tickets to process in each batch")
):
    """
    Manually sync all tickets (or tickets for a specific company) with fresh Bluestakes data.
    
    This endpoint updates existing tickets in the project_tickets table with comprehensive
    Bluestakes data including location, work_area (GeoJSON), dates, contact info, etc.
    
    Query Parameters:
        company_id: Optional company ID to sync (syncs all if not provided)
        max_age_hours: Only sync tickets older than this many hours (default: 24)
        batch_size: Number of tickets to process in each batch (default: 50)
        
    Returns:
        JSON response indicating the bulk sync job was queued
    """
    try:
        # Add the bulk sync job to background tasks
        background_tasks.add_task(
            sync_existing_tickets_bluestakes_data,
            company_id,
            batch_size,
            max_age_hours
        )
        
        if company_id:
            logging.info(f"Bulk Bluestakes data sync queued for company {company_id}")
        else:
            logging.info("Bulk Bluestakes data sync queued for all companies")
        
        return {
            "status": "success",
            "message": "Bulk Bluestakes data sync job queued successfully",
            "parameters": {
                "company_id": company_id,
                "max_age_hours": max_age_hours,
                "batch_size": batch_size
            }
        }
        
    except Exception as e:
        error_msg = f"Error queueing bulk sync: {str(e)}"
        logging.error(error_msg)
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )



