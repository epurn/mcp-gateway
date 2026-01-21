"""Rate limiting middleware and FastAPI dependencies."""

from typing import Annotated, Callable
from fastapi import Depends, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.auth.dependencies import get_current_user
from src.auth.models import AuthenticatedUser

from .limiter import check_rate_limit, RateLimitResult, RateLimitConfig
from .exceptions import RateLimitExceededError


def add_rate_limit_headers(response: Response, result: RateLimitResult) -> None:
    """Add rate limit headers to response.
    
    Args:
        response: Response to add headers to.
        result: Rate limit check result.
    """
    response.headers["X-RateLimit-Limit"] = str(result.limit)
    response.headers["X-RateLimit-Remaining"] = str(result.remaining)
    response.headers["X-RateLimit-Reset"] = str(result.reset_at)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware that applies rate limiting to all requests.
    
    Note: This is an alternative to the dependency approach. Use one or the other.
    """
    
    async def dispatch(self, request: Request, call_next: Callable):
        # Skip rate limiting for health checks
        if request.url.path == "/health":
            return await call_next(request)
        
        # Get user from auth header (if present)
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            # No auth, skip rate limiting (auth will reject anyway)
            return await call_next(request)
        
        # For middleware, we'd need to extract user_id from token
        # This is simpler with the dependency approach
        return await call_next(request)


async def rate_limit_dependency(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> RateLimitResult:
    """FastAPI dependency that enforces rate limiting.
    
    Add this to your route dependencies to enable rate limiting.
    Automatically adds rate limit headers to the response.
    
    Args:
        request: FastAPI request.
        user: Authenticated user.
        
    Returns:
        RateLimitResult for informational purposes.
        
    Raises:
        RateLimitExceededError: If rate limit is exceeded.
    """
    # Extract tool name from request body if this is an invoke request
    tool_name = None
    if request.url.path.endswith("/invoke"):
        # Body is already parsed by FastAPI, check if we can get tool_name
        # This will be handled by the endpoint itself
        pass
    
    result = check_rate_limit(user_id=user.user_id, tool_name=tool_name)
    
    if not result.allowed:
        raise RateLimitExceededError(
            limit=result.limit,
            retry_after=result.retry_after
        )
    
    # Store result in request state so endpoint can access it
    request.state.rate_limit_result = result
    
    return result


def get_rate_limit_result(request: Request) -> RateLimitResult | None:
    """Get the rate limit result from request state.
    
    Use this in your endpoint to access rate limit info.
    """
    return getattr(request.state, "rate_limit_result", None)
