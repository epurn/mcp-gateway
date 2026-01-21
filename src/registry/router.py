"""FastAPI router for tool registry endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.models import AuthenticatedUser
from src.database import get_db

from .schemas import ToolListResponse
from .service import get_tools_for_user


router = APIRouter(prefix="/mcp", tags=["tools"])


@router.get("/tools", response_model=ToolListResponse)
async def list_tools(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> ToolListResponse:
    """List all tools the authenticated user can access.
    
    Returns tools filtered by the user's roles and permissions
    as defined in the policy configuration.
    
    Requires: Valid JWT token in Authorization header.
    
    Returns:
        ToolListResponse with list of accessible tools and count.
    """
    return await get_tools_for_user(db, user)
