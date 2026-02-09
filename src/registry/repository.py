"""Repository layer for tool registry data access."""

from sqlalchemy import select, update, func, cast, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import ARRAY

from .models import Tool, ToolScope, PGVECTOR_AVAILABLE


async def get_all_active_tools(db: AsyncSession) -> list[Tool]:
    """Fetch all active tools from the database.
    
    Args:
        db: Async database session.
        
    Returns:
        List of active Tool objects.
    """
    stmt = select(Tool).where(Tool.is_active == True).order_by(Tool.name)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_active_tools_by_scope(db: AsyncSession, scope: str) -> list[Tool]:
    """Fetch all active tools in a single scope."""
    stmt = (
        select(Tool)
        .where(Tool.is_active == True, Tool.scope == ToolScope(scope))
        .order_by(Tool.name)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_tool_by_name(db: AsyncSession, name: str) -> Tool | None:
    """Fetch a single tool by its name.
    
    Args:
        db: Async database session.
        name: Tool name to look up.
        
    Returns:
        Tool object if found, None otherwise.
    """
    stmt = select(Tool).where(Tool.name == name)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_tool(
    db: AsyncSession,
    name: str,
    description: str,
    backend_url: str,
    scope: str,
    risk_level: str = "low",
    required_roles: list[str] | None = None,
    is_active: bool = True,
    input_schema: dict | None = None,
) -> Tool:
    """Create a new tool in the registry.
    
    Args:
        db: Async database session.
        name: Unique tool identifier.
        description: Human-readable description.
        backend_url: URL to route requests to.
        risk_level: Risk classification (low, medium, high).
        required_roles: Optional role requirements.
        is_active: Whether tool is available.
        input_schema: Optional JSON schema for tool arguments.
        
    Returns:
        Created Tool object.
    """
    from .models import RiskLevel
    
    tool = Tool(
        name=name,
        description=description,
        backend_url=backend_url,
        scope=ToolScope(scope),
        risk_level=RiskLevel(risk_level),
        required_roles=required_roles,
        is_active=is_active,
        input_schema=input_schema,
    )
    db.add(tool)
    await db.commit()
    await db.refresh(tool)
    return tool


async def get_tools_by_categories(
    db: AsyncSession,
    categories: list[str],
    user_id: str | None = None
) -> list[Tool]:
    """Get tools matching any of the specified categories."""
    query = select(Tool).where(Tool.is_active == True)
    
    # Filter by categories (matches ANY category in the list)
    if categories:
        query = query.where(
            Tool.categories.overlap(cast(categories, ARRAY(String(50))))
        )
    
    # Apply user permissions if needed
    # ... (extend with your auth logic)
    
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_core_tools(db: AsyncSession) -> list[Tool]:
    """Get core tools that should always be available."""
    query = select(Tool).where(
        Tool.is_active == True,
        Tool.categories.overlap(cast(['core'], ARRAY(String(50))))
    )
    result = await db.execute(query)
    return list(result.scalars().all())


async def search_tools_by_embedding(
    db: AsyncSession,
    query_embedding: list[float],
    top_k: int = 10,
    threshold: float = 0.7
) -> list[Tool]:
    """Search tools using vector similarity (RAG-MCP)."""
    if not PGVECTOR_AVAILABLE:
        raise RuntimeError("pgvector not available")
    
    # Cosine similarity search with threshold
    # pgvector distance = 1 - cosine_similarity
    query = select(Tool).where(
        Tool.is_active == True,
        Tool.embedding.isnot(None),
        Tool.embedding.cosine_distance(query_embedding) < (1.0 - threshold)
    ).order_by(
        Tool.embedding.cosine_distance(query_embedding)
    ).limit(top_k)
    
    result = await db.execute(query)
    return list(result.scalars().all())


async def increment_tool_usage(
    db: AsyncSession,
    tool_id: int
) -> None:
    """Increment usage counter for a tool."""
    await db.execute(
        update(Tool)
        .where(Tool.id == tool_id)
        .values(
            usage_count=Tool.usage_count + 1,
            last_used_at=func.now()
        )
    )
    await db.commit()


async def deactivate_tools_not_in_list(
    db: AsyncSession,
    active_names: set[str]
) -> int:
    """Deactivate tools that are not present in the provided name set.

    Args:
        db: Async database session.
        active_names: Tool names that should remain active.

    Returns:
        Number of rows updated.
    """
    if not active_names:
        return 0

    result = await db.execute(
        update(Tool)
        .where(Tool.name.notin_(active_names))
        .values(is_active=False)
    )
    await db.commit()
    return result.rowcount or 0
