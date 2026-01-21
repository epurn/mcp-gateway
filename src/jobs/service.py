"""Service layer for Async Jobs."""

import asyncio
from uuid import UUID

from fastapi import BackgroundTasks
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from src.auth.models import AuthenticatedUser
from src.database import AsyncSessionLocal
from src.gateway.service import invoke_tool as gateway_invoke_tool
from src.gateway.schemas import InvokeToolRequest

from .models import Job
from .schemas import JobCreate, JobStatus
from .repository import create_job, get_job, update_job_status

logger = get_logger()


async def submit_job(
    db: AsyncSession,
    user: AuthenticatedUser,
    job_create: JobCreate,
    background_tasks: BackgroundTasks,
) -> Job:
    """Submit a new async job.
    
    Creates the job record in DB and schedules the background task.
    
    Args:
        db: Database session.
        user: Authenticated user.
        job_create: Job creation details.
        background_tasks: FastAPI BackgroundTasks object.
        
    Returns:
        The created Job instance.
    """
    # Create DB record
    job = await create_job(db, job_create, user.user_id)
    
    # Schedule background processing
    # We pass the job ID and user details to reconstruct context
    background_tasks.add_task(
        process_job_task,
        job_id=job.id,
        user=user,
        job_create=job_create
    )
    
    logger.info("job_submitted", job_id=str(job.id), tool_name=job.tool_name, user_id=user.user_id)
    return job


async def process_job_task(
    job_id: UUID,
    user: AuthenticatedUser,
    job_create: JobCreate
) -> None:
    """Background task to process a job.
    
    This runs in the background, invokes the tool, and updates the job status.
    It creates its own DB session and HTTP client.
    """
    logger.info("job_started", job_id=str(job_id))
    
    async with AsyncSessionLocal() as db:
        async with httpx.AsyncClient() as client:
            try:
                # 1. Mark as RUNNING
                await update_job_status(db, job_id, JobStatus.RUNNING)
                
                # 2. Invoke tool via Gateway Service
                # We need to reconstruct InvokeToolRequest
                request = InvokeToolRequest(
                    tool_name=job_create.tool_name,
                    arguments=job_create.arguments,
                    request_id=job_create.request_id or str(job_id)
                )
                
                response = await gateway_invoke_tool(
                    db=db,
                    user=user,
                    request=request,
                    client=client
                )
                
                # 3. Check for error in response
                if response.error:
                    await update_job_status(
                        db, 
                        job_id, 
                        JobStatus.FAILED, 
                        error=response.error.message
                    )
                    logger.info("job_failed", job_id=str(job_id), error=response.error.message)
                else:
                    await update_job_status(
                        db, 
                        job_id, 
                        JobStatus.COMPLETED, 
                        result=response.result
                    )
                    logger.info("job_completed", job_id=str(job_id))
                    
            except Exception as e:
                logger.error("job_exception", job_id=str(job_id), error=str(e))
                # Catch-all for unexpected errors (e.g. gateway exceptions that bubbled up)
                try:
                    await update_job_status(
                        db, 
                        job_id, 
                        JobStatus.FAILED, 
                        error=str(e)
                    )
                except Exception as update_error:
                    # If we can't even update the DB, just log it
                    logger.critical("job_status_update_failed", job_id=str(job_id), error=str(update_error))
