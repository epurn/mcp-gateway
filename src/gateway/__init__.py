"""Gateway module - MCP request handling and proxying."""

from .schemas import (
    MCPRequest,
    MCPResponse,
    MCPErrorDetail,
    MCPErrorCodes,
    MCPToolCallParams,
    InvokeToolRequest,
)
from .exceptions import (
    GatewayError,
    ToolNotFoundError,
    BackendTimeoutError,
    BackendUnavailableError,
    PayloadTooLargeError,
    BackendError,
)
from .service import invoke_tool
from .router import router


__all__ = [
    # Schemas
    "MCPRequest",
    "MCPResponse",
    "MCPErrorDetail",
    "MCPErrorCodes",
    "MCPToolCallParams",
    "InvokeToolRequest",
    # Exceptions
    "GatewayError",
    "ToolNotFoundError",
    "BackendTimeoutError",
    "BackendUnavailableError",
    "PayloadTooLargeError",
    "BackendError",
    # Service
    "invoke_tool",
    # Router
    "router",
]
