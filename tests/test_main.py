"""Integration tests for the main application."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from src.main import app
from src.auth.dependencies import get_current_user
from src.auth.models import AuthenticatedUser, UserClaims
from src.auth.exceptions import AuthenticationError

# Mock the lifespan context to avoid DB connection and set up mocks
@pytest.fixture(scope="module", autouse=True)
def mock_lifespan():
    with patch("src.main.lifespan", new_callable=AsyncMock) as mock_lifespan:
        # We need to manually set the state that lifespan would have set
        app.state.http_client = AsyncMock()
        yield
        # Clean up
        if hasattr(app.state, "http_client"):
            del app.state.http_client

client = TestClient(app)


def test_health_check():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "app": "MCP Gateway"}

def test_auth_error_handler():
    """Test that AuthenticationError returns 401."""
    # The /mcp/tools endpoint requires auth.
    # Without a token, the dependency raises HTTPException or our custom error?
    # Our dependency raises InvalidTokenError (which should be mapped or inherit).
    # InvalidTokenError inherits from MCPGatewayError? No, let's check.
    # If dependencies raise HTTPException, we might check that.
    # But let's check if we can simulate our custom AuthenticationError.
    
    # We'll use a route that definitely raises AuthenticationError
    # or rely on the fact that missing auth usually triggers the default FastAPI 401 or our deps.
    
    # Let's override the dependency to raise our specific error
    async def mock_auth_raise():
        raise AuthenticationError("Custom auth error")
        
    app.dependency_overrides[get_current_user] = mock_auth_raise
    try:
        response = client.get("/mcp/tools")
        assert response.status_code == 401
        assert response.json()["error"] == "AuthenticationError"
    finally:
        del app.dependency_overrides[get_current_user]

def test_payload_too_large_handler():
    """Test PayloadTooLargeError returns 413."""
    # We need to bypass auth to reach the service layer where validation happens,
    # OR override auth to succeed.
    
    async def mock_auth_success():
        return AuthenticatedUser(
            claims=UserClaims(user_id="u1", roles=[]),
            allowed_tools={"*"}
        )
        
    app.dependency_overrides[get_current_user] = mock_auth_success
    
    # Mock invoke_tool to raise PayloadTooLargeError
    from src.gateway.exceptions import PayloadTooLargeError
    
    # We need to patch where the router imports invoke_tool or match the route
    with patch("src.gateway.router.invoke_tool", side_effect=PayloadTooLargeError(200, 100)):
        try:
            response = client.post("/mcp/invoke", json={
                "tool_name": "test",
                "arguments": {}
            })
            assert response.status_code == 413
            assert response.json()["error"] == "PAYLOAD_TOO_LARGE"
        finally:
             del app.dependency_overrides[get_current_user]

def test_tool_not_found_handler():
    """Test ToolNotFoundError returns 404."""
    async def mock_auth_success():
        return AuthenticatedUser(
            claims=UserClaims(user_id="u1", roles=[]),
            allowed_tools={"*"}
        )
        
    app.dependency_overrides[get_current_user] = mock_auth_success
    
    from src.gateway.exceptions import ToolNotFoundError
    
    with patch("src.gateway.router.invoke_tool", side_effect=ToolNotFoundError("missing")):
        try:
            response = client.post("/mcp/invoke", json={
                "tool_name": "missing",
                "arguments": {}
            })
            assert response.status_code == 404
            assert response.json()["error"] == "TOOL_NOT_FOUND"
        finally:
            del app.dependency_overrides[get_current_user]

def test_openapi_schema_generated():
    """Test that OpenAPI schema is generated successfully."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "openapi" in response.json()
    assert "paths" in response.json()

