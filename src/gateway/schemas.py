"""Pydantic schemas for MCP JSON-RPC protocol messages."""

from typing import Any, Literal
from pydantic import BaseModel, Field


class MCPToolCallParams(BaseModel):
    """Parameters for a tool call request.
    
    Attributes:
        name: Name of the tool to invoke.
        arguments: Arguments to pass to the tool.
    """
    
    name: str = Field(..., description="Name of the tool to invoke")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")


class MCPRequest(BaseModel):
    """JSON-RPC 2.0 request for MCP tool invocation.
    
    Attributes:
        jsonrpc: JSON-RPC version (always "2.0").
        method: The method to call (e.g., "tools/call").
        params: Tool call parameters.
        id: Request identifier for correlation.
    """
    
    jsonrpc: Literal["2.0"] = Field(default="2.0", description="JSON-RPC version")
    method: str = Field(..., description="Method to call")
    params: MCPToolCallParams = Field(..., description="Tool call parameters")
    id: str | int = Field(..., description="Request ID for correlation")


class MCPErrorDetail(BaseModel):
    """Error details in JSON-RPC format.
    
    Attributes:
        code: Error code (negative integers for protocol errors).
        message: Human-readable error message.
        data: Optional additional error data.
    """
    
    code: int = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    data: Any | None = Field(default=None, description="Additional error data")


class MCPResponse(BaseModel):
    """JSON-RPC 2.0 response wrapper.
    
    Attributes:
        jsonrpc: JSON-RPC version (always "2.0").
        result: Result on success.
        error: Error details on failure.
        id: Request ID for correlation.
    """
    
    jsonrpc: Literal["2.0"] = Field(default="2.0", description="JSON-RPC version")
    result: Any | None = Field(default=None, description="Result on success")
    error: MCPErrorDetail | None = Field(default=None, description="Error on failure")
    id: str | int = Field(..., description="Request ID for correlation")
    
    @classmethod
    def success(cls, id: str | int, result: Any) -> "MCPResponse":
        """Create a successful response.
        
        Args:
            id: Request ID.
            result: Result data.
            
        Returns:
            MCPResponse with result field populated.
        """
        return cls(id=id, result=result)
    
    @classmethod
    def error_response(
        cls, 
        id: str | int, 
        code: int, 
        message: str, 
        data: Any | None = None
    ) -> "MCPResponse":
        """Create an error response.
        
        Args:
            id: Request ID.
            code: Error code.
            message: Error message.
            data: Optional error data.
            
        Returns:
            MCPResponse with error field populated.
        """
        return cls(id=id, error=MCPErrorDetail(code=code, message=message, data=data))


# Standard JSON-RPC error codes
class MCPErrorCodes:
    """Standard MCP/JSON-RPC error codes."""
    
    # JSON-RPC standard errors
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    
    # Custom MCP Gateway errors (-32000 to -32099)
    TOOL_NOT_FOUND = -32001
    PERMISSION_DENIED = -32002
    BACKEND_TIMEOUT = -32003
    BACKEND_UNAVAILABLE = -32004
    PAYLOAD_TOO_LARGE = -32005


class InvokeToolRequest(BaseModel):
    """Simplified request schema for the invoke endpoint.
    
    This is a convenience wrapper that extracts the essential fields
    for tool invocation without full JSON-RPC ceremony.
    
    Attributes:
        tool_name: Name of the tool to invoke.
        arguments: Arguments to pass to the tool.
        request_id: Optional request ID for tracing.
    """
    
    tool_name: str = Field(..., description="Tool to invoke")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    request_id: str | None = Field(default=None, description="Optional request ID")
