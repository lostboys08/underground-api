"""
Job management system for background ticket update tasks.
Provides in-memory job tracking with unique IDs, status management, and result storage.
"""
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional, Any, List
from enum import Enum
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """Job status enumeration."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class JobResult:
    """Job execution result."""
    success: bool
    message: str
    details: Optional[str] = None
    updated_at: Optional[datetime] = None


@dataclass
class Job:
    """Job data structure."""
    id: str
    status: JobStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    ticket_number: str = ""
    username: str = ""
    result: Optional[JobResult] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary for API responses."""
        data = asdict(self)
        # Convert enum to string
        data['status'] = self.status.value
        # Convert datetime objects to ISO strings
        for field in ['created_at', 'started_at', 'completed_at']:
            if data[field]:
                data[field] = data[field].isoformat()
        # Convert result to dict if present
        if self.result:
            result_dict = asdict(self.result)
            if result_dict.get('updated_at'):
                result_dict['updated_at'] = result_dict['updated_at'].isoformat()
            data['result'] = result_dict
        return data


class JobManager:
    """
    In-memory job management system for ticket update tasks.
    Handles job creation, status tracking, and result storage.
    """
    
    def __init__(self):
        self._jobs: Dict[str, Job] = {}
        # Use semaphore to limit concurrent ticket updates (only 1 at a time)
        self._semaphore = asyncio.Semaphore(1)
        self._active_jobs = 0
        
    def create_job(self, ticket_number: str, username: str) -> str:
        """
        Create a new job for tracking.
        
        Args:
            ticket_number: Ticket number to update
            username: Username for the update
            
        Returns:
            Job ID string
        """
        job_id = str(uuid.uuid4())
        job = Job(
            id=job_id,
            status=JobStatus.QUEUED,
            created_at=datetime.now(timezone.utc),
            ticket_number=ticket_number,
            username=username
        )
        
        self._jobs[job_id] = job
        logger.info(f"Job {job_id} created for ticket {ticket_number}")
        
        return job_id
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """
        Get job by ID.
        
        Args:
            job_id: Job ID to retrieve
            
        Returns:
            Job object or None if not found
        """
        return self._jobs.get(job_id)
    
    def update_job_status(self, job_id: str, status: JobStatus, result: Optional[JobResult] = None):
        """
        Update job status and optionally set result.
        
        Args:
            job_id: Job ID to update
            status: New job status
            result: Optional job result
        """
        job = self._jobs.get(job_id)
        if not job:
            logger.warning(f"Attempted to update non-existent job {job_id}")
            return
        
        job.status = status
        
        if status == JobStatus.PROCESSING and not job.started_at:
            job.started_at = datetime.now(timezone.utc)
        elif status in [JobStatus.COMPLETED, JobStatus.FAILED]:
            job.completed_at = datetime.now(timezone.utc)
            if result:
                job.result = result
        
        logger.info(f"Job {job_id} status updated to {status.value}")
    
    def get_semaphore(self) -> asyncio.Semaphore:
        """
        Get the semaphore for controlling concurrent job execution.
        
        Returns:
            The asyncio.Semaphore instance
        """
        return self._semaphore
    
    def get_queue_status(self) -> Dict[str, Any]:
        """
        Get current queue status information.
        
        Returns:
            Dictionary with queue statistics
        """
        total_jobs = len(self._jobs)
        queued_jobs = sum(1 for job in self._jobs.values() if job.status == JobStatus.QUEUED)
        processing_jobs = sum(1 for job in self._jobs.values() if job.status == JobStatus.PROCESSING)
        completed_jobs = sum(1 for job in self._jobs.values() if job.status == JobStatus.COMPLETED)
        failed_jobs = sum(1 for job in self._jobs.values() if job.status == JobStatus.FAILED)
        
        return {
            "total_jobs": total_jobs,
            "queued_jobs": queued_jobs,
            "processing_jobs": processing_jobs,
            "completed_jobs": completed_jobs,
            "failed_jobs": failed_jobs,
            "concurrent_limit": self._semaphore._value,
            "available_slots": self._semaphore._value,
            "active_jobs": self._active_jobs
        }
    
    def cleanup_old_jobs(self, max_age_hours: int = 24):
        """
        Clean up old completed/failed jobs to prevent memory leaks.
        
        Args:
            max_age_hours: Maximum age in hours for completed jobs
        """
        cutoff_time = datetime.now(timezone.utc).replace(hour=datetime.now().hour - max_age_hours)
        
        jobs_to_remove = []
        for job_id, job in self._jobs.items():
            if (job.status in [JobStatus.COMPLETED, JobStatus.FAILED] and 
                job.completed_at and job.completed_at < cutoff_time):
                jobs_to_remove.append(job_id)
        
        for job_id in jobs_to_remove:
            del self._jobs[job_id]
            logger.info(f"Cleaned up old job {job_id}")
        
        if jobs_to_remove:
            logger.info(f"Cleaned up {len(jobs_to_remove)} old jobs")
    
    def increment_active_jobs(self):
        """Increment the active jobs counter."""
        self._active_jobs += 1
    
    def decrement_active_jobs(self):
        """Decrement the active jobs counter."""
        self._active_jobs = max(0, self._active_jobs - 1)


# Global job manager instance
job_manager = JobManager()
