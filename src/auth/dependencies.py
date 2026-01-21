"""FastAPI dependencies for authentication."""

from fastapi import Depends, Header
from typing import Annotated

from .exceptions import InvalidTokenError
from .models import AuthenticatedUser, UserClaims
from .utils import extract_user_claims
from .policy import get_allowed_tools_for_user


async def get_token_from_header(authorization: Annotated[str | None, Header()] = None) -> str:
    """Extract JWT token from Authorization header.
    
    Args:
        authorization: Authorization header value (format: 'Bearer <token>').
        
    Returns:
        JWT token string.
        
    Raises:
        InvalidTokenError: If header is missing or malformed.
    """
    if not authorization:
        raise InvalidTokenError("Missing Authorization header")
    
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise InvalidTokenError("Invalid Authorization header format. Expected: 'Bearer <token>'")
    
    return parts[1]


async def get_current_user_claims(token: Annotated[str, Depends(get_token_from_header)]) -> UserClaims:
    """Extract and validate user claims from JWT token.
    
    This dependency can be injected into FastAPI route handlers to get the authenticated user's claims.
    
    Args:
        token: JWT token extracted from Authorization header.
        
    Returns:
        UserClaims object with user information.
        
    Raises:
        InvalidTokenError: If token is invalid.
        ExpiredTokenError: If token has expired.
    """
    return extract_user_claims(token)


async def get_current_user(
    claims: Annotated[UserClaims, Depends(get_current_user_claims)]
) -> AuthenticatedUser:
    """Get the current authenticated user with their permissions.
    
    This dependency builds on get_current_user_claims and adds permission information
    by loading the policy and determining which tools the user can access.
    
    Args:
        claims: User claims from JWT.
        
    Returns:
        AuthenticatedUser object with claims and permissions.
    """
    allowed_tools = get_allowed_tools_for_user(claims)
    return AuthenticatedUser(claims=claims, allowed_tools=allowed_tools)
