"""High-level async audit logger for tool invocations."""

import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from .schemas import AuditLogCreate, AuditStatus
from .repository import create_audit_log

# Configure structured logger
logger = structlog.get_logger("audit")


class AuditContext:
    """Context manager for tracking tool invocation timing and status.
    
    Attributes:
        request_id: Correlation ID for tracing.
        user_id: Who is invoking the tool.
        tool_name: Which tool is being invoked.
        start_time: When the invocation started.
        status: Final status of the invocation.
        error_code: Error code if failed.
    """
    
    def __init__(
        self,
        request_id: str,
        user_id: str,
        tool_name: str,
    ) -> None:
        """Initialize audit context.
        
        Args:
            request_id: Correlation ID for tracing.
            user_id: Who is invoking the tool.
            tool_name: Which tool is being invoked.
        """
        self.request_id = request_id
        self.user_id = user_id
        self.tool_name = tool_name
        self.start_time = time.perf_counter()
        self.status = AuditStatus.success
        self.error_code: str | None = None
    
    def mark_error(self, error_code: str) -> None:
        """Mark the invocation as failed with an error code.
        
        Args:
            error_code: The error code to record.
        """
        self.status = AuditStatus.error
        self.error_code = error_code
    
    def mark_timeout(self) -> None:
        """Mark the invocation as timed out."""
        self.status = AuditStatus.timeout
        self.error_code = "BACKEND_TIMEOUT"
    
    def mark_rate_limited(self) -> None:
        """Mark the invocation as rate limited."""
        self.status = AuditStatus.rate_limited
        self.error_code = "RATE_LIMITED"
    
    @property
    def duration_ms(self) -> int:
        """Calculate duration in milliseconds."""
        elapsed = time.perf_counter() - self.start_time
        return int(elapsed * 1000)


async def log_tool_invocation(
    db: AsyncSession,
    context: AuditContext,
) -> None:
    """Log a tool invocation to the database.
    
    This is the main entry point for audit logging. It persists
    the audit record and logs to structlog.
    
    Args:
        db: Async database session.
        context: Audit context with invocation details.
    """
    log_data = AuditLogCreate(
        request_id=context.request_id,
        user_id=context.user_id,
        tool_name=context.tool_name,
        status=context.status,
        duration_ms=context.duration_ms,
        error_code=context.error_code,
    )
    
    # Persist to database
    await create_audit_log(db, log_data)
    
    # Also log to structlog for real-time monitoring
    logger.info(
        "tool_invocation",
        request_id=context.request_id,
        user_id=context.user_id,
        tool_name=context.tool_name,
        status=context.status.value,
        duration_ms=context.duration_ms,
        error_code=context.error_code,
    )


@asynccontextmanager
async def audit_tool_invocation(
    db: AsyncSession,
    request_id: str,
    user_id: str,
    tool_name: str,
) -> AsyncGenerator[AuditContext, None]:
    """Context manager for auditing tool invocations.
    
    Automatically tracks timing and logs when the context exits.
    
    Args:
        db: Async database session.
        request_id: Correlation ID for tracing.
        user_id: Who is invoking the tool.
        tool_name: Which tool is being invoked.
        
    Yields:
        AuditContext for marking status/errors.
        
    Example:
        async with audit_tool_invocation(db, req_id, user_id, tool) as ctx:
            try:
                result = await do_work()
            except TimeoutError:
                ctx.mark_timeout()
                raise
    """
    context = AuditContext(request_id, user_id, tool_name)
    try:
        yield context
    finally:
        await log_tool_invocation(db, context)
