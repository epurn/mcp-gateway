"""Custom exceptions for the MCP Gateway."""

from src.auth.exceptions import MCPGatewayError


class GatewayError(MCPGatewayError):
    """Base exception for gateway-specific errors."""
    pass


class ToolNotFoundError(GatewayError):
    """Raised when requested tool is not in the registry.
    
    Attributes:
        tool_name: Name of the tool that was not found.
    """
    
    def __init__(self, tool_name: str):
        super().__init__(
            message=f"Tool '{tool_name}' not found in registry",
            code="TOOL_NOT_FOUND"
        )
        self.tool_name = tool_name


class BackendTimeoutError(GatewayError):
    """Raised when backend MCP server doesn't respond in time.
    
    Attributes:
        backend_url: URL of the backend that timed out.
        timeout_seconds: Timeout duration that was exceeded.
    """
    
    def __init__(self, backend_url: str, timeout_seconds: float):
        super().__init__(
            message=f"Backend at '{backend_url}' timed out after {timeout_seconds}s",
            code="BACKEND_TIMEOUT"
        )
        self.backend_url = backend_url
        self.timeout_seconds = timeout_seconds


class BackendUnavailableError(GatewayError):
    """Raised when backend MCP server is unreachable.
    
    Attributes:
        backend_url: URL of the unreachable backend.
        reason: Description of the connection failure.
    """
    
    def __init__(self, backend_url: str, reason: str = "Connection failed"):
        super().__init__(
            message=f"Backend at '{backend_url}' is unavailable: {reason}",
            code="BACKEND_UNAVAILABLE"
        )
        self.backend_url = backend_url
        self.reason = reason


class PayloadTooLargeError(GatewayError):
    """Raised when request payload exceeds the size limit.
    
    Attributes:
        size_bytes: Actual size of the payload.
        max_bytes: Maximum allowed size.
    """
    
    def __init__(self, size_bytes: int, max_bytes: int):
        super().__init__(
            message=f"Payload size {size_bytes} bytes exceeds limit of {max_bytes} bytes",
            code="PAYLOAD_TOO_LARGE"
        )
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes


class BackendError(GatewayError):
    """Raised when backend returns an error response.
    
    Attributes:
        backend_url: URL of the backend that returned an error.
        status_code: HTTP status code from backend.
        detail: Error detail from backend response.
    """
    
    def __init__(self, backend_url: str, status_code: int, detail: str = ""):
        super().__init__(
            message=f"Backend at '{backend_url}' returned error {status_code}: {detail}",
            code="BACKEND_ERROR"
        )
        self.backend_url = backend_url
        self.status_code = status_code
        self.detail = detail
