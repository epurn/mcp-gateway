"""SSE transport implementation for MCP protocol."""

import asyncio
import uuid
from typing import Annotated, Any
import httpx

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.models import AuthenticatedUser
from src.database import get_db
from src.dependencies import get_http_client

from .schemas import MCPJSONRPCRequest, MCPJSONRPCResponse, MCPInitializeParams, MCPToolCallParams
from .service import handle_initialize, handle_tools_list, handle_tools_call, handle_find_tools


router = APIRouter(prefix="", tags=["mcp-sse"])


@router.post("/debug-headers")
async def debug_headers(request: Request):
    """Debug endpoint to see what headers are being sent (NO AUTH)."""
    import logging
    logger = logging.getLogger(__name__)
    
    headers_dict = dict(request.headers)
    logger.info(f"=== DEBUG HEADERS ===")
    logger.info(f"Headers: {headers_dict}")
    logger.info(f"Authorization: {headers_dict.get('authorization', 'MISSING')}")
    
    return {"headers": headers_dict}


@router.api_route("/sse", methods=["GET", "POST"])
async def sse_endpoint(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)] = None,
):
    """Handle both SSE connections (GET) and JSON-RPC messages (POST).
    
    This unified endpoint allows mcp-http-bridge to use a single URL.
    - GET: Establish SSE stream and send endpoint info
    - POST: Handle JSON-RPC 2.0 messages
    
    Args:
        request: FastAPI request object.
        user: Authenticated user from JWT.
        db: Database session (for POST requests).
        client: HTTP client (for POST requests).
        
    Returns:
        StreamingResponse for GET, MCPJSONRPCResponse for POST.
    """
    # Debug logging
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Request method: {request.method}")
    logger.info(f"Headers: {dict(request.headers)}")
    
    if request.method == "GET":
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
            }
        )
    
    else:  # POST - handle JSON-RPC messages
        # Parse the JSON-RPC request
        body = await request.json()
        logger.info(f"Received JSON-RPC request: {body}")
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
                logger.info(f"Handling tools/list request: {jsonrpc_request}")
                
                # Extract context if available (standard in some MCP clients)
                context = params.get("context")
                result = await handle_tools_list(db, user, context=context)
                
                response = MCPJSONRPCResponse(id=jsonrpc_request.id, result=result.model_dump())
                logger.info(f"Sending tools/list response: {response.model_dump()}")
                return response
            
            elif method == "tools/call":
                call_params = MCPToolCallParams(**params)
                
                # Special handling for find_tools meta-tool
                if call_params.name == "find_tools":
                    import json # Added missing import for json.dumps
                    result_data = await handle_find_tools(
                        db=db, # Corrected typo from 'b' to 'db'
                        query=call_params.arguments.get("query", ""),
                        max_results=call_params.arguments.get("max_results", 5)
                    )
                    # Return as MCP tool call result
                    return MCPJSONRPCResponse(
                        id=jsonrpc_request.id,
                        result={
                            "content": [{"type": "text", "text": json.dumps(result_data, indent=2)}],
                            "isError": False
                        }
                    )
                
                # Special handling for call_tool meta-tool (invoke discovered tools)
                if call_params.name == "call_tool":
                    import json
                    tool_name = call_params.arguments.get("name", "")
                    tool_args = call_params.arguments.get("arguments", {})
                    
                    if not tool_name:
                        return MCPJSONRPCResponse(
                            id=jsonrpc_request.id,
                            result={
                                "content": [{"type": "text", "text": "Error: 'name' is required"}],
                                "isError": True
                            }
                        )
                    
                    # Proxy the call to the actual tool
                    result = await handle_tools_call(
                        db=db,
                        user=user,
                        client=client,
                        name=tool_name,
                        arguments=tool_args
                    )
                    return MCPJSONRPCResponse(id=jsonrpc_request.id, result=result.model_dump())
                
                # Regular tool call
                result = await handle_tools_call(
                    db=db,
                    user=user,
                    client=client,
                    name=call_params.name,
                    arguments=call_params.arguments
                )
                return MCPJSONRPCResponse(id=jsonrpc_request.id, result=result.model_dump())
            
            else:
                logger.warning(f"Unknown method: {method}")
                return MCPJSONRPCResponse(
                    id=jsonrpc_request.id,
                    error={
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                )
                
        except Exception as e:
            logger.error(f"Internal error processing {method}: {e}", exc_info=True)
            return MCPJSONRPCResponse(
                id=jsonrpc_request.id,
                error={
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            )


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
