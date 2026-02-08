"""Business logic for MCP protocol handlers."""

import json
import re
from typing import Any, Literal
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from src.audit import log_denied_tool_invocation
from src.auth.models import AuthenticatedUser
from src.auth.exceptions import ToolNotAllowedError
from src.registry.service import get_tools_for_user, get_all_tools_cached, get_tools_by_scope_cached
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

META_TOOL_NAMES = {"find_tools", "call_tool"}


def _default_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    }


def _build_meta_tools() -> list[MCPTool]:
    return [
        MCPTool(
            name="find_tools",
            description="Discover available tools by intent and return tool schemas.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "User intent or task description."},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        MCPTool(
            name="call_tool",
            description="Invoke a discovered tool by name with explicit arguments.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Discovered tool name to invoke."},
                    "arguments": {"type": "object", "default": {}},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        ),
    ]


def _to_mcp_tool(tool: Any) -> MCPTool:
    return MCPTool(
        name=getattr(tool, "name"),
        description=getattr(tool, "description"),
        inputSchema=getattr(tool, "input_schema", None) or _default_input_schema(),
    )


def _merge_with_meta_tools(tools: list[MCPTool]) -> list[MCPTool]:
    merged: list[MCPTool] = []
    seen_names: set[str] = set()

    for tool in [*_build_meta_tools(), *tools]:
        if tool.name in seen_names:
            continue
        merged.append(tool)
        seen_names.add(tool.name)

    return merged


def _is_tool_accessible(tool: Any, user: AuthenticatedUser) -> bool:
    if "*" not in user.allowed_tools and getattr(tool, "name", "") not in user.allowed_tools:
        return False

    required_roles = getattr(tool, "required_roles", None) or []
    if required_roles and not any(role in user.roles for role in required_roles):
        return False

    return True


def _tool_discovery_payload(tool: Any) -> dict[str, Any]:
    return {
        "name": getattr(tool, "name"),
        "description": getattr(tool, "description"),
        "inputSchema": getattr(tool, "input_schema", None) or _default_input_schema(),
    }


def _tool_match_score(tool: Any, query: str, categories: set[str]) -> int:
    query_lower = query.lower().strip()
    if not query_lower:
        return 0

    name = (getattr(tool, "name", "") or "").lower()
    description = (getattr(tool, "description", "") or "").lower()
    text = f"{name} {description}"

    score = 0
    if query_lower in text:
        score += 5

    terms = [term for term in re.split(r"[^a-z0-9]+", query_lower) if term]
    for term in terms:
        if term in name:
            score += 3
        elif term in description:
            score += 1

    tool_categories = set(getattr(tool, "categories", []) or [])
    if categories and tool_categories.intersection(categories):
        score += 2

    return score


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
    if strategy == "minimal":
        core_tools = await get_core_tools(db)
        mcp_tools = [_to_mcp_tool(tool) for tool in core_tools]
        return MCPToolListResult(tools=_merge_with_meta_tools(mcp_tools))
    
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
    mcp_tools = [_to_mcp_tool(tool) for tool in tools_to_return]
    return MCPToolListResult(tools=_merge_with_meta_tools(mcp_tools))


async def handle_find_tools(
    db: AsyncSession,
    user: AuthenticatedUser,
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
    errors: list[str] = []
    query = (query or "").strip()
    max_results = max(1, min(max_results, 20))

    semantic_tools: list[Any] = []
    if query:
        try:
            query_embedding = await generate_embedding(query)
            semantic_tools = await search_tools_by_embedding(
                db,
                query_embedding,
                top_k=max_results,
                threshold=0.3,
            )
        except Exception as e:
            errors.append(str(e))

    discovered_tools: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for tool in semantic_tools:
        if not _is_tool_accessible(tool, user):
            continue
        name = getattr(tool, "name", "")
        if name in seen_names:
            continue
        discovered_tools.append(_tool_discovery_payload(tool))
        seen_names.add(name)

    if len(discovered_tools) < max_results:
        all_tools = await get_all_tools_cached(db)
        accessible_tools = [tool for tool in all_tools if _is_tool_accessible(tool, user)]
        categories = extract_categories_from_prompt(query)

        ranked = sorted(
            accessible_tools,
            key=lambda tool: (
                _tool_match_score(tool, query, categories),
                getattr(tool, "name", ""),
            ),
            reverse=True,
        )
        for tool in ranked:
            name = getattr(tool, "name", "")
            if name in seen_names:
                continue
            if query and _tool_match_score(tool, query, categories) <= 0:
                continue
            discovered_tools.append(_tool_discovery_payload(tool))
            seen_names.add(name)
            if len(discovered_tools) >= max_results:
                break

    response: dict[str, Any] = {
        "query": query,
        "found": len(discovered_tools),
        "tools": discovered_tools,
        "message": f"Found {len(discovered_tools)} tool(s) matching '{query}'. You can now use these tools directly.",
    }
    if errors and len(discovered_tools) == 0:
        response["error"] = "; ".join(errors)
    return response


async def handle_tools_list(
    db: AsyncSession,
    user: AuthenticatedUser,
    scope: str,
    context: str | None = None
) -> MCPToolListResult:
    """Handle tools/list request scoped to a single endpoint.
    
    Args:
        db: Database session.
        user: Authenticated user.
        scope: Endpoint scope.
        context: Unused in v2 scoped list flow.
        
    Returns:
        List of tools available to the user.
    """
    scoped_tools = await get_tools_by_scope_cached(db, scope)
    visible_tools = [
        _to_mcp_tool(tool)
        for tool in scoped_tools
        if _is_tool_accessible(tool, user) and getattr(tool, "name", "") not in META_TOOL_NAMES
    ]
    return MCPToolListResult(tools=visible_tools)


async def handle_tools_call(
    db: AsyncSession,
    user: AuthenticatedUser,
    client: httpx.AsyncClient,
    scope: str,
    name: str,
    arguments: dict[str, Any],
    endpoint_path: str = "/unknown",
) -> MCPToolCallResult:
    """Handle tools/call request.
    
    Args:
        db: Database session.
        user: Authenticated user.
        client: HTTP client for backend requests.
        scope: Endpoint scope.
        name: Tool name to invoke.
        arguments: Tool arguments.
        endpoint_path: API endpoint path used for invocation.
        
    Returns:
        Tool execution result.
    """
    all_tools = await get_all_tools_cached(db)
    tool = next((t for t in all_tools if t.name == name), None)
    if tool is None:
        await log_denied_tool_invocation(
            db=db,
            user_id=user.user_id,
            tool_name=name,
            endpoint_path=endpoint_path,
            error_code="TOOL_NOT_FOUND",
        )
        return MCPToolCallResult(
            content=[MCPContent(type="text", text=f"Error: Tool '{name}' not found")],
            isError=True,
        )

    if tool.scope.value != scope:
        await log_denied_tool_invocation(
            db=db,
            user_id=user.user_id,
            tool_name=name,
            endpoint_path=endpoint_path,
            error_code="TOOL_NOT_IN_SCOPE",
        )
        raise ToolNotAllowedError(tool_name=name, user_id=user.user_id)

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
            client=client,
            endpoint_path=endpoint_path,
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
        
    except ToolNotAllowedError:
        raise
    except Exception as e:
        return MCPToolCallResult(
            content=[MCPContent(
                type="text",
                text=f"Exception: {str(e)}"
            )],
            isError=True
        )
