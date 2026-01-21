"""Auth module initialization."""

from .exceptions import (
    MCPGatewayError,
    AuthenticationError,
    InvalidTokenError,
    ExpiredTokenError,
    AuthorizationError,
    ToolNotAllowedError,
)
from .models import UserClaims, AuthenticatedUser
from .utils import decode_jwt, extract_user_claims, create_test_jwt
from .dependencies import get_current_user, get_current_user_claims
from .policy import (
    PolicyConfig,
    load_policy,
    get_allowed_tools_for_user,
    check_tool_permission,
    enforce_tool_permission,
)

__all__ = [
    # Exceptions
    "MCPGatewayError",
    "AuthenticationError",
    "InvalidTokenError",
    "ExpiredTokenError",
    "AuthorizationError",
    "ToolNotAllowedError",
    # Models
    "UserClaims",
    "AuthenticatedUser",
    # Utils
    "decode_jwt",
    "extract_user_claims",
    "create_test_jwt",
    # Dependencies
    "get_current_user",
    "get_current_user_claims",
    # Policy
    "PolicyConfig",
    "load_policy",
    "get_allowed_tools_for_user",
    "check_tool_permission",
    "enforce_tool_permission",
]
