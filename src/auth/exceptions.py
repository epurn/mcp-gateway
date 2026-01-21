"""Custom exceptions for authentication and authorization."""


class MCPGatewayError(Exception):
    """Base exception for all MCP Gateway errors."""
    
    def __init__(self, message: str, code: str | None = None):
        self.message = message
        self.code = code or self.__class__.__name__
        super().__init__(self.message)


class AuthenticationError(MCPGatewayError):
    """Raised when authentication fails."""
    pass


class InvalidTokenError(AuthenticationError):
    """Raised when JWT token is invalid or malformed."""
    pass


class ExpiredTokenError(AuthenticationError):
    """Raised when JWT token has expired."""
    pass


class AuthorizationError(MCPGatewayError):
    """Raised when user lacks permission for an action."""
    pass


class ToolNotAllowedError(AuthorizationError):
    """Raised when user attempts to access a tool they're not permitted to use."""
    
    def __init__(self, tool_name: str, user_id: str):
        super().__init__(
            message=f"User '{user_id}' is not authorized to use tool '{tool_name}'",
            code="TOOL_NOT_ALLOWED"
        )
        self.tool_name = tool_name
        self.user_id = user_id
