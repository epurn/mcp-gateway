"""Repository layer for audit log database operations."""

from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditLog, AuditStatus
from .schemas import AuditLogCreate


async def create_audit_log(
    db: AsyncSession,
    log_data: AuditLogCreate,
) -> AuditLog:
    """Create a new audit log entry.
    
    Args:
        db: Async database session.
        log_data: Audit log data to insert.
        
    Returns:
        The created AuditLog instance.
    """
    audit_log = AuditLog(
        request_id=log_data.request_id,
        user_id=log_data.user_id,
        tool_name=log_data.tool_name,
        endpoint_path=log_data.endpoint_path,
        status=log_data.status,
        duration_ms=log_data.duration_ms,
        error_code=log_data.error_code,
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(audit_log)
    return audit_log


async def get_audit_logs(
    db: AsyncSession,
    user_id: str | None = None,
    tool_name: str | None = None,
    endpoint_path: str | None = None,
    status: AuditStatus | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[AuditLog], int]:
    """Query audit logs with optional filters.
    
    Args:
        db: Async database session.
        user_id: Filter by user ID.
        tool_name: Filter by tool name.
        status: Filter by status.
        start_time: Filter logs after this time.
        end_time: Filter logs before this time.
        limit: Maximum results to return.
        offset: Pagination offset.
        
    Returns:
        Tuple of (list of matching logs, total count).
    """
    # Build base query
    query = select(AuditLog)
    count_query = select(func.count(AuditLog.id))
    
    # Apply filters
    if user_id is not None:
        query = query.where(AuditLog.user_id == user_id)
        count_query = count_query.where(AuditLog.user_id == user_id)
    
    if tool_name is not None:
        query = query.where(AuditLog.tool_name == tool_name)
        count_query = count_query.where(AuditLog.tool_name == tool_name)

    if endpoint_path is not None:
        query = query.where(AuditLog.endpoint_path == endpoint_path)
        count_query = count_query.where(AuditLog.endpoint_path == endpoint_path)
    
    if status is not None:
        query = query.where(AuditLog.status == status)
        count_query = count_query.where(AuditLog.status == status)
    
    if start_time is not None:
        query = query.where(AuditLog.timestamp >= start_time)
        count_query = count_query.where(AuditLog.timestamp >= start_time)
    
    if end_time is not None:
        query = query.where(AuditLog.timestamp <= end_time)
        count_query = count_query.where(AuditLog.timestamp <= end_time)
    
    # Get total count
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Apply ordering and pagination
    query = query.order_by(AuditLog.timestamp.desc())
    query = query.limit(limit).offset(offset)
    
    # Execute query
    result = await db.execute(query)
    logs = list(result.scalars().all())
    
    return logs, total
