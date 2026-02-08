"""HTTP proxy client for forwarding requests to MCP backend servers."""

import uuid
from typing import Any

import httpx

from src.config import get_settings
from .schemas import MCPRequest, MCPResponse, MCPErrorCodes
from .exceptions import BackendTimeoutError, BackendUnavailableError, BackendError


# Default timeout for backend requests
DEFAULT_TIMEOUT_SECONDS = 30.0


async def forward_to_backend(
    client: httpx.AsyncClient,
    backend_url: str,
    mcp_request: MCPRequest,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    request_id: str | None = None,
    user_id: str | None = None,
) -> MCPResponse:
    """Forward an MCP request to a backend server.
    
    Args:
        client: Shared HTTP client.
        backend_url: URL of the backend MCP server.
        mcp_request: The MCP JSON-RPC request to forward.
        timeout: Request timeout in seconds.
        request_id: Optional trace ID (generated if not provided).
        user_id: Optional user ID for audit headers.
        
    Returns:
        MCPResponse from the backend server.
        
    Raises:
        BackendTimeoutError: If backend doesn't respond in time.
        BackendUnavailableError: If backend connection fails.
        BackendError: If backend returns HTTP error status.
    """
    if request_id is None:
        request_id = str(uuid.uuid4())

    settings = get_settings()
    shared_secret = settings.TOOL_GATEWAY_SHARED_SECRET
    if not shared_secret:
        raise BackendError(
            backend_url=backend_url,
            status_code=500,
            detail="Gateway shared secret not configured",
        )
    
    headers = {
        "Content-Type": "application/json",
        "X-Request-ID": request_id,
        "X-Gateway-Auth": shared_secret,
    }
    
    if user_id:
        headers["X-User-ID"] = user_id
    
    try:
        response = await client.post(
            backend_url,
            json=mcp_request.model_dump(),
            headers=headers,
            timeout=timeout,
        )
        
        # Handle HTTP-level errors
        if response.status_code >= 400:
            raise BackendError(
                backend_url=backend_url,
                status_code=response.status_code,
                detail=response.text[:200]  # Truncate for safety
            )
        
        # Parse the JSON-RPC response
        data = response.json()
        return MCPResponse(**data)
        
    except httpx.TimeoutException:
        raise BackendTimeoutError(
            backend_url=backend_url,
            timeout_seconds=timeout
        )
    except httpx.ConnectError as e:
        raise BackendUnavailableError(
            backend_url=backend_url,
            reason=str(e)
        )
    except httpx.RequestError as e:
        raise BackendUnavailableError(
            backend_url=backend_url,
            reason=f"Request failed: {e}"
        )


async def forward_tool_call(
    client: httpx.AsyncClient,
    backend_url: str,
    tool_name: str,
    arguments: dict[str, Any],
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    request_id: str | None = None,
    user_id: str | None = None,
) -> MCPResponse:
    """Convenience function to invoke a tool on a backend server.
    
    Wraps the tool call in proper MCP JSON-RPC format.
    
    Args:
        client: Shared HTTP client.
        backend_url: URL of the backend MCP server.
        tool_name: Name of the tool to invoke.
        arguments: Arguments to pass to the tool.
        timeout: Request timeout in seconds.
        request_id: Optional trace ID.
        user_id: Optional user ID for audit.
        
    Returns:
        MCPResponse from the backend server.
    """
    from .schemas import MCPToolCallParams
    
    if request_id is None:
        request_id = str(uuid.uuid4())
    
    mcp_request = MCPRequest(
        method="tools/call",
        params=MCPToolCallParams(name=tool_name, arguments=arguments),
        id=request_id
    )
    
    return await forward_to_backend(
        client=client,
        backend_url=backend_url,
        mcp_request=mcp_request,
        timeout=timeout,
        request_id=request_id,
        user_id=user_id,
    )
