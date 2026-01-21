"""Repository layer for tool registry data access."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Tool


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
    risk_level: str = "low",
    required_roles: list[str] | None = None,
    is_active: bool = True
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
        
    Returns:
        Created Tool object.
    """
    from .models import RiskLevel
    
    tool = Tool(
        name=name,
        description=description,
        backend_url=backend_url,
        risk_level=RiskLevel(risk_level),
        required_roles=required_roles,
        is_active=is_active
    )
    db.add(tool)
    await db.commit()
    await db.refresh(tool)
    return tool
