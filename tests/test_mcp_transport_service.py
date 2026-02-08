"""Tests for MCP transport service tool listing behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.auth.models import AuthenticatedUser, UserClaims
from src.mcp_transport.service import handle_find_tools, handle_tools_list_smart
from src.registry.schemas import ToolListResponse, ToolResponse


def _user() -> AuthenticatedUser:
    return AuthenticatedUser(
        claims=UserClaims(user_id="user-1", roles=["analyst"]),
        allowed_tools={"*"},
    )


def _limited_user() -> AuthenticatedUser:
    return AuthenticatedUser(
        claims=UserClaims(user_id="user-2", roles=["analyst"]),
        allowed_tools={"exact_calculate"},
    )


@pytest.mark.asyncio
async def test_tools_list_minimal_includes_meta_tools_when_registry_core_is_empty():
    db = AsyncMock()

    with patch("src.mcp_transport.service.get_core_tools", new_callable=AsyncMock) as mock_get_core_tools:
        mock_get_core_tools.return_value = []
        result = await handle_tools_list_smart(db=db, user=_user(), strategy="minimal")

    names = [tool.name for tool in result.tools]
    assert names == ["find_tools", "call_tool"]


@pytest.mark.asyncio
async def test_tools_list_minimal_keeps_meta_tools_authoritative_when_names_collide():
    db = AsyncMock()
    duplicate_db_tool = SimpleNamespace(
        name="call_tool",
        description="DB-defined duplicate",
        input_schema={"type": "object", "properties": {"unexpected": {"type": "string"}}},
    )

    with patch("src.mcp_transport.service.get_core_tools", new_callable=AsyncMock) as mock_get_core_tools:
        mock_get_core_tools.return_value = [duplicate_db_tool]
        result = await handle_tools_list_smart(db=db, user=_user(), strategy="minimal")

    names = [tool.name for tool in result.tools]
    assert names.count("call_tool") == 1

    call_tool = next(tool for tool in result.tools if tool.name == "call_tool")
    assert "name" in call_tool.inputSchema["properties"]
    assert "unexpected" not in call_tool.inputSchema["properties"]


@pytest.mark.asyncio
async def test_tools_list_all_preserves_db_discovery_and_adds_meta_tools():
    db = AsyncMock()
    user_tools = ToolListResponse(
        tools=[
            ToolResponse(
                name="exact_calculate",
                description="Deterministic high-precision arithmetic calculations.",
                backend_url="http://calculator:8000/mcp",
                risk_level="low",
            )
        ],
        count=1,
    )

    with patch("src.mcp_transport.service.get_core_tools", new_callable=AsyncMock) as mock_get_core_tools:
        with patch("src.mcp_transport.service.get_tools_for_user", new_callable=AsyncMock) as mock_get_tools_for_user:
            mock_get_core_tools.return_value = []
            mock_get_tools_for_user.return_value = user_tools

            result = await handle_tools_list_smart(db=db, user=_user(), strategy="all")

    names = [tool.name for tool in result.tools]
    assert names[:2] == ["find_tools", "call_tool"]
    assert "exact_calculate" in names
    assert len(names) == 3


@pytest.mark.asyncio
async def test_find_tools_falls_back_to_keyword_match_when_semantic_search_is_empty():
    db = AsyncMock()
    tools = [
        SimpleNamespace(
            name="exact_calculate",
            description="Deterministic high-precision arithmetic calculations.",
            input_schema={"type": "object", "properties": {"operator": {"type": "string"}}},
            required_roles=None,
            categories=["math"],
        ),
        SimpleNamespace(
            name="document_generate",
            description="Deterministic document generation for PDF/DOCX artifacts.",
            input_schema={"type": "object", "properties": {"format": {"type": "string"}}},
            required_roles=None,
            categories=["document"],
        ),
    ]

    with patch("src.mcp_transport.service.generate_embedding", new_callable=AsyncMock) as mock_embedding:
        with patch("src.mcp_transport.service.search_tools_by_embedding", new_callable=AsyncMock) as mock_search:
            with patch("src.mcp_transport.service.get_all_tools_cached", new_callable=AsyncMock) as mock_all_tools:
                mock_embedding.return_value = [0.0] * 384
                mock_search.return_value = []
                mock_all_tools.return_value = tools

                result = await handle_find_tools(
                    db=db,
                    user=_user(),
                    query="calculate",
                    max_results=5,
                )

    assert result["found"] >= 1
    returned_names = [tool["name"] for tool in result["tools"]]
    assert "exact_calculate" in returned_names


@pytest.mark.asyncio
async def test_find_tools_applies_user_permissions_in_fallback_results():
    db = AsyncMock()
    tools = [
        SimpleNamespace(
            name="exact_calculate",
            description="Deterministic high-precision arithmetic calculations.",
            input_schema={"type": "object", "properties": {"operator": {"type": "string"}}},
            required_roles=None,
            categories=["math"],
        ),
        SimpleNamespace(
            name="document_generate",
            description="Deterministic document generation for PDF/DOCX artifacts.",
            input_schema={"type": "object", "properties": {"format": {"type": "string"}}},
            required_roles=None,
            categories=["document"],
        ),
    ]

    with patch("src.mcp_transport.service.generate_embedding", new_callable=AsyncMock) as mock_embedding:
        with patch("src.mcp_transport.service.search_tools_by_embedding", new_callable=AsyncMock) as mock_search:
            with patch("src.mcp_transport.service.get_all_tools_cached", new_callable=AsyncMock) as mock_all_tools:
                mock_embedding.return_value = [0.0] * 384
                mock_search.return_value = []
                mock_all_tools.return_value = tools

                result = await handle_find_tools(
                    db=db,
                    user=_limited_user(),
                    query="document",
                    max_results=5,
                )

    returned_names = [tool["name"] for tool in result["tools"]]
    assert "document_generate" not in returned_names
