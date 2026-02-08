"""Unit tests for the MCP Gateway module."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from src.gateway.schemas import (
    MCPRequest,
    MCPResponse,
    MCPToolCallParams,
    MCPErrorDetail,
    MCPErrorCodes,
    InvokeToolRequest,
)
from src.gateway.exceptions import (
    BackendTimeoutError,
    BackendUnavailableError,
    PayloadTooLargeError,
    ToolNotFoundError,
    BackendError,
)
from src.gateway.service import validate_payload_size, invoke_tool
from src.gateway.proxy import forward_to_backend, forward_tool_call
from src.auth.models import AuthenticatedUser, UserClaims
from src.registry.models import Tool, RiskLevel
from src.config import get_settings


class TestMCPSchemas:
    """Tests for MCP JSON-RPC schemas."""
    
    def test_mcp_request_serialization(self):
        """Test MCPRequest creates valid JSON-RPC structure."""
        request = MCPRequest(
            method="tools/call",
            params=MCPToolCallParams(name="read_file", arguments={"path": "/test"}),
            id="req-123"
        )
        
        data = request.model_dump()
        assert data["jsonrpc"] == "2.0"
        assert data["method"] == "tools/call"
        assert data["params"]["name"] == "read_file"
        assert data["id"] == "req-123"
    
    def test_mcp_response_success(self):
        """Test creating success response."""
        response = MCPResponse.success(id="req-123", result={"content": "file data"})
        
        assert response.jsonrpc == "2.0"
        assert response.id == "req-123"
        assert response.result == {"content": "file data"}
        assert response.error is None
    
    def test_mcp_response_error(self):
        """Test creating error response."""
        response = MCPResponse.error_response(
            id="req-456",
            code=MCPErrorCodes.TOOL_NOT_FOUND,
            message="Tool not found"
        )
        
        assert response.jsonrpc == "2.0"
        assert response.id == "req-456"
        assert response.result is None
        assert response.error.code == -32001
        assert response.error.message == "Tool not found"
    
    def test_invoke_tool_request(self):
        """Test InvokeToolRequest schema."""
        request = InvokeToolRequest(
            tool_name="write_file",
            arguments={"path": "/test", "content": "hello"}
        )
        
        assert request.tool_name == "write_file"
        assert request.arguments["content"] == "hello"


class TestPayloadValidation:
    """Tests for payload size validation."""
    
    def test_valid_payload_size(self):
        """Test that small payloads pass validation."""
        # Should not raise
        validate_payload_size({"key": "value"}, max_bytes=1024)
    
    def test_payload_too_large(self):
        """Test that oversized payloads are rejected."""
        large_data = {"data": "x" * 1000}
        
        with pytest.raises(PayloadTooLargeError):
            validate_payload_size(large_data, max_bytes=100)
    
    def test_payload_exactly_at_limit(self):
        """Test payload at exact size limit."""
        # 13 bytes: {"a": "b"}
        validate_payload_size({"a": "b"}, max_bytes=15)  # Should pass


class TestGatewayExceptions:
    """Tests for gateway exception classes."""
    
    def test_backend_timeout_error(self):
        """Test BackendTimeoutError attributes."""
        exc = BackendTimeoutError(backend_url="http://backend:8000", timeout_seconds=30.0)
        
        assert exc.backend_url == "http://backend:8000"
        assert exc.timeout_seconds == 30.0
        assert "timed out" in exc.message
        assert exc.code == "BACKEND_TIMEOUT"
    
    def test_backend_unavailable_error(self):
        """Test BackendUnavailableError attributes."""
        exc = BackendUnavailableError(backend_url="http://backend:8000", reason="Connection refused")
        
        assert exc.backend_url == "http://backend:8000"
        assert "unavailable" in exc.message
        assert exc.code == "BACKEND_UNAVAILABLE"
    
    def test_payload_too_large_error(self):
        """Test PayloadTooLargeError attributes."""
        exc = PayloadTooLargeError(size_bytes=2000000, max_bytes=1000000)
        
        assert exc.size_bytes == 2000000
        assert exc.max_bytes == 1000000
        assert "2000000" in exc.message
        assert exc.code == "PAYLOAD_TOO_LARGE"
    
    def test_tool_not_found_error(self):
        """Test ToolNotFoundError attributes."""
        exc = ToolNotFoundError(tool_name="missing_tool")
        
        assert exc.tool_name == "missing_tool"
        assert "not found" in exc.message
        assert exc.code == "TOOL_NOT_FOUND"


class TestProxyClient:
    """Tests for the HTTP proxy client."""
    
    @pytest.fixture
    def mcp_request(self) -> MCPRequest:
        """Create a sample MCP request."""
        return MCPRequest(
            method="tools/call",
            params=MCPToolCallParams(name="test_tool", arguments={}),
            id="test-123"
        )
    
    @pytest.mark.asyncio
    async def test_forward_timeout_raises_error(self, mcp_request):
        """Test that timeout raises BackendTimeoutError."""
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.TimeoutException("timeout")
        
        with pytest.raises(BackendTimeoutError) as exc_info:
            await forward_to_backend(
                client=mock_client,
                backend_url="http://backend:8000",
                mcp_request=mcp_request,
                timeout=5.0
            )
        
        assert exc_info.value.timeout_seconds == 5.0
    
    @pytest.mark.asyncio
    async def test_forward_connection_error_raises(self, mcp_request):
        """Test that connection errors raise BackendUnavailableError."""
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("refused")
        
        with pytest.raises(BackendUnavailableError):
            await forward_to_backend(
                client=mock_client,
                backend_url="http://backend:8000",
                mcp_request=mcp_request
            )
    
    @pytest.mark.asyncio
    async def test_forward_success(self, mcp_request):
        """Test successful forwarding returns MCPResponse."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "result": {"data": "success"},
            "id": "test-123"
        }
        mock_client.post.return_value = mock_response
        
        response = await forward_to_backend(
            client=mock_client,
            backend_url="http://backend:8000",
            mcp_request=mcp_request
        )
        
        assert response.result == {"data": "success"}
        assert response.id == "test-123"

        settings = get_settings()
        _, kwargs = mock_client.post.call_args
        assert kwargs["headers"]["X-Gateway-Auth"] == settings.TOOL_GATEWAY_SHARED_SECRET

    @pytest.mark.asyncio
    async def test_forward_missing_gateway_secret_raises(self, mcp_request, monkeypatch):
        """Test missing shared secret fails closed."""
        monkeypatch.setenv("TOOL_GATEWAY_SHARED_SECRET", "")
        get_settings.cache_clear()
        try:
            mock_client = AsyncMock()
            with pytest.raises(BackendError):
                await forward_to_backend(
                    client=mock_client,
                    backend_url="http://backend:8000",
                    mcp_request=mcp_request
                )
        finally:
            get_settings.cache_clear()


class TestInvokeToolService:
    """Tests for the invoke_tool service function."""
    
    @pytest.fixture
    def admin_user(self) -> AuthenticatedUser:
        """Create an admin user."""
        claims = UserClaims(user_id="admin1", roles=["admin"])
        return AuthenticatedUser(claims=claims, allowed_tools={"*"})
    
    @pytest.fixture
    def viewer_user(self) -> AuthenticatedUser:
        """Create a viewer user with limited tools."""
        claims = UserClaims(user_id="viewer1", roles=["viewer"])
        return AuthenticatedUser(claims=claims, allowed_tools={"read_file"})
    
    @pytest.fixture
    def mock_tool(self) -> Tool:
        """Create a mock tool."""
        return Tool(
            id=1,
            name="read_file",
            description="Read file",
            backend_url="http://backend:8000",
            risk_level=RiskLevel.low,
            is_active=True,
            required_roles=None
        )
    
    @pytest.mark.asyncio
    async def test_user_permission_denied(self, viewer_user):
        """Test that unauthorized tool access is denied."""
        from src.auth.exceptions import ToolNotAllowedError
        
        request = InvokeToolRequest(tool_name="write_file", arguments={})
        db = AsyncMock()
        db.add = MagicMock()
        mock_client = AsyncMock()
        
        with pytest.raises(ToolNotAllowedError):
            await invoke_tool(db=db, user=viewer_user, request=request, client=mock_client)
    
    @pytest.mark.asyncio
    async def test_tool_not_in_registry(self, admin_user):
        """Test that missing tool raises ToolNotFoundError."""
        request = InvokeToolRequest(tool_name="nonexistent_tool", arguments={})
        db = AsyncMock()
        db.add = MagicMock()
        mock_client = AsyncMock()
        
        with patch("src.gateway.service.get_all_tools_cached", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = []  # No tools in registry
            
            with pytest.raises(ToolNotFoundError):
                await invoke_tool(db=db, user=admin_user, request=request, client=mock_client)
    
    @pytest.mark.asyncio
    async def test_payload_too_large_rejected(self, admin_user, mock_tool):
        """Test that oversized payloads are rejected."""
        large_args = {"data": "x" * 2000000}  # 2MB
        request = InvokeToolRequest(tool_name="read_file", arguments=large_args)
        db = AsyncMock()
        db.add = MagicMock()
        mock_client = AsyncMock()
        
        with pytest.raises(PayloadTooLargeError):
            await invoke_tool(
                db=db, 
                user=admin_user, 
                request=request,
                client=mock_client,
                max_payload_bytes=1000000  # 1MB limit
            )


class TestInvokeAuditLogging:
    """Tests that exceptions trigger audit logging."""
    
    @pytest.fixture
    def mock_deps(self):
        db = AsyncMock()
        user = AuthenticatedUser(
            claims=UserClaims(user_id="u1", roles=[]),
            allowed_tools={"*"}
        )
        request = InvokeToolRequest(tool_name="tool", arguments={})
        client = AsyncMock()
        return db, user, request, client

    @pytest.mark.asyncio
    async def test_audit_logs_timeout(self, mock_deps):
        """Test BackendTimeoutError is logged."""
        db, user, request, client = mock_deps
        
        with patch("src.gateway.service.audit_tool_invocation") as mock_audit_ctx, \
             patch("src.gateway.service.validate_payload_size"), \
             patch("src.gateway.service.get_all_tools_cached") as mock_get_tools:
            
            # Setup audit context mock
            ctx_instance = AsyncMock()
            mock_audit_ctx.return_value.__aenter__.return_value = ctx_instance
            
            # Simulate generic error to trigger logging? 
            # No, we need to mock something that raises BackendTimeoutError
            # Let's mock validation to raise it (unrealistic but works for flow)
            # OR better: mock forward_tool_call
            
            tool = MagicMock()
            tool.name = "tool"
            tool.backend_url = "http://bad"
            tool.required_roles = None
            mock_get_tools.return_value = [tool]
            
            with patch("src.gateway.service.forward_tool_call", side_effect=BackendTimeoutError("url", 1.0)):
                with pytest.raises(BackendTimeoutError):
                    await invoke_tool(db, user, request, client)
                
                ctx_instance.mark_timeout.assert_called_once()

    @pytest.mark.asyncio
    async def test_audit_logs_tool_not_found(self, mock_deps):
        """Test ToolNotFoundError is logged."""
        db, user, request, client = mock_deps
        
        with patch("src.gateway.service.audit_tool_invocation") as mock_audit_ctx, \
             patch("src.gateway.service.get_all_tools_cached") as mock_get_tools:
            
            ctx_instance = AsyncMock()
            mock_audit_ctx.return_value.__aenter__.return_value = ctx_instance
            
            mock_get_tools.return_value = []
            
            with pytest.raises(ToolNotFoundError):
                await invoke_tool(db, user, request, client)
                
            ctx_instance.mark_error.assert_called_with("TOOL_NOT_FOUND")

