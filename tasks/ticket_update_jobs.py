"""
Background job functions for ticket update processing.
Uses asyncio.Semaphore to limit concurrent ticket updates with FastAPI BackgroundTasks.
"""
import asyncio
import logging
from typing import Dict, Any
from services.job_manager import job_manager, JobStatus, JobResult
from services.ticket_updater_service import update_single_ticket, TicketUpdateResult
from utils.encryption import safe_decrypt_password, EncryptionError

logger = logging.getLogger(__name__)


async def process_ticket_update_with_semaphore(
    job_id: str, 
    username: str, 
    password: str, 
    ticket_number: str
):
    """
    Process a ticket update job with semaphore-controlled concurrency.
    
    This function uses the job manager's semaphore to ensure only a limited number
    of ticket updates run concurrently (default: 1 to prevent multiple browsers).
    
    Args:
        job_id: Unique job identifier
        username: BlueStakes username
        password: BlueStakes password
        ticket_number: Ticket number to update
    """
    semaphore = job_manager.get_semaphore()
    
    logger.info(f"Job {job_id} waiting for semaphore (ticket: {ticket_number})")
    
    async with semaphore:
        logger.info(f"Job {job_id} acquired semaphore, starting processing (ticket: {ticket_number})")

        # Update job status to processing
        job_manager.update_job_status(job_id, JobStatus.PROCESSING)
        job_manager.increment_active_jobs()

        try:
            # Decrypt the password before using it
            try:
                decrypted_password = safe_decrypt_password(password)
                logger.info(f"Job {job_id}: Password decrypted successfully")
            except EncryptionError as e:
                logger.error(f"Job {job_id}: Failed to decrypt password: {str(e)}")
                raise Exception(f"Password decryption failed: {str(e)}")

            # Call the existing ticket updater service with decrypted password
            result: TicketUpdateResult = await update_single_ticket(
                username=username,
                password=decrypted_password,
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
            
            logger.info(f"Job {job_id} completed with status: {final_status.value} (ticket: {ticket_number})")
            
        except Exception as e:
            logger.error(f"Job {job_id} failed with exception: {str(e)} (ticket: {ticket_number})")
            
            # Mark job as failed
            job_result = JobResult(
                success=False,
                message=f"Job failed with error: {str(e)}",
                details=f"Exception during ticket update: {type(e).__name__}: {str(e)}"
            )
            job_manager.update_job_status(job_id, JobStatus.FAILED, job_result)
            
        finally:
            job_manager.decrement_active_jobs()
            logger.info(f"Job {job_id} released semaphore (ticket: {ticket_number})")




async def cleanup_old_jobs():
    """
    Periodic cleanup task for old jobs.
    Should be called periodically to prevent memory leaks.
    """
    logger.info("Running job cleanup")
    job_manager.cleanup_old_jobs(max_age_hours=24)
