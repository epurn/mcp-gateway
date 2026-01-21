"""Pydantic schemas for Async Jobs."""

from datetime import datetime
from enum import StrEnum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class JobStatus(StrEnum):
    """Status of an asynchronous job."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobCreate(BaseModel):
    """Schema for creating a new job (wrapping an invoke request)."""
    tool_name: str = Field(..., description="Name of the tool to invoke")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    request_id: Optional[str] = Field(None, description="Client-provided request ID for tracing")


class JobRead(BaseModel):
    """Schema for reading job details."""
    id: UUID
    user_id: str
    tool_name: str
    arguments: dict[str, Any]
    status: JobStatus
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    request_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
