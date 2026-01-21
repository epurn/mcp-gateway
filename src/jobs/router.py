"""FastAPI router for Async Jobs."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.models import AuthenticatedUser
from src.database import get_db

from .schemas import JobCreate, JobRead
from .repository import get_job
from .service import submit_job

router = APIRouter(prefix="/mcp/jobs", tags=["jobs"])


@router.post("", response_model=JobRead, status_code=202)
async def submit_job_endpoint(
    job_create: JobCreate,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
) -> JobRead:
    """Submit a new tool invocation job.
    
    Args:
        job_create: Job details.
        user: Authenticated user.
        db: Database session.
        background_tasks: FastAPI background tasks.
        
    Returns:
        The created Job in PENDING status.
    """
    job = await submit_job(db, user, job_create, background_tasks)
    return job


@router.get("/{job_id}", response_model=JobRead)
async def get_job_endpoint(
    job_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobRead:
    """Get the status and result of a job.
    
    Args:
        job_id: UUID of the job.
        user: Authenticated user (must be the creator or admin).
        db: Database session.
        
    Returns:
        The Job details.
        
    Raises:
        HTTPException(404): If job not found.
        HTTPException(403): If user doesn't own the job.
    """
    job = await get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    # Check ownership (unless admin)
    if job.user_id != user.user_id and "admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Not authorized to view this job")
        
    return job


from .repository import cleanup_old_jobs

@router.delete("", status_code=204)
async def cleanup_jobs_endpoint(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    hours: int = 24
):
    """Clean up old jobs (Admin only).
    
    Args:
        hours: Retention period in hours (default 24).
    """
    if "admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Only admins can clean up jobs")
        
    await cleanup_old_jobs(db, hours)
    return None

