"""Repository layer for Async Jobs."""

from typing import Optional
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Job
from .schemas import JobStatus, JobCreate


async def create_job(db: AsyncSession, job_create: JobCreate, user_id: str) -> Job:
    """Create a new job in the database.
    
    Args:
        db: Database session.
        job_create: Job creation data.
        user_id: ID of the user creating the job.
        
    Returns:
        The created Job instance.
    """
    job = Job(
        user_id=user_id,
        tool_name=job_create.tool_name,
        arguments=job_create.arguments,
        request_id=job_create.request_id,
        status=JobStatus.PENDING,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def get_job(db: AsyncSession, job_id: UUID) -> Optional[Job]:
    """Get a job by ID.
    
    Args:
        db: Database session.
        job_id: ID of the job to retrieve.
        
    Returns:
        The Job instance or None if not found.
    """
    result = await db.execute(select(Job).where(Job.id == job_id))
    return result.scalar_one_or_none()


async def update_job_status(
    db: AsyncSession, 
    job_id: UUID, 
    status: JobStatus, 
    result: Optional[dict] = None,
    error: Optional[str] = None
) -> Job:
    """Update job status and result.
    
    Args:
        db: Database session.
        job_id: ID of the job to update.
        status: New status.
        result: Optional result data (for completed jobs).
        error: Optional error message (for failed jobs).
        
    Returns:
        The updated Job instance.
        
    Raises:
        ValueError: If job not found.
    """
    job = await get_job(db, job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")
        
    job.status = status
    if result is not None:
        job.result = result
    if error is not None:
        job.error = error
        
    if status in (JobStatus.COMPLETED, JobStatus.FAILED):
        job.completed_at = datetime.now(timezone.utc)
        
    await db.commit()
    await db.refresh(job)
    return job


from sqlalchemy import delete
from datetime import timedelta

async def cleanup_old_jobs(db: AsyncSession, retention_hours: int = 24) -> int:
    """Delete jobs older than retention period.
    
    Args:
        db: Database session.
        retention_hours: Age in hours to delete.
        
    Returns:
        Number of deleted jobs.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=retention_hours)
    
    result = await db.execute(
        delete(Job).where(Job.created_at < cutoff)
    )
    
    await db.commit()
    return result.rowcount

