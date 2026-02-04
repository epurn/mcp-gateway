"""Business logic for MCP protocol handlers."""

import json
import os
from typing import Any, Literal
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from src.auth.models import AuthenticatedUser
from src.registry.service import get_tools_for_user
from src.gateway.service import invoke_tool
from src.gateway.schemas import InvokeToolRequest
from src.registry.filtering import extract_categories_from_prompt
from src.registry.embedding import generate_embedding
from src.registry.repository import (
    get_tools_by_categories,
    get_core_tools,
    search_tools_by_embedding,
    increment_tool_usage,
)

from .schemas import (
    MCPTool,
    MCPToolListResult,
    MCPToolCallResult,
    MCPContent,
    MCPInitializeParams,
)


async def handle_initialize(params: MCPInitializeParams) -> dict[str, Any]:
    """Handle initialize request.
    
    Args:
        params: Initialize parameters from client.
        
    Returns:
        Server initialization response.
    """
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "tools": {
                "listChanged": False  # Static tool list for now
            }
        },
        "serverInfo": {
            "name": "MCP Gateway",
            "version": "1.0.0"
        }
    }


async def handle_tools_list_smart(
    db: AsyncSession,
    user: AuthenticatedUser,
    context: str | None = None,
    strategy: Literal["all", "rule", "rag", "hybrid", "minimal"] = "minimal",
    max_tools: int = 15
) -> MCPToolListResult:
    """Handle tools/list with smart routing.
    
    Args:
        db: Database session
        user: Authenticated user
        context: User's prompt or conversation context
        strategy: Filtering strategy to use
        max_tools: Maximum tools to return
        
    Returns:
        Filtered list of relevant tools
    """
    # NEW: Minimal strategy - return only core tools from database
    # (find_tools is stored as a core tool in the registry)
    if strategy == "minimal":
        core_tools = await get_core_tools(db)
        
        mcp_tools = []
        for tool in core_tools:
            mcp_tools.append(MCPTool(
                name=tool.name,
                description=tool.description,
                inputSchema=tool.input_schema or {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": True
                }
            ))
        
        return MCPToolListResult(tools=mcp_tools)
    
    # LEGACY: Full smart routing for other strategies
    tools_to_return = []
    
    # Core strategy: Always get core tools first
    core_tools = await get_core_tools(db)
    tools_to_return.extend(core_tools)
    existing_names = {t.name for t in tools_to_return}
    
    if strategy == "all" or not context:
        # No filtering (beyond core), return all available tools
        tool_response = await get_tools_for_user(db, user)
        for t_resp in tool_response.tools:
            if t_resp.name not in existing_names:
                # Add enough info for MCPTool conversion later
                tools_to_return.append(t_resp)
                existing_names.add(t_resp.name)
                
    elif strategy == "rule":
        # Tier 2: Category-based filtering
        categories = extract_categories_from_prompt(context)
        if categories:
            category_tools = await get_tools_by_categories(db, list(categories), user.user_id)
            for tool in category_tools:
                if tool.name not in existing_names and len(tools_to_return) < max_tools:
                    tools_to_return.append(tool)
                    existing_names.add(tool.name)
        
    elif strategy == "rag":
        # Tier 3: Pure RAG-MCP approach
        try:
            query_embedding = await generate_embedding(context)
            rag_tools = await search_tools_by_embedding(
                db, query_embedding, top_k=max_tools - len(tools_to_return)
            )
            for tool in rag_tools:
                if tool.name not in existing_names and len(tools_to_return) < max_tools:
                    tools_to_return.append(tool)
                    existing_names.add(tool.name)
        except Exception:
            # Fallback to all if RAG fails
            tool_response = await get_tools_for_user(db, user)
            for t_resp in tool_response.tools:
                if t_resp.name not in existing_names and len(tools_to_return) < max_tools:
                    tools_to_return.append(t_resp)
                    existing_names.add(t_resp.name)
        
    elif strategy == "hybrid":
        # Tier 2: Rule-based category filtering
        categories = extract_categories_from_prompt(context)
        if categories:
            category_tools = await get_tools_by_categories(db, list(categories), user.user_id)
            for tool in category_tools:
                if tool.name not in existing_names and len(tools_to_return) < max_tools:
                    tools_to_return.append(tool)
                    existing_names.add(tool.name)
        
        # Tier 3: RAG fallback if we have < 10 tools
        if len(tools_to_return) < 10:
            try:
                query_embedding = await generate_embedding(context)
                rag_tools = await search_tools_by_embedding(
                    db, query_embedding, top_k=max_tools - len(tools_to_return)
                )
                for tool in rag_tools:
                    if tool.name not in existing_names and len(tools_to_return) < max_tools:
                        tools_to_return.append(tool)
                        existing_names.add(tool.name)
            except Exception:
                pass
    
    # Convert to MCP format
    mcp_tools = []
    for tool in tools_to_return:
        # Handle both physical Tool models and ToolResponse schemas
        name = getattr(tool, "name")
        description = getattr(tool, "description")
        input_schema = getattr(tool, "input_schema", None)
        
        mcp_tools.append(MCPTool(
            name=name,
            description=description,
            inputSchema=input_schema or {
                "type": "object",
                "properties": {},
                "additionalProperties": True
            }
        ))
    
    return MCPToolListResult(tools=mcp_tools)


async def handle_find_tools(
    db: AsyncSession,
    query: str,
    max_results: int = 5
) -> dict:
    """Handle find_tools meta-tool call.
    
    Searches for tools using semantic similarity and returns their full schemas
    so the LLM can use them immediately.
    
    Args:
        db: Database session
        query: What the user wants to do (e.g., "generate PDF", "calculate average")
        max_results: Maximum number of tools to return
        
    Returns:
        Dictionary with discovered tools and their schemas
    """
    try:
        # Use semantic search to find relevant tools
        query_embedding = await generate_embedding(query)
        tools = await search_tools_by_embedding(
            db, 
            query_embedding, 
            top_k=max_results,
            threshold=0.3
        )
        
        # Return tool schemas that LLM can use immediately
        discovered_tools = []
        for tool in tools:
            discovered_tools.append({
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema or {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": True
                }
            })
        
        return {
            "query": query,
            "found": len(discovered_tools),
            "tools": discovered_tools,
            "message": f"Found {len(discovered_tools)} tool(s) matching '{query}'. You can now use these tools directly."
        }
    except Exception as e:
        return {
            "query": query,
            "found": 0,
            "tools": [],
            "error": str(e),
            "message": "Tool search failed. Please try a different query."
        }


async def handle_tools_list(
    db: AsyncSession,
    user: AuthenticatedUser,
    context: str | None = None
) -> MCPToolListResult:
    """Handle tools/list request with smart routing.
    
    Args:
        db: Database session.
        user: Authenticated user.
        context: Optional context for tool filtering.
        
    Returns:
        List of tools available to the user.
    """
    strategy = os.getenv("TOOL_FILTER_STRATEGY", "minimal")
    return await handle_tools_list_smart(db, user, context, strategy=strategy)


async def handle_tools_call(
    db: AsyncSession,
    user: AuthenticatedUser,
    client: httpx.AsyncClient,
    name: str,
    arguments: dict[str, Any]
) -> MCPToolCallResult:
    """Handle tools/call request.
    
    Args:
        db: Database session.
        user: Authenticated user.
        client: HTTP client for backend requests.
        name: Tool name to invoke.
        arguments: Tool arguments.
        
    Returns:
        Tool execution result.
    """
    # Create invoke request
    request = InvokeToolRequest(
        tool_name=name,
        arguments=arguments
    )
    
    try:
        # Use existing gateway invoke logic
        response = await invoke_tool(
            db=db,
            user=user,
            request=request,
            client=client
        )
        
        # Increment usage counter if successful
        if not response.error and response.tool_id:
            await increment_tool_usage(db, response.tool_id)
        
        # Convert gateway response to MCP format
        if response.error:
            return MCPToolCallResult(
                content=[MCPContent(
                    type="text",
                    text=f"Error: {response.error.message}"
                )],
                isError=True
            )
        
        # Format successful result as text content
        result_text = json.dumps(response.result, indent=2)
        return MCPToolCallResult(
            content=[MCPContent(
                type="text",
                text=result_text
            )],
            isError=False
        )
        
    except Exception as e:
        return MCPToolCallResult(
            content=[MCPContent(
                type="text",
                text=f"Exception: {str(e)}"
            )],
            isError=True
        )
