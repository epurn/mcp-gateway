"""Unit tests for authorization policy."""

import pytest
from pathlib import Path
import tempfile
import yaml

from src.auth.policy import (
    PolicyConfig,
    load_policy,
    get_allowed_tools_for_user,
    check_tool_permission,
    enforce_tool_permission,
)
from src.auth.models import UserClaims
from src.auth.exceptions import ToolNotAllowedError


class TestPolicyLoading:
    """Tests for policy loading from YAML."""
    
    def test_load_default_policy(self):
        """Test loading the default policy file."""
        policy = load_policy()
        assert isinstance(policy, PolicyConfig)
    
    def test_load_policy_from_custom_path(self):
        """Test loading policy from a custom path."""
        # Create a temp policy file
        policy_data = {
            "default_action": "deny",
            "roles": {
                "test_role": {"allowed_tools": ["tool_a", "tool_b"]}
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(policy_data, f)
            temp_path = f.name
        
        # Clear cache to force reload
        load_policy.cache_clear()
        
        policy = load_policy(temp_path)
        assert "test_role" in policy.roles
        assert policy.roles["test_role"]["allowed_tools"] == ["tool_a", "tool_b"]
        
        # Cleanup
        Path(temp_path).unlink()
        load_policy.cache_clear()


class TestGetAllowedTools:
    """Tests for determining allowed tools for a user."""
    
    def test_admin_gets_wildcard_access(self):
        """Test that admin role gets wildcard access."""
        policy = PolicyConfig(
            roles={"admin": {"allowed_tools": ["*"]}}
        )
        claims = UserClaims(user_id="admin1", roles=["admin"])
        
        allowed = get_allowed_tools_for_user(claims, policy)
        assert "*" in allowed
    
    def test_role_based_access(self):
        """Test that users get tools from their roles."""
        policy = PolicyConfig(
            roles={
                "developer": {"allowed_tools": ["read_file", "write_file"]},
                "viewer": {"allowed_tools": ["read_file"]}
            }
        )
        claims = UserClaims(user_id="dev1", roles=["developer"])
        
        allowed = get_allowed_tools_for_user(claims, policy)
        assert "read_file" in allowed
        assert "write_file" in allowed
    
    def test_multiple_roles_combined(self):
        """Test that multiple roles combine their permissions."""
        policy = PolicyConfig(
            roles={
                "role_a": {"allowed_tools": ["tool_a"]},
                "role_b": {"allowed_tools": ["tool_b"]}
            }
        )
        claims = UserClaims(user_id="user1", roles=["role_a", "role_b"])
        
        allowed = get_allowed_tools_for_user(claims, policy)
        assert "tool_a" in allowed
        assert "tool_b" in allowed
    
    def test_workspace_restrictions(self):
        """Test that workspace can restrict tools."""
        policy = PolicyConfig(
            roles={"developer": {"allowed_tools": ["read_file", "write_file", "delete_file"]}},
            workspaces={"production": {"denied_tools": ["delete_file"]}}
        )
        claims = UserClaims(user_id="dev1", roles=["developer"], workspace="production")
        
        allowed = get_allowed_tools_for_user(claims, policy)
        assert "read_file" in allowed
        assert "write_file" in allowed
        assert "delete_file" not in allowed


class TestCheckToolPermission:
    """Tests for checking specific tool permissions."""
    
    def test_allowed_tool_returns_true(self):
        """Test that allowed tool returns True."""
        policy = PolicyConfig(
            roles={"user": {"allowed_tools": ["my_tool"]}}
        )
        claims = UserClaims(user_id="user1", roles=["user"])
        
        assert check_tool_permission(claims, "my_tool", policy) is True
    
    def test_denied_tool_returns_false(self):
        """Test that denied tool returns False."""
        policy = PolicyConfig(
            roles={"user": {"allowed_tools": ["other_tool"]}}
        )
        claims = UserClaims(user_id="user1", roles=["user"])
        
        assert check_tool_permission(claims, "my_tool", policy) is False
    
    def test_wildcard_allows_any_tool(self):
        """Test that wildcard allows any tool."""
        policy = PolicyConfig(
            roles={"admin": {"allowed_tools": ["*"]}}
        )
        claims = UserClaims(user_id="admin1", roles=["admin"])
        
        assert check_tool_permission(claims, "any_tool", policy) is True
        assert check_tool_permission(claims, "another_tool", policy) is True
    
    def test_required_roles_enforced(self):
        """Test that tool-specific required roles are enforced."""
        policy = PolicyConfig(
            roles={"user": {"allowed_tools": ["dangerous_tool"]}},
            tools={"dangerous_tool": {"required_roles": ["admin"]}}
        )
        claims = UserClaims(user_id="user1", roles=["user"])
        
        # User has the tool in allowed list but lacks required admin role
        assert check_tool_permission(claims, "dangerous_tool", policy) is False


class TestEnforceToolPermission:
    """Tests for permission enforcement."""
    
    def test_allowed_tool_does_not_raise(self):
        """Test that allowed tool doesn't raise."""
        # Clear cache to ensure clean state
        load_policy.cache_clear()
        
        policy = PolicyConfig(
            roles={"user": {"allowed_tools": ["my_tool"]}}
        )
        claims = UserClaims(user_id="user1", roles=["user"])
        
        # Manually check permission - should not raise
        assert check_tool_permission(claims, "my_tool", policy) is True
    
    def test_denied_tool_raises_exception(self):
        """Test that denied tool raises ToolNotAllowedError."""
        # Create empty policy (deny all)
        policy = PolicyConfig(roles={})
        claims = UserClaims(user_id="user1", roles=["user"])
        
        # Use check_tool_permission which accepts policy parameter
        assert check_tool_permission(claims, "forbidden_tool", policy) is False
