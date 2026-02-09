"""Route-level tests for scoped MCP SSE transport."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse

from src.auth.dependencies import get_current_user
from src.auth.models import AuthenticatedUser, UserClaims
from src.auth.exceptions import AuthorizationError
from src.database import get_db
from src.dependencies import get_http_client
from src.mcp_transport.sse import router as mcp_router
from src.ratelimit.exceptions import RateLimitExceededError
from src.ratelimit.limiter import RateLimitResult


def _initialize_payload() -> dict:
    return {
        "jsonrpc": "2.0",
        "id": "req-1",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        },
    }


def _tool_call_payload(name: str, arguments: dict | None = None) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": "req-2",
        "method": "tools/call",
        "params": {
            "name": name,
            "arguments": arguments or {},
        },
    }


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(mcp_router)

    @app.exception_handler(AuthorizationError)
    async def authorization_error_handler(request, exc: AuthorizationError):
        return JSONResponse(
            status_code=403,
            content={"error": exc.code, "message": exc.message},
        )

    @app.exception_handler(RateLimitExceededError)
    async def rate_limit_handler(request, exc: RateLimitExceededError):
        return JSONResponse(
            status_code=429,
            content={"error": exc.code, "message": exc.message},
            headers={"Retry-After": str(int(exc.retry_after) + 1)},
        )

    async def mock_auth_success():
        return AuthenticatedUser(
            claims=UserClaims(user_id="u1", roles=["developer"]),
            allowed_tools={"*"},
        )

    async def mock_get_db():
        yield AsyncMock()

    async def mock_http_client():
        return AsyncMock()

    app.dependency_overrides[get_current_user] = mock_auth_success
    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[get_http_client] = mock_http_client
    with TestClient(app) as test_client:
        yield test_client


def test_scoped_sse_post_initialize_succeeds(client):
    response = client.post("/calculator/sse", json=_initialize_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["protocolVersion"] == "2024-11-05"


def test_unknown_scope_returns_404(client):
    response = client.post("/invalid/sse", json=_initialize_payload())
    assert response.status_code == 404
    assert response.json()["error"]["code"] == -32010
    assert "Invalid endpoint scope" in response.json()["error"]["message"]


def test_unified_sse_endpoint_removed(client):
    response = client.post("/sse", json=_initialize_payload())
    assert response.status_code == 404


def test_legacy_messages_endpoint_removed(client):
    response = client.post("/messages", json=_initialize_payload())
    assert response.status_code == 404


@pytest.mark.parametrize("meta_tool_name", ["find_tools", "call_tool"])
def test_meta_tool_call_returns_removed_error(client, meta_tool_name):
    response = client.post(
        "/calculator/sse",
        json=_tool_call_payload(meta_tool_name, {"query": "calculate"}),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error"]["code"] == -32012
    assert meta_tool_name in body["error"]["message"]
    assert "removed in v2" in body["error"]["message"]


def test_tool_call_outside_scope_returns_403(client):
    with patch("src.mcp_transport.service.get_all_tools_cached", new_callable=AsyncMock) as mock_get_tools:
        with patch("src.mcp_transport.service.log_denied_tool_invocation", new_callable=AsyncMock):
            mock_get_tools.return_value = [
                SimpleNamespace(
                    name="document_generate",
                    scope=SimpleNamespace(value="docs"),
                )
            ]
            response = client.post(
                "/calculator/sse",
                json=_tool_call_payload("document_generate", {"content": "x", "format": "pdf"}),
            )

    assert response.status_code == 200
    assert response.json()["error"]["code"] == -32011
    assert "not available on endpoint" in response.json()["error"]["message"]


def test_tools_call_rate_limit_returns_429(client):
    denied = RateLimitResult(
        allowed=False,
        limit=100,
        remaining=0,
        reset_at=0,
        retry_after=1.2,
    )
    with patch("src.mcp_transport.sse.check_rate_limit", return_value=denied):
        response = client.post(
            "/calculator/sse",
            json=_tool_call_payload("exact_calculate", {"operator": "add", "operands": ["1", "2"]}),
        )

    assert response.status_code == 429
    assert response.json()["error"] == "RATE_LIMIT_EXCEEDED"


def test_tools_call_checks_rate_limit_with_user_and_tool(client):
    allowed = RateLimitResult(
        allowed=True,
        limit=1000,
        remaining=999,
        reset_at=0,
        retry_after=0.0,
    )
    with patch("src.mcp_transport.sse.check_rate_limit", return_value=allowed) as mock_rate_limit:
        with patch("src.mcp_transport.sse.handle_tools_call", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = SimpleNamespace(
                model_dump=lambda: {"content": [{"type": "text", "text": "{}"}], "isError": False}
            )
            client.post(
                "/calculator/sse",
                json=_tool_call_payload("exact_calculate", {"operator": "add", "operands": ["1", "2"]}),
            )

    _, kwargs = mock_rate_limit.call_args
    assert kwargs["user_id"] == "u1"
    assert kwargs["tool_name"] == "exact_calculate"
