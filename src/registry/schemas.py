"""Pydantic schemas for tool registry API responses."""

from pydantic import BaseModel, Field


class ToolResponse(BaseModel):
    """API response schema for a single tool.
    
    Attributes:
        name: Unique tool identifier.
        description: Human-readable description.
        backend_url: URL to route requests to.
        risk_level: Risk classification.
    """
    
    name: str = Field(..., description="Unique tool identifier")
    description: str = Field(..., description="Human-readable description")
    backend_url: str = Field(..., description="Backend URL for routing")
    risk_level: str = Field(..., description="Risk classification: low, medium, high")


class ToolListResponse(BaseModel):
    """API response schema for list of tools.
    
    Attributes:
        tools: List of tool definitions.
        count: Total number of tools returned.
    """
    
    tools: list[ToolResponse] = Field(default_factory=list, description="List of tools")
    count: int = Field(..., description="Total number of tools")
