"""Admin router for audit log queries."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.auth.models import AuthenticatedUser
from src.auth.dependencies import get_current_user
from src.auth.exceptions import AuthorizationError

from .schemas import (
    AuditStatus,
    AuditLogResponse,
    AuditLogListResponse,
)
from .repository import get_audit_logs


router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin(user: AuthenticatedUser) -> AuthenticatedUser:
    """Verify user has admin role.
    
    Args:
        user: Authenticated user to check.
        
    Returns:
        The user if they are an admin.
        
    Raises:
        AuthorizationError: If user is not an admin.
    """
    if "admin" not in user.roles:
        raise AuthorizationError(
            code="admin_required",
            message="Admin role required for this operation",
        )
    return user


@router.get("/audit-logs", response_model=AuditLogListResponse)
async def query_audit_logs(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    user_id: Annotated[str | None, Query(description="Filter by user ID")] = None,
    tool_name: Annotated[str | None, Query(description="Filter by tool name")] = None,
    status: Annotated[AuditStatus | None, Query(description="Filter by status")] = None,
    start_time: Annotated[datetime | None, Query(description="Filter logs after this time")] = None,
    end_time: Annotated[datetime | None, Query(description="Filter logs before this time")] = None,
    limit: Annotated[int, Query(ge=1, le=1000, description="Max results")] = 100,
    offset: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
) -> AuditLogListResponse:
    """Query audit logs with optional filters.
    
    Requires admin role. Returns paginated list of audit log entries
    matching the specified filters.
    
    Args:
        db: Database session.
        current_user: Authenticated user (must be admin).
        user_id: Filter by user ID.
        tool_name: Filter by tool name.
        status: Filter by status.
        start_time: Filter logs after this time.
        end_time: Filter logs before this time.
        limit: Maximum results to return.
        offset: Pagination offset.
        
    Returns:
        Paginated list of audit log entries.
    """
    # Verify admin access
    require_admin(current_user)
    
    # Query audit logs
    logs, total = await get_audit_logs(
        db=db,
        user_id=user_id,
        tool_name=tool_name,
        status=status,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )
    
    return AuditLogListResponse(
        items=[AuditLogResponse.model_validate(log) for log in logs],
        total=total,
        limit=limit,
        offset=offset,
    )
