"""
Cron job endpoints for scheduled tasks.
These routes are protected by CRON_SECRET and trigger background jobs.
"""
from fastapi import APIRouter, BackgroundTasks, HTTPException, Header, Query
from typing import Optional
import os
import logging
from datetime import datetime
from tasks.jobs import sync_bluestakes_tickets, sync_updateable_tickets, send_weekly_project_digest

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










@cron_router.post("/sync-updatable-tickets")
async def sync_updatable_tickets_cron(
    background_tasks: BackgroundTasks,
    x_cron_secret: Optional[str] = Header(None),
    company_id: Optional[int] = Query(default=None, description="Company ID to sync. If not provided, syncs all companies")
):
    """
    Sync updateable tickets job - queries database for tickets meeting criteria,
    verifies them via BlueStakes API, and populates the updateable_tickets table.
    
    This endpoint should run on the same schedule as the daily update to maintain
    the updateable tickets table with current verification status.
    
    Headers:
        X-CRON-SECRET: Secret key for cron job authentication
        
    Query Parameters:
        company_id: Optional company ID to sync (syncs all if not provided)
        
    Returns:
        JSON response indicating the job was queued successfully
    """
    verify_cron_secret(x_cron_secret)
    
    if company_id:
        logger.info(f"Updateable tickets sync cron job triggered for company {company_id}")
    else:
        logger.info("Updateable tickets sync cron job triggered for all companies")
    
    # Add the job to background tasks
    background_tasks.add_task(sync_updateable_tickets, company_id)
    
    return {
        "status": "success",
        "message": "Updatable tickets sync job queued successfully",
        "job": "sync_updateable_tickets",
        "parameters": {
            "company_id": company_id
        }
    }


@cron_router.post("/send-weekly-project-digest")
async def send_weekly_project_digest_cron(
    background_tasks: BackgroundTasks,
    x_cron_secret: Optional[str] = Header(None)
):
    """
    Send weekly project digest emails job using Next.js API.
    
    This endpoint triggers the bulk email process that:
    1. Queries all assigned users from the database
    2. For each user, gathers their projects and active tickets
    3. Sends individual weekly update emails via Next.js API using 'weeklyUpdate' template
    4. Automatically calculates new tickets (legal date within 7 days) and expiring tickets
    
    Headers:
        X-CRON-SECRET: Secret key for cron job authentication
        
    Returns:
        JSON response indicating the job was queued successfully
    """
    verify_cron_secret(x_cron_secret)
    
    logger.info("Send weekly project digest cron job triggered")
    
    # Add the job to background tasks so we can respond immediately
    background_tasks.add_task(send_weekly_project_digest)
    
    return {
        "status": "success",
        "message": "Weekly project digest job queued successfully",
        "job": "send_weekly_project_digest"
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
            },
            {
                "endpoint": "/cron/send-notifications",
                "method": "POST",
                "description": "Send general notification emails"
            },
            {
                "endpoint": "/cron/sync-updatable-tickets",
                "method": "POST",
                "description": "Sync updateable tickets with BlueStakes verification",
                "parameters": ["company_id"]
            },
            {
                "endpoint": "/cron/send-weekly-project-digest",
                "method": "POST",
                "description": "Send weekly project digest emails to assigned users"
            }
        ],
        "authentication": {
            "type": "Header",
            "header": "X-CRON-SECRET",
            "configured": bool(os.getenv("CRON_SECRET"))
        }
    }
