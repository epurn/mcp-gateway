"""Tests for scoped MCP transport service behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.auth.exceptions import ToolNotAllowedError
from src.auth.models import AuthenticatedUser, UserClaims
from src.mcp_transport.service import handle_tools_call, handle_tools_list


def _user_all() -> AuthenticatedUser:
    return AuthenticatedUser(
        claims=UserClaims(user_id="user-1", roles=["developer"]),
        allowed_tools={"*"},
    )


def _user_limited() -> AuthenticatedUser:
    return AuthenticatedUser(
        claims=UserClaims(user_id="user-2", roles=["viewer"]),
        allowed_tools={"exact_calculate"},
    )


@pytest.mark.asyncio
async def test_tools_list_is_scoped_and_permission_filtered():
    db = AsyncMock()
    tools = [
        SimpleNamespace(
            name="exact_calculate",
            description="Calc",
            input_schema={"type": "object"},
            required_roles=None,
        ),
        SimpleNamespace(
            name="exact_statistics",
            description="Stats",
            input_schema={"type": "object"},
            required_roles=["admin"],
        ),
        SimpleNamespace(
            name="find_tools",
            description="Legacy meta tool",
            input_schema={"type": "object"},
            required_roles=None,
        ),
    ]

    with patch("src.mcp_transport.service.get_tools_by_scope_cached", new_callable=AsyncMock) as mock_scoped_tools:
        mock_scoped_tools.return_value = tools
        result = await handle_tools_list(db=db, user=_user_limited(), scope="calculator")

    names = [tool.name for tool in result.tools]
    assert names == ["exact_calculate"]


@pytest.mark.asyncio
async def test_tools_call_outside_scope_raises_tool_not_allowed():
    db = AsyncMock()
    client = AsyncMock()
    scoped_mismatch_tool = SimpleNamespace(
        name="document_generate",
        scope=SimpleNamespace(value="docs"),
    )

    with patch("src.mcp_transport.service.get_all_tools_cached", new_callable=AsyncMock) as mock_all_tools:
        with patch("src.mcp_transport.service.log_denied_tool_invocation", new_callable=AsyncMock):
            mock_all_tools.return_value = [scoped_mismatch_tool]
            with pytest.raises(ToolNotAllowedError):
                await handle_tools_call(
                    db=db,
                    user=_user_all(),
                    client=client,
                    scope="calculator",
                    name="document_generate",
                    arguments={"content": "x", "format": "pdf"},
                )


@pytest.mark.asyncio
async def test_tools_call_not_found_logs_denied_reason():
    db = AsyncMock()
    client = AsyncMock()

    with patch("src.mcp_transport.service.get_all_tools_cached", new_callable=AsyncMock) as mock_all_tools:
        with patch("src.mcp_transport.service.log_denied_tool_invocation", new_callable=AsyncMock) as mock_log_denied:
            mock_all_tools.return_value = []
            result = await handle_tools_call(
                db=db,
                user=_user_all(),
                client=client,
                scope="calculator",
                name="missing_tool",
                arguments={},
                endpoint_path="/calculator/sse",
            )

    assert result.isError is True
    assert "not found" in result.content[0].text
    mock_log_denied.assert_awaited_once_with(
        db=db,
        user_id="user-1",
        tool_name="missing_tool",
        endpoint_path="/calculator/sse",
        error_code="TOOL_NOT_FOUND",
    )


@pytest.mark.asyncio
async def test_tools_call_in_scope_invokes_gateway():
    db = AsyncMock()
    client = AsyncMock()
    scoped_tool = SimpleNamespace(
        name="exact_calculate",
        scope=SimpleNamespace(value="calculator"),
    )
    gateway_response = SimpleNamespace(
        error=None,
        tool_id=7,
        result={"answer": "42"},
    )

    with patch("src.mcp_transport.service.get_all_tools_cached", new_callable=AsyncMock) as mock_all_tools:
        with patch("src.mcp_transport.service.invoke_tool", new_callable=AsyncMock) as mock_invoke:
            with patch("src.mcp_transport.service.increment_tool_usage", new_callable=AsyncMock) as mock_increment:
                mock_all_tools.return_value = [scoped_tool]
                mock_invoke.return_value = gateway_response

                result = await handle_tools_call(
                    db=db,
                    user=_user_all(),
                    client=client,
                    scope="calculator",
                    name="exact_calculate",
                    arguments={"operator": "add", "operands": ["40", "2"]},
                )

    assert result.isError is False
    assert '"answer": "42"' in result.content[0].text
    mock_increment.assert_awaited_once_with(db, 7)
