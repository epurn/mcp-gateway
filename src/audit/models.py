"""SQLAlchemy models for audit logging."""

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    String,
    Integer,
    DateTime,
    Enum as SQLAlchemyEnum,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class AuditStatus(str, Enum):
    """Status of a tool invocation.
    
    Attributes:
        success: Tool executed successfully.
        error: Tool returned an error.
        timeout: Backend timed out.
        rate_limited: Request was rate limited.
    """
    
    success = "success"
    error = "error"
    timeout = "timeout"
    rate_limited = "rate_limited"


class AuditLog(Base):
    """Audit log entry for tool invocations.
    
    Records WHO called WHAT tool WHEN. No inputs or conversation data
    are stored per org data retention policy.
    
    Attributes:
        id: Primary key.
        timestamp: When the invocation occurred.
        request_id: Correlation ID for distributed tracing.
        user_id: Who invoked the tool.
        tool_name: Which tool was invoked.
        status: Outcome of the invocation.
        duration_ms: How long the call took in milliseconds.
        error_code: Error code if failed (nullable).
    """
    
    __tablename__ = "audit_logs"
    
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
        comment="When the invocation occurred",
    )
    request_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        nullable=False,
        index=True,
        comment="Correlation ID for tracing",
    )
    user_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Who invoked the tool",
    )
    tool_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Which tool was invoked",
    )
    status: Mapped[AuditStatus] = mapped_column(
        SQLAlchemyEnum(AuditStatus, name="audit_status_enum"),
        nullable=False,
        index=True,
        comment="Outcome of the invocation",
    )
    duration_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Call duration in milliseconds",
    )
    error_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Error code if failed",
    )
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<AuditLog(id={self.id}, user={self.user_id}, "
            f"tool={self.tool_name}, status={self.status.value})>"
        )
