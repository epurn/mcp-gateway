"""Service layer for tool registry with caching."""

import asyncio
from functools import lru_cache
from typing import TYPE_CHECKING

from cachetools import TTLCache

from src.auth.models import AuthenticatedUser
from src.auth.policy import check_tool_permission

from .models import RiskLevel, Tool
from .repository import get_all_active_tools, get_tool_by_name, create_tool, deactivate_tools_not_in_list
from .config import load_tool_registry
from .schemas import ToolResponse, ToolListResponse

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# Cache for tool definitions (5 minute TTL, max 1000 entries)
_tool_cache: TTLCache[str, list[Tool]] = TTLCache(maxsize=1000, ttl=300)


def clear_tool_cache() -> None:
    """Clear the tool cache. Useful after tool updates."""
    _tool_cache.clear()


async def sync_tools_from_config(db: "AsyncSession", config_path: str | None = None) -> None:
    """Ensure tool registry entries exist for the static config.

    Args:
        db: Async database session.
        config_path: Optional path override for the tool registry config.
    """
    registry_config = load_tool_registry(config_path)
    if not registry_config.tools:
        clear_tool_cache()
        return

    seen_names: set[str] = set()
    for tool in registry_config.tools:
        if tool.name in seen_names:
            raise ValueError(f"duplicate tool name in config: {tool.name}")
        seen_names.add(tool.name)

        existing = await get_tool_by_name(db, tool.name)
        if existing is None:
            await create_tool(
                db=db,
                name=tool.name,
                description=tool.description,
                backend_url=tool.backend_url,
                risk_level=tool.risk_level,
                required_roles=tool.required_roles or None,
                is_active=tool.is_active,
                input_schema=tool.input_schema,
            )
            continue

        updated = False
        if existing.description != tool.description:
            existing.description = tool.description
            updated = True
        if existing.backend_url != tool.backend_url:
            existing.backend_url = tool.backend_url
            updated = True
        if existing.risk_level.value != tool.risk_level:
            existing.risk_level = RiskLevel(tool.risk_level)
            updated = True
        if (existing.required_roles or None) != (tool.required_roles or None):
            existing.required_roles = tool.required_roles or None
            updated = True
        if existing.is_active != tool.is_active:
            existing.is_active = tool.is_active
            updated = True
        if existing.input_schema != tool.input_schema:
            existing.input_schema = tool.input_schema
            updated = True

        if updated:
            await db.commit()
            await db.refresh(existing)

    await deactivate_tools_not_in_list(db, seen_names)
    clear_tool_cache()


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
