"""Pydantic schemas for MCP protocol messages."""

from typing import Any, Literal
from pydantic import BaseModel, Field


class MCPInitializeParams(BaseModel):
    """Parameters for initialize request."""
    
    protocolVersion: str = Field(description="MCP protocol version")
    capabilities: dict[str, Any] = Field(default_factory=dict)
    clientInfo: dict[str, str] = Field(default_factory=dict)


class MCPToolInput(BaseModel):
    """Schema for a tool input parameter."""
    
    type: str
    description: str | None = None
    required: bool = False


class MCPTool(BaseModel):
    """MCP tool definition."""
    
    name: str
    description: str
    inputSchema: dict[str, Any]


class MCPToolListResult(BaseModel):
    """Result for tools/list."""
    
    tools: list[MCPTool]


class MCPToolCallParams(BaseModel):
    """Parameters for tools/call."""
    
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class MCPContent(BaseModel):
    """Content item in tool response."""
    
    type: Literal["text", "image", "resource"]
    text: str | None = None
    data: str | None = None
    mimeType: str | None = None


class MCPToolCallResult(BaseModel):
    """Result for tools/call."""
    
    content: list[MCPContent]
    isError: bool = False


class MCPJSONRPCRequest(BaseModel):
    """Generic JSON-RPC 2.0 request."""
    
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] | None = None


class MCPJSONRPCResponse(BaseModel):
    """Generic JSON-RPC 2.0 response."""
    
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None = None
    result: Any | None = None
    error: dict[str, Any] | None = None
