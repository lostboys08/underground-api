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



