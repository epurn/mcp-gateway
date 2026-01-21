"""Service layer for MCP Gateway with validation and routing logic."""

import inspect
import uuid
from typing import Any
import httpx

from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import AuthenticatedUser
from src.auth.exceptions import ToolNotAllowedError
from src.registry.service import get_all_tools_cached
from src.audit import audit_tool_invocation

from .schemas import MCPResponse, InvokeToolRequest
from .exceptions import (
    ToolNotFoundError,
    PayloadTooLargeError,
    BackendTimeoutError,
    BackendUnavailableError,
    BackendError,
)
from .proxy import forward_tool_call


# Configuration defaults
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_PAYLOAD_BYTES = 1024 * 1024  # 1 MB


def validate_payload_size(
    arguments: dict[str, Any],
    max_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES
) -> None:
    """Validate that the request payload is within size limits.
    
    Args:
        arguments: Tool arguments to validate.
        max_bytes: Maximum allowed size in bytes.
        
    Raises:
        PayloadTooLargeError: If payload exceeds limit.
    """
    import json
    payload_str = json.dumps(arguments)
    size = len(payload_str.encode("utf-8"))
    
    if size > max_bytes:
        raise PayloadTooLargeError(size_bytes=size, max_bytes=max_bytes)


def generate_request_id() -> str:
    """Generate a unique request ID for tracing."""
    return str(uuid.uuid4())


async def _maybe_await(result: object) -> None:
    """Await async results while tolerating sync audit helpers.

    Args:
        result: Return value from an audit helper method.
    """
    if inspect.isawaitable(result):
        await result


async def invoke_tool(
    db: AsyncSession,
    user: AuthenticatedUser,
    request: InvokeToolRequest,
    client: httpx.AsyncClient,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
) -> MCPResponse:
    """Invoke an MCP tool on behalf of a user.
    
    This is the main entry point for tool invocation. It:
    1. Validates payload size
    2. Checks user has permission for the tool
    3. Looks up tool's backend URL from registry
    4. Forwards request to backend
    5. Logs the invocation for audit
    
    Args:
        db: Database session for registry lookup.
        user: Authenticated user making the request.
        request: Tool invocation request.
        client: HTTP client for backend requests.
        timeout: Backend request timeout.
        max_payload_bytes: Maximum payload size.
        
    Returns:
        MCPResponse from the backend.
        
    Raises:
        PayloadTooLargeError: If payload exceeds limit.
        ToolNotAllowedError: If user lacks permission.
        ToolNotFoundError: If tool is not in registry.
        BackendTimeoutError: If backend times out.
        BackendUnavailableError: If backend is unreachable.
    """
    request_id = request.request_id or generate_request_id()
    
    # Wrap entire operation in audit context
    async with audit_tool_invocation(
        db=db,
        request_id=request_id,
        user_id=user.user_id,
        tool_name=request.tool_name,
    ) as audit_ctx:
        try:
            # 1. Validate payload size
            validate_payload_size(request.arguments, max_payload_bytes)
            
            # 2. Check user has permission
            if not user.can_use_tool(request.tool_name):
                # Also check wildcard access
                if "*" not in user.allowed_tools:
                    raise ToolNotAllowedError(
                        tool_name=request.tool_name,
                        user_id=user.user_id
                    )
            
            # 3. Look up tool from registry
            all_tools = await get_all_tools_cached(db)
            tool = next((t for t in all_tools if t.name == request.tool_name), None)
            
            if tool is None:
                raise ToolNotFoundError(request.tool_name)
            
            # 4. Check tool-specific role requirements
            if tool.required_roles:
                if not any(role in user.roles for role in tool.required_roles):
                    raise ToolNotAllowedError(
                        tool_name=request.tool_name,
                        user_id=user.user_id
                    )
            
            # 5. Forward to backend
            response = await forward_tool_call(
                client=client,
                backend_url=tool.backend_url,
                tool_name=request.tool_name,
                arguments=request.arguments,
                timeout=timeout,
                request_id=request_id,
                user_id=user.user_id,
            )
            
            return response
            
        except BackendTimeoutError as e:
            await _maybe_await(audit_ctx.mark_timeout())
            raise
        except BackendUnavailableError as e:
            await _maybe_await(audit_ctx.mark_error("BACKEND_UNAVAILABLE"))
            raise
        except BackendError as e:
            await _maybe_await(audit_ctx.mark_error(e.code))
            raise
        except ToolNotFoundError as e:
            await _maybe_await(audit_ctx.mark_error("TOOL_NOT_FOUND"))
            raise
        except ToolNotAllowedError as e:
            await _maybe_await(audit_ctx.mark_error("TOOL_NOT_ALLOWED"))
            raise
        except PayloadTooLargeError as e:
            await _maybe_await(audit_ctx.mark_error("PAYLOAD_TOO_LARGE"))
            raise
