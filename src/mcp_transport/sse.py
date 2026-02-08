"""SSE transport implementation for MCP protocol."""

import asyncio
from typing import Annotated
import httpx

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.models import AuthenticatedUser
from src.auth.exceptions import MCPGatewayError, ToolNotAllowedError
from src.database import get_db
from src.dependencies import get_http_client
from src.ratelimit import check_rate_limit, RateLimitExceededError

from .schemas import MCPJSONRPCRequest, MCPJSONRPCResponse, MCPInitializeParams, MCPToolCallParams
from .service import handle_initialize, handle_tools_list, handle_tools_call


router = APIRouter(prefix="", tags=["mcp-sse"])
ALLOWED_SCOPES = {"calculator", "git", "docs"}
INVALID_SCOPE_ERROR_CODE = -32010
TOOL_NOT_IN_SCOPE_ERROR_CODE = -32011
META_TOOL_REMOVED_ERROR_CODE = -32012


def _validate_scope(scope: str) -> None:
    if scope not in ALLOWED_SCOPES:
        raise HTTPException(status_code=404, detail="Not Found")


def _jsonrpc_error_response(
    request_id: str | int | None,
    code: int,
    message: str,
    status_code: int = 200,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=MCPJSONRPCResponse(
            id=request_id,
            error={"code": code, "message": message},
        ).model_dump(),
    )


async def _handle_sse_get(request: Request, scope: str) -> StreamingResponse:
    # SSE Stream for server-to-client messages
    async def event_stream():
        # Send endpoint configuration
        message_endpoint = f"{request.url.scheme}://{request.url.netloc}/{scope}/sse"
        yield f"event: endpoint\\ndata: {message_endpoint}\\n\\n"

        # Keep connection alive
        try:
            while True:
                await asyncio.sleep(30)
                yield f": ping\\n\\n"
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


async def _handle_sse_post(
    scope: str,
    request: Request,
    user: AuthenticatedUser,
    db: AsyncSession,
    client: httpx.AsyncClient,
) -> MCPJSONRPCResponse | None:
    # Parse the JSON-RPC request
    body = await request.json()
    jsonrpc_request = MCPJSONRPCRequest(**body)

    method = jsonrpc_request.method
    params = jsonrpc_request.params or {}

    try:
        if method == "initialize":
            init_params = MCPInitializeParams(**params)
            result = await handle_initialize(init_params)
            return MCPJSONRPCResponse(id=jsonrpc_request.id, result=result)

        elif method == "notifications/initialized":
            # Client is confirming initialization, just acknowledge
            return None

        elif method == "tools/list":
            # Extract context if available (standard in some MCP clients)
            context = params.get("context")
            result = await handle_tools_list(db, user, scope=scope, context=context)
            return MCPJSONRPCResponse(id=jsonrpc_request.id, result=result.model_dump())

        elif method == "tools/call":
            call_params = MCPToolCallParams(**params)

            if call_params.name in {"find_tools", "call_tool"}:
                return _jsonrpc_error_response(
                    request_id=jsonrpc_request.id,
                    code=META_TOOL_REMOVED_ERROR_CODE,
                    message=(
                        f"Meta-tool '{call_params.name}' was removed in v2. "
                        "Use scoped tools/list and tools/call directly."
                    ),
                )

            rate_result = check_rate_limit(user_id=user.user_id, tool_name=call_params.name)
            if not rate_result.allowed:
                raise RateLimitExceededError(limit=rate_result.limit, retry_after=rate_result.retry_after)

            # Regular tool call
            try:
                result = await handle_tools_call(
                    db=db,
                    user=user,
                    client=client,
                    scope=scope,
                    name=call_params.name,
                    arguments=call_params.arguments,
                    endpoint_path=request.url.path,
                )
            except ToolNotAllowedError:
                return _jsonrpc_error_response(
                    request_id=jsonrpc_request.id,
                    code=TOOL_NOT_IN_SCOPE_ERROR_CODE,
                    message=(
                        f"Tool '{call_params.name}' is not available on endpoint "
                        f"'/{scope}/sse'."
                    ),
                )
            return MCPJSONRPCResponse(id=jsonrpc_request.id, result=result.model_dump())

        else:
            return MCPJSONRPCResponse(
                id=jsonrpc_request.id,
                error={
                    "code": -32601,
                    "message": f"Method not found: {method}",
                },
            )

    except Exception as e:
        if isinstance(e, MCPGatewayError):
            raise
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Internal error processing {method}: {e}", exc_info=True)
        return MCPJSONRPCResponse(
            id=jsonrpc_request.id,
            error={
                "code": -32603,
                "message": f"Internal error: {str(e)}",
            },
        )


@router.get("/{scope}/sse", operation_id="sse_endpoint_get")
async def sse_get_endpoint(
    scope: str,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    """Establish SSE stream and send endpoint info."""
    _validate_scope(scope)
    return await _handle_sse_get(request, scope)


@router.post("/{scope}/sse", operation_id="sse_endpoint_post")
async def sse_post_endpoint(
    scope: str,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
):
    """Handle JSON-RPC 2.0 messages."""
    if scope not in ALLOWED_SCOPES:
        request_id: str | int | None = None
        try:
            body = await request.json()
            request_id = body.get("id")
        except Exception:
            pass
        return _jsonrpc_error_response(
            request_id=request_id,
            code=INVALID_SCOPE_ERROR_CODE,
            message=f"Invalid endpoint scope '{scope}'.",
            status_code=404,
        )
    return await _handle_sse_post(scope, request, user, db, client)
