"""Pydantic schemas for audit logging."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class AuditStatus(str, Enum):
    """Status of a tool invocation."""
    
    success = "success"
    error = "error"
    timeout = "timeout"
    rate_limited = "rate_limited"


class AuditLogCreate(BaseModel):
    """Internal DTO for creating audit log entries.
    
    Attributes:
        request_id: Correlation ID for tracing.
        user_id: Who invoked the tool.
        tool_name: Which tool was invoked.
        endpoint_path: API endpoint path used for invocation.
        status: Outcome of the invocation.
        duration_ms: Call duration in milliseconds.
        error_code: Error code if failed.
    """
    
    request_id: str
    user_id: str
    tool_name: str
    endpoint_path: str
    status: AuditStatus
    duration_ms: int = Field(ge=0)
    error_code: str | None = None


class AuditLogResponse(BaseModel):
    """API response model for audit log entries.
    
    Attributes:
        id: Primary key.
        timestamp: When the invocation occurred.
        request_id: Correlation ID for tracing.
        user_id: Who invoked the tool.
        tool_name: Which tool was invoked.
        endpoint_path: API endpoint path used for invocation.
        status: Outcome of the invocation.
        duration_ms: Call duration in milliseconds.
        error_code: Error code if failed.
    """
    
    id: int
    timestamp: datetime
    request_id: str
    user_id: str
    tool_name: str
    endpoint_path: str
    status: AuditStatus
    duration_ms: int
    error_code: str | None = None
    
    model_config = {"from_attributes": True}


class AuditLogQuery(BaseModel):
    """Query filters for admin audit log endpoint.
    
    Attributes:
        user_id: Filter by user.
        tool_name: Filter by tool.
        endpoint_path: Filter by endpoint path.
        status: Filter by status.
        start_time: Filter logs after this time.
        end_time: Filter logs before this time.
        limit: Maximum results to return.
        offset: Pagination offset.
    """
    
    user_id: str | None = None
    tool_name: str | None = None
    endpoint_path: str | None = None
    status: AuditStatus | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class AuditLogListResponse(BaseModel):
    """Paginated response for audit log queries.
    
    Attributes:
        items: List of audit log entries.
        total: Total count matching the query.
        limit: Limit used in query.
        offset: Offset used in query.
    """
    
    items: list[AuditLogResponse]
    total: int
    limit: int
    offset: int
