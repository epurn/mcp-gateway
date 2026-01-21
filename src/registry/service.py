"""Service layer for tool registry with caching."""

import asyncio
from functools import lru_cache
from typing import TYPE_CHECKING

from cachetools import TTLCache

from src.auth.models import AuthenticatedUser
from src.auth.policy import check_tool_permission

from .models import Tool
from .repository import get_all_active_tools
from .schemas import ToolResponse, ToolListResponse

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# Cache for tool definitions (5 minute TTL, max 1000 entries)
_tool_cache: TTLCache[str, list[Tool]] = TTLCache(maxsize=1000, ttl=300)


def clear_tool_cache() -> None:
    """Clear the tool cache. Useful after tool updates."""
    _tool_cache.clear()


async def get_all_tools_cached(db: "AsyncSession") -> list[Tool]:
    """Get all active tools with caching.
    
    Returns cached results if available and within TTL.
    Otherwise fetches from database and caches the result.
    
    Args:
        db: Async database session.
        
    Returns:
        List of active Tool objects.
    """
    cache_key = "all_active_tools"
    
    if cache_key in _tool_cache:
        return _tool_cache[cache_key]
    
    tools = await get_all_active_tools(db)
    _tool_cache[cache_key] = tools
    return tools


async def get_tools_for_user(
    db: "AsyncSession",
    user: AuthenticatedUser
) -> ToolListResponse:
    """Get all tools filtered by user permissions.
    
    Fetches active tools from the database (with caching) and filters
    them based on the user's allowed_tools set from their JWT claims.
    
    Args:
        db: Async database session.
        user: Authenticated user with claims and permissions.
        
    Returns:
        ToolListResponse with filtered tool list.
    """
    all_tools = await get_all_tools_cached(db)
    
    # Filter tools based on user permissions
    filtered_tools: list[ToolResponse] = []
    
    for tool in all_tools:
        # Check if user has wildcard access or specific tool access
        if "*" in user.allowed_tools or tool.name in user.allowed_tools:
            # Also check tool-specific required_roles if set
            if tool.required_roles:
                # Tool has role requirements - check if user has any required role
                if not any(role in user.roles for role in tool.required_roles):
                    continue
            
            filtered_tools.append(ToolResponse(
                name=tool.name,
                description=tool.description,
                backend_url=tool.backend_url,
                risk_level=tool.risk_level.value
            ))
    
    return ToolListResponse(tools=filtered_tools, count=len(filtered_tools))
