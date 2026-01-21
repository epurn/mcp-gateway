"""SQLAlchemy models for the tool registry."""

from datetime import datetime
from enum import Enum
from typing import Annotated

from sqlalchemy import (
    String,
    Text,
    Boolean,
    DateTime,
    Enum as SQLAlchemyEnum,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class RiskLevel(str, Enum):
    """Risk level classification for tools.
    
    Attributes:
        low: Low risk tools (e.g., read-only operations).
        medium: Medium risk tools (e.g., write operations).
        high: High risk tools (e.g., destructive operations).
    """
    
    low = "low"
    medium = "medium"
    high = "high"


class Tool(Base):
    """Tool definition stored in the registry.
    
    Attributes:
        id: Primary key.
        name: Unique tool identifier (e.g., "read_file").
        description: Human-readable description of the tool.
        backend_url: URL to route tool requests to.
        risk_level: Risk classification for policy checks.
        required_roles: Optional list of roles required to use this tool.
        is_active: Whether the tool is available for use.
        created_at: Timestamp when the tool was registered.
        updated_at: Timestamp of last update.
    """
    
    __tablename__ = "tools"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(
        String(100), 
        unique=True, 
        index=True,
        nullable=False,
        comment="Unique tool identifier"
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Human-readable tool description"
    )
    backend_url: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="URL to route requests to"
    )
    risk_level: Mapped[RiskLevel] = mapped_column(
        SQLAlchemyEnum(RiskLevel, name="risk_level_enum"),
        default=RiskLevel.low,
        nullable=False,
        comment="Risk classification for policy checks"
    )
    required_roles: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(50)),
        nullable=True,
        comment="Optional role overrides for this tool"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether the tool is available"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Registration timestamp"
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
        comment="Last update timestamp"
    )
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<Tool(name='{self.name}', risk_level={self.risk_level.value}, active={self.is_active})>"
