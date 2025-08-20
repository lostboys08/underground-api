"""
Cron job endpoints for scheduled tasks.
These routes are protected by CRON_SECRET and trigger background jobs.
"""
from fastapi import APIRouter, BackgroundTasks, HTTPException, Header, Query
from typing import Optional
import os
import logging
from tasks.jobs import sync_bluestakes_tickets, refresh_todo_table, send_ticket_emails

logger = logging.getLogger(__name__)

cron_router = APIRouter(prefix="/cron", tags=["cron"])


def verify_cron_secret(x_cron_secret: Optional[str] = Header(None)):
    """
    Verify the cron secret header matches the environment variable.
    
    Args:
        x_cron_secret: The X-CRON-SECRET header value
        
    Raises:
        HTTPException: If the secret is missing or invalid
    """
    expected_secret = os.getenv("CRON_SECRET")
    
    if not expected_secret:
        logger.error("CRON_SECRET environment variable not configured")
        raise HTTPException(
            status_code=500, 
            detail="Cron secret not configured on server"
        )
    
    if not x_cron_secret:
        logger.warning("Cron endpoint accessed without X-CRON-SECRET header")
        raise HTTPException(
            status_code=401, 
            detail="X-CRON-SECRET header is required"
        )
    
    if x_cron_secret != expected_secret:
        logger.warning("Cron endpoint accessed with invalid secret")
        raise HTTPException(
            status_code=403, 
            detail="Invalid cron secret"
        )


@cron_router.post("/daily-update")
async def daily_update(
    background_tasks: BackgroundTasks,
    x_cron_secret: Optional[str] = Header(None)
):
    """
    Daily update job that syncs BlueStakes tickets.
    
    This endpoint should be called by a cron scheduler (like Railway's cron jobs)
    to perform daily synchronization of ticket data from BlueStakes.
    Uses 2-day lookback for daily sync operations.
    
    Headers:
        X-CRON-SECRET: Secret key for cron job authentication
        
    Returns:
        JSON response indicating the job was queued successfully
    """
    verify_cron_secret(x_cron_secret)
    
    logger.info("Daily update cron job triggered")
    
    # Add the job to background tasks so we can respond immediately
    # Use default parameters: all companies, 2 days back
    background_tasks.add_task(sync_bluestakes_tickets, None, 2)
    
    return {
        "status": "success",
        "message": "Daily update job queued successfully",
        "job": "sync_bluestakes_tickets",
        "parameters": {
            "company_id": None,
            "days_back": 2
        }
    }


@cron_router.post("/sync-bluestakes")
async def sync_bluestakes_cron(
    background_tasks: BackgroundTasks,
    x_cron_secret: Optional[str] = Header(None),
    company_id: Optional[int] = Query(default=None, description="Company ID to sync. If not provided, syncs all companies"),
    days_back: int = Query(default=28, description="Number of days to look back for tickets")
):
    """
    Flexible BlueStakes sync job with parameters.
    
    This endpoint allows more control over the sync process and can be used
    for both scheduled daily syncs and on-demand company-specific syncs.
    
    Headers:
        X-CRON-SECRET: Secret key for cron job authentication
        
    Query Parameters:
        company_id: Optional company ID to sync (syncs all if not provided)
        days_back: Number of days to look back (1-365, default 28)
        
    Returns:
        JSON response indicating the job was queued successfully
    """
    verify_cron_secret(x_cron_secret)
    
    # Validate parameters
    if days_back < 1 or days_back > 365:
        raise HTTPException(
            status_code=400,
            detail="days_back must be between 1 and 365"
        )
    
    if company_id:
        logger.info(f"BlueStakes sync cron job triggered for company {company_id} ({days_back} days)")
    else:
        logger.info(f"BlueStakes sync cron job triggered for all companies ({days_back} days)")
    
    # Add the job to background tasks with parameters
    background_tasks.add_task(sync_bluestakes_tickets, company_id, days_back)
    
    return {
        "status": "success",
        "message": "BlueStakes sync job queued successfully",
        "job": "sync_bluestakes_tickets",
        "parameters": {
            "company_id": company_id,
            "days_back": days_back
        }
    }


@cron_router.post("/refresh-todo")
async def refresh_todo(
    background_tasks: BackgroundTasks,
    x_cron_secret: Optional[str] = Header(None)
):
    """
    Refresh todo table job.
    
    This endpoint should be called periodically to refresh and maintain
    the todo table data integrity.
    
    Headers:
        X-CRON-SECRET: Secret key for cron job authentication
        
    Returns:
        JSON response indicating the job was queued successfully
    """
    verify_cron_secret(x_cron_secret)
    
    logger.info("Refresh todo cron job triggered")
    
    # Add the job to background tasks so we can respond immediately
    background_tasks.add_task(refresh_todo_table)
    
    return {
        "status": "success",
        "message": "Todo refresh job queued successfully",
        "job": "refresh_todo_table"
    }


@cron_router.post("/send-emails")
async def send_emails(
    background_tasks: BackgroundTasks,
    x_cron_secret: Optional[str] = Header(None)
):
    """
    Send ticket emails job.
    
    This endpoint should be called periodically to send ticket-related
    email notifications and reports.
    
    Headers:
        X-CRON-SECRET: Secret key for cron job authentication
        
    Returns:
        JSON response indicating the job was queued successfully
    """
    verify_cron_secret(x_cron_secret)
    
    logger.info("Send emails cron job triggered")
    
    # Add the job to background tasks so we can respond immediately
    background_tasks.add_task(send_ticket_emails)
    
    return {
        "status": "success",
        "message": "Email sending job queued successfully",
        "job": "send_ticket_emails"
    }


@cron_router.get("/status")
async def cron_status(x_cron_secret: Optional[str] = Header(None)):
    """
    Get cron job status and configuration.
    
    This endpoint can be used to verify cron job setup and configuration.
    
    Headers:
        X-CRON-SECRET: Secret key for cron job authentication
        
    Returns:
        JSON response with cron job status and available endpoints
    """
    verify_cron_secret(x_cron_secret)
    
    return {
        "status": "active",
        "message": "Cron service is running",
        "available_jobs": [
            {
                "endpoint": "/cron/daily-update",
                "method": "POST",
                "description": "Sync BlueStakes tickets (default: all companies, 2 days)"
            },
            {
                "endpoint": "/cron/sync-bluestakes",
                "method": "POST",
                "description": "Flexible BlueStakes sync with parameters",
                "parameters": ["company_id", "days_back"]
            },
            {
                "endpoint": "/cron/refresh-todo",
                "method": "POST", 
                "description": "Refresh todo table"
            },
            {
                "endpoint": "/cron/send-emails",
                "method": "POST",
                "description": "Send ticket emails"
            }
        ],
        "authentication": {
            "type": "Header",
            "header": "X-CRON-SECRET",
            "configured": bool(os.getenv("CRON_SECRET"))
        }
    }
