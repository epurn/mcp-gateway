"""FastAPI router for MCP Gateway endpoints."""

import uuid
from typing import Annotated
import httpx

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.models import AuthenticatedUser
from src.database import get_db
from src.dependencies import get_http_client
from src.ratelimit import check_rate_limit, RateLimitExceededError, RateLimitResult

from .schemas import MCPResponse, MCPErrorCodes, InvokeToolRequest
from .service import invoke_tool
from .exceptions import (
    GatewayError,
    ToolNotFoundError,
    BackendTimeoutError,
    BackendUnavailableError,
    PayloadTooLargeError,
    BackendError,
)


router = APIRouter(prefix="/mcp", tags=["gateway"])


@router.post("/invoke", response_model=MCPResponse)
async def invoke_tool_endpoint(
    http_request: Request,
    request: InvokeToolRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
    x_request_id: Annotated[str | None, Header()] = None,
) -> MCPResponse:
    """Invoke an MCP tool and proxy the request to the backend.
    
    This endpoint receives tool invocation requests, validates user
    permissions, looks up the tool's backend URL, and forwards the
    request.
    
    Args:
        request: Tool name and arguments.
        user: Authenticated user from JWT.
        db: Database session.
        x_request_id: Optional correlation ID (generated if not provided).
        
    Returns:
        MCPResponse with result or error from backend.
    """
    # Use provided request ID or generate one
    if x_request_id:
        request.request_id = x_request_id
    elif not request.request_id:
        request.request_id = str(uuid.uuid4())
    
    # Check rate limit (user-level + tool-level)
    rate_result = check_rate_limit(user_id=user.user_id, tool_name=request.tool_name)
    if not rate_result.allowed:
        raise RateLimitExceededError(
            limit=rate_result.limit,
            retry_after=rate_result.retry_after
        )
    
    response = await invoke_tool(
        db=db,
        user=user,
        request=request,
        client=client,
        endpoint_path=http_request.url.path,
    )
    
    return response


def create_error_response(
    request_id: str | int,
    code: int,
    message: str
) -> JSONResponse:
    """Create a JSON response for errors that happen before backend call."""
    return JSONResponse(
        content={
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message,
            }
        }
    )
