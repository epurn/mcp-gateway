"""SSE transport implementation for MCP protocol."""

import asyncio
from typing import Annotated
import httpx

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.models import AuthenticatedUser
from src.database import get_db
from src.dependencies import get_http_client

from .schemas import MCPJSONRPCRequest, MCPJSONRPCResponse, MCPInitializeParams, MCPToolCallParams
from .service import handle_initialize, handle_tools_list, handle_tools_call, handle_find_tools


router = APIRouter(prefix="", tags=["mcp-sse"])


async def _handle_sse_get(request: Request) -> StreamingResponse:
    # SSE Stream for server-to-client messages
    async def event_stream():
        # Send endpoint configuration
        message_endpoint = f"{request.url.scheme}://{request.url.netloc}/sse"
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
            result = await handle_tools_list(db, user, context=context)
            return MCPJSONRPCResponse(id=jsonrpc_request.id, result=result.model_dump())

        elif method == "tools/call":
            call_params = MCPToolCallParams(**params)

            # Special handling for find_tools meta-tool
            if call_params.name == "find_tools":
                import json
                result_data = await handle_find_tools(
                    db=db,
                    query=call_params.arguments.get("query", ""),
                    max_results=call_params.arguments.get("max_results", 5),
                )
                # Return as MCP tool call result
                return MCPJSONRPCResponse(
                    id=jsonrpc_request.id,
                    result={
                        "content": [{"type": "text", "text": json.dumps(result_data, indent=2)}],
                        "isError": False,
                    },
                )

            # Special handling for call_tool meta-tool (invoke discovered tools)
            if call_params.name == "call_tool":
                tool_name = call_params.arguments.get("name", "")
                tool_args = call_params.arguments.get("arguments", {})

                if not tool_name:
                    return MCPJSONRPCResponse(
                        id=jsonrpc_request.id,
                        result={
                            "content": [{"type": "text", "text": "Error: 'name' is required"}],
                            "isError": True,
                        },
                    )

                # Proxy the call to the actual tool
                result = await handle_tools_call(
                    db=db,
                    user=user,
                    client=client,
                    name=tool_name,
                    arguments=tool_args,
                )
                return MCPJSONRPCResponse(id=jsonrpc_request.id, result=result.model_dump())

            # Regular tool call
            result = await handle_tools_call(
                db=db,
                user=user,
                client=client,
                name=call_params.name,
                arguments=call_params.arguments,
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


@router.get("/sse", operation_id="sse_endpoint_get")
async def sse_get_endpoint(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    """Establish SSE stream and send endpoint info."""
    return await _handle_sse_get(request)


@router.post("/sse", operation_id="sse_endpoint_post")
async def sse_post_endpoint(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
):
    """Handle JSON-RPC 2.0 messages."""
    return await _handle_sse_post(request, user, db, client)


@router.post("/messages")
async def messages_endpoint(
    request: MCPJSONRPCRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> MCPJSONRPCResponse:
    """Handle JSON-RPC 2.0 messages for MCP protocol (legacy endpoint).
    
    This endpoint is kept for backwards compatibility but /sse POST should be used.
    """
    method = request.method
    params = request.params or {}
    
    try:
        if method == "initialize":
            init_params = MCPInitializeParams(**params)
            result = await handle_initialize(init_params)
            return MCPJSONRPCResponse(id=request.id, result=result)
        
        elif method == "tools/list":
            context = params.get("context")
            result = await handle_tools_list(db, user, context=context)
            return MCPJSONRPCResponse(id=request.id, result=result.model_dump())
        
        elif method == "tools/call":
            call_params = MCPToolCallParams(**params)
            result = await handle_tools_call(
                db=db,
                user=user,
                client=client,
                name=call_params.name,
                arguments=call_params.arguments
            )
            return MCPJSONRPCResponse(id=request.id, result=result.model_dump())
        
        else:
            return MCPJSONRPCResponse(
                id=request.id,
                error={
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            )
            
    except Exception as e:
        return MCPJSONRPCResponse(
            id=request.id,
            error={
                "code": -32603,
                "message": f"Internal error: {str(e)}"
            }
        )
