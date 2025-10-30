"""
Background job functions for ticket update processing.
Handles sequential processing of ticket update requests using the job manager.
"""
import asyncio
import logging
from typing import Dict, Any
from services.job_manager import job_manager, JobStatus, JobResult
from services.ticket_updater_service import update_single_ticket, TicketUpdateResult

logger = logging.getLogger(__name__)


async def process_ticket_update_job(job_id: str, username: str, password: str, ticket_number: str):
    """
    Process a single ticket update job in the background.
    
    Args:
        job_id: Unique job identifier
        username: BlueStakes username
        password: BlueStakes password
        ticket_number: Ticket number to update
    """
    logger.info(f"Starting ticket update job {job_id} for ticket {ticket_number}")
    
    # Update job status to processing
    job_manager.update_job_status(job_id, JobStatus.PROCESSING)
    
    try:
        # Call the existing ticket updater service
        result: TicketUpdateResult = await update_single_ticket(
            username=username,
            password=password,
            ticket_number=ticket_number
        )
        
        # Convert service result to job result
        job_result = JobResult(
            success=result.success,
            message=result.message,
            details=result.details,
            updated_at=result.updated_at
        )
        
        # Update job status based on result
        final_status = JobStatus.COMPLETED if result.success else JobStatus.FAILED
        job_manager.update_job_status(job_id, final_status, job_result)
        
        logger.info(f"Ticket update job {job_id} completed with status: {final_status.value}")
        
    except Exception as e:
        logger.error(f"Ticket update job {job_id} failed with exception: {str(e)}")
        
        # Mark job as failed
        job_result = JobResult(
            success=False,
            message=f"Job failed with error: {str(e)}",
            details=f"Exception during ticket update: {type(e).__name__}: {str(e)}"
        )
        job_manager.update_job_status(job_id, JobStatus.FAILED, job_result)


async def ticket_update_queue_processor():
    """
    Background queue processor that handles ticket update jobs sequentially.
    This function runs continuously and processes jobs one at a time.
    """
    logger.info("Ticket update queue processor started")
    job_manager.set_processing_status(False)
    
    while True:
        try:
            # Check for next job in queue
            job_data = await job_manager.get_next_job()
            
            if job_data is None:
                # No jobs in queue, wait a bit before checking again
                await asyncio.sleep(1)
                continue
            
            job_id = job_data['job_id']
            ticket_number = job_data['ticket_number']
            username = job_data['username']
            
            logger.info(f"Processing job {job_id} for ticket {ticket_number}")
            job_manager.set_processing_status(True)
            
            # Get the job to retrieve the password (stored separately for security)
            job = job_manager.get_job(job_id)
            if not job:
                logger.error(f"Job {job_id} not found in job manager")
                continue
            
            # Note: We need to get the password from the original request
            # For now, we'll need to modify this to store the password securely
            # This is a limitation of the current approach - we'll address it in the endpoint
            
            logger.warning(f"Job {job_id} cannot be processed - password not available in job data")
            job_manager.update_job_status(
                job_id, 
                JobStatus.FAILED, 
                JobResult(
                    success=False,
                    message="Job processing error: password not available",
                    details="Password cannot be stored in job queue for security reasons"
                )
            )
            
        except Exception as e:
            logger.error(f"Error in queue processor: {str(e)}")
            await asyncio.sleep(5)  # Wait longer on errors
        finally:
            job_manager.set_processing_status(False)


async def start_ticket_update_processor():
    """
    Start the ticket update queue processor as a background task.
    This should be called when the application starts.
    """
    logger.info("Starting ticket update queue processor")
    asyncio.create_task(ticket_update_queue_processor())


# Alternative approach: Process jobs immediately in background tasks
async def process_ticket_update_background_task(
    job_id: str, 
    username: str, 
    password: str, 
    ticket_number: str
):
    """
    Process ticket update as a FastAPI background task.
    This approach processes each job immediately without a persistent queue.
    
    Args:
        job_id: Unique job identifier
        username: BlueStakes username  
        password: BlueStakes password
        ticket_number: Ticket number to update
    """
    logger.info(f"Starting background task for job {job_id}, ticket {ticket_number}")
    
    # Update job status to processing
    job_manager.update_job_status(job_id, JobStatus.PROCESSING)
    
    try:
        # Call the existing ticket updater service
        result: TicketUpdateResult = await update_single_ticket(
            username=username,
            password=password,
            ticket_number=ticket_number
        )
        
        # Convert service result to job result
        job_result = JobResult(
            success=result.success,
            message=result.message,
            details=result.details,
            updated_at=result.updated_at
        )
        
        # Update job status based on result
        final_status = JobStatus.COMPLETED if result.success else JobStatus.FAILED
        job_manager.update_job_status(job_id, final_status, job_result)
        
        logger.info(f"Background task for job {job_id} completed with status: {final_status.value}")
        
    except Exception as e:
        logger.error(f"Background task for job {job_id} failed with exception: {str(e)}")
        
        # Mark job as failed
        job_result = JobResult(
            success=False,
            message=f"Job failed with error: {str(e)}",
            details=f"Exception during ticket update: {type(e).__name__}: {str(e)}"
        )
        job_manager.update_job_status(job_id, JobStatus.FAILED, job_result)


async def cleanup_old_jobs():
    """
    Periodic cleanup task for old jobs.
    Should be called periodically to prevent memory leaks.
    """
    logger.info("Running job cleanup")
    job_manager.cleanup_old_jobs(max_age_hours=24)
