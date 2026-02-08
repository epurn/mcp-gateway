"""Unit tests for the tool registry module."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.registry.models import Tool, RiskLevel
from src.registry.schemas import ToolResponse, ToolListResponse
from src.registry.service import get_tools_for_user, clear_tool_cache, _tool_cache, sync_tools_from_config
from src.registry.config import ToolRegistryConfig, ToolConfig
from src.auth.models import AuthenticatedUser, UserClaims


class TestRiskLevel:
    """Tests for RiskLevel enum."""
    
    def test_risk_level_values(self):
        """Test that RiskLevel enum has expected values."""
        assert RiskLevel.low.value == "low"
        assert RiskLevel.medium.value == "medium"
        assert RiskLevel.high.value == "high"
    
    def test_risk_level_from_string(self):
        """Test creating RiskLevel from string."""
        assert RiskLevel("low") == RiskLevel.low
        assert RiskLevel("high") == RiskLevel.high


class TestToolModel:
    """Tests for Tool SQLAlchemy model."""
    
    def test_tool_repr(self):
        """Test Tool string representation."""
        tool = Tool(
            name="test_tool",
            description="A test tool",
            backend_url="http://localhost:8000",
            risk_level=RiskLevel.medium,
            is_active=True
        )
        
        assert "test_tool" in repr(tool)
        assert "medium" in repr(tool)


class TestToolSchemas:
    """Tests for Pydantic response schemas."""
    
    def test_tool_response_serialization(self):
        """Test ToolResponse serializes correctly."""
        response = ToolResponse(
            name="read_file",
            description="Read file contents",
            backend_url="http://backend:8000/read",
            risk_level="low"
        )
        
        data = response.model_dump()
        assert data["name"] == "read_file"
        assert data["risk_level"] == "low"
    
    def test_tool_list_response(self):
        """Test ToolListResponse with multiple tools."""
        tools = [
            ToolResponse(name="tool1", description="Tool 1", backend_url="http://a", risk_level="low"),
            ToolResponse(name="tool2", description="Tool 2", backend_url="http://b", risk_level="high"),
        ]
        
        response = ToolListResponse(tools=tools, count=2)
        
        assert len(response.tools) == 2
        assert response.count == 2


class TestToolFiltering:
    """Tests for tool filtering logic in service layer."""
    
    @pytest.fixture
    def mock_tools(self) -> list[Tool]:
        """Create mock tools for testing."""
        return [
            Tool(id=1, name="read_file", description="Read", backend_url="http://a", 
                 risk_level=RiskLevel.low, is_active=True, required_roles=None),
            Tool(id=2, name="write_file", description="Write", backend_url="http://b", 
                 risk_level=RiskLevel.medium, is_active=True, required_roles=None),
            Tool(id=3, name="admin_tool", description="Admin only", backend_url="http://c",
                 risk_level=RiskLevel.high, is_active=True, required_roles=["admin"]),
            Tool(id=4, name="search_code", description="Search", backend_url="http://d",
                 risk_level=RiskLevel.low, is_active=True, required_roles=None),
        ]
    
    @pytest.fixture
    def viewer_user(self) -> AuthenticatedUser:
        """Create a viewer user."""
        claims = UserClaims(user_id="viewer1", roles=["viewer"])
        return AuthenticatedUser(
            claims=claims, 
            allowed_tools={"read_file", "search_code", "list_directory"}
        )
    
    @pytest.fixture
    def admin_user(self) -> AuthenticatedUser:
        """Create an admin user."""
        claims = UserClaims(user_id="admin1", roles=["admin"])
        return AuthenticatedUser(claims=claims, allowed_tools={"*"})
    
    @pytest.fixture
    def developer_user(self) -> AuthenticatedUser:
        """Create a developer user."""
        claims = UserClaims(user_id="dev1", roles=["developer"])
        return AuthenticatedUser(
            claims=claims,
            allowed_tools={"read_file", "write_file", "search_code"}
        )
    
    @pytest.mark.asyncio
    async def test_viewer_gets_filtered_tools(self, mock_tools, viewer_user):
        """Test that viewers only get their allowed tools."""
        clear_tool_cache()
        
        with patch("src.registry.service.get_all_active_tools", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_tools
            
            db = AsyncMock()
            result = await get_tools_for_user(db, viewer_user)
            
            # Viewer should only see read_file and search_code (both are in allowed_tools and in mock_tools)
            tool_names = {t.name for t in result.tools}
            assert tool_names == {"read_file", "search_code"}
            assert result.count == 2
    
    @pytest.mark.asyncio
    async def test_admin_gets_all_tools(self, mock_tools, admin_user):
        """Test that admins with wildcard access get all tools."""
        clear_tool_cache()
        
        with patch("src.registry.service.get_all_active_tools", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_tools
            
            db = AsyncMock()
            result = await get_tools_for_user(db, admin_user)
            
            # Admin should see all tools including admin_tool (has admin role)
            tool_names = {t.name for t in result.tools}
            assert tool_names == {"read_file", "write_file", "admin_tool", "search_code"}
            assert result.count == 4
    
    @pytest.mark.asyncio
    async def test_developer_blocked_from_admin_tool(self, mock_tools, developer_user):
        """Test that developers cannot access admin_tool even if in allowed_tools."""
        # Modify developer to have admin_tool in allowed_tools but no admin role
        developer_user.allowed_tools.add("admin_tool")
        clear_tool_cache()
        
        with patch("src.registry.service.get_all_active_tools", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_tools
            
            db = AsyncMock()
            result = await get_tools_for_user(db, developer_user)
            
            # Developer should NOT see admin_tool (requires admin role)
            tool_names = {t.name for t in result.tools}
            assert "admin_tool" not in tool_names
            # But should see read_file, write_file, search_code
            assert "read_file" in tool_names
            assert "write_file" in tool_names


class TestToolCache:
    """Tests for caching behavior."""
    
    @pytest.mark.asyncio
    async def test_cache_is_used(self):
        """Test that cache prevents repeated DB calls."""
        clear_tool_cache()
        
        mock_tools = [
            Tool(id=1, name="cached_tool", description="Test", backend_url="http://x",
                 risk_level=RiskLevel.low, is_active=True, required_roles=None)
        ]
        
        claims = UserClaims(user_id="u1", roles=["viewer"])
        user = AuthenticatedUser(claims=claims, allowed_tools={"cached_tool"})
        
        with patch("src.registry.service.get_all_active_tools", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_tools
            
            db = AsyncMock()
            
            # First call should hit the DB
            result1 = await get_tools_for_user(db, user)
            
            # Second call should use cache
            result2 = await get_tools_for_user(db, user)
            
            # get_all_active_tools should only be called once
            assert mock_get.call_count == 1
            assert result1.count == result2.count
    
    def test_cache_clear(self):
        """Test that clear_tool_cache actually clears the cache."""
        # Put something in cache
        _tool_cache["test_key"] = "test_value"
        assert len(_tool_cache) > 0
        
        clear_tool_cache()
        
        assert len(_tool_cache) == 0


class TestToolSync:
    """Tests for syncing tool registry from config."""

    @pytest.mark.asyncio
    async def test_sync_prunes_and_clears_cache(self):
        _tool_cache["stale_key"] = "stale"

        config = ToolRegistryConfig(
            tools=[
                ToolConfig(
                    name="tool_a",
                    description="Tool A",
                    backend_url="http://a",
                    risk_level="low",
                )
            ]
        )

        with patch("src.registry.service.load_tool_registry", return_value=config):
            with patch("src.registry.service.get_tool_by_name", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = None
                with patch("src.registry.service.create_tool", new_callable=AsyncMock) as mock_create:
                    with patch("src.registry.service.deactivate_tools_not_in_list", new_callable=AsyncMock) as mock_prune:
                        db = AsyncMock()
                        await sync_tools_from_config(db)

                        mock_create.assert_awaited_once()
                        mock_prune.assert_awaited_once_with(db, {"tool_a"})
                        assert len(_tool_cache) == 0

    @pytest.mark.asyncio
    async def test_sync_empty_config_clears_cache_only(self):
        _tool_cache["stale_key"] = "stale"
        config = ToolRegistryConfig(tools=[])

        with patch("src.registry.service.load_tool_registry", return_value=config):
            with patch("src.registry.service.deactivate_tools_not_in_list", new_callable=AsyncMock) as mock_prune:
                db = AsyncMock()
                await sync_tools_from_config(db)

                mock_prune.assert_not_awaited()
                assert len(_tool_cache) == 0

    @pytest.mark.asyncio
    async def test_sync_create_passes_input_schema(self):
        config = ToolRegistryConfig(
            tools=[
                ToolConfig(
                    name="document_generate",
                    description="Deterministic document generation.",
                    backend_url="http://document-generator:8000/mcp",
                    risk_level="low",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "format": {"type": "string", "enum": ["docx", "pdf", "html"]},
                        },
                        "required": ["content", "format"],
                    },
                )
            ]
        )

        with patch("src.registry.service.load_tool_registry", return_value=config):
            with patch("src.registry.service.get_tool_by_name", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = None
                with patch("src.registry.service.create_tool", new_callable=AsyncMock) as mock_create:
                    with patch("src.registry.service.deactivate_tools_not_in_list", new_callable=AsyncMock):
                        db = AsyncMock()
                        await sync_tools_from_config(db)

                        _, kwargs = mock_create.await_args
                        assert kwargs["name"] == "document_generate"
                        assert kwargs["input_schema"]["properties"]["format"]["enum"] == ["docx", "pdf", "html"]

    @pytest.mark.asyncio
    async def test_sync_updates_existing_input_schema(self):
        existing = Tool(
            id=1,
            name="document_generate",
            description="Old",
            backend_url="http://document-generator:8000/mcp",
            risk_level=RiskLevel.low,
            required_roles=None,
            is_active=True,
            input_schema={"type": "object", "properties": {}},
        )
        config = ToolRegistryConfig(
            tools=[
                ToolConfig(
                    name="document_generate",
                    description="New",
                    backend_url="http://document-generator:8000/mcp",
                    risk_level="low",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "format": {"type": "string", "enum": ["docx", "pdf", "html"]},
                        },
                        "required": ["content", "format"],
                    },
                )
            ]
        )

        with patch("src.registry.service.load_tool_registry", return_value=config):
            with patch("src.registry.service.get_tool_by_name", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = existing
                with patch("src.registry.service.create_tool", new_callable=AsyncMock) as mock_create:
                    with patch("src.registry.service.deactivate_tools_not_in_list", new_callable=AsyncMock):
                        db = AsyncMock()
                        await sync_tools_from_config(db)

                        mock_create.assert_not_awaited()
                        assert existing.description == "New"
                        assert existing.input_schema["required"] == ["content", "format"]
                        db.commit.assert_awaited()
                        db.refresh.assert_awaited_with(existing)
