"""Authorization policy service for tool access control."""

from pathlib import Path
from functools import lru_cache
import yaml

from pydantic import BaseModel, Field

from .models import UserClaims
from .exceptions import ToolNotAllowedError


class PolicyConfig(BaseModel):
    """Configuration loaded from policy.yaml."""
    
    default_action: str = "deny"
    roles: dict[str, dict] = Field(default_factory=dict)
    workspaces: dict[str, dict] = Field(default_factory=dict)
    tools: dict[str, dict] = Field(default_factory=dict)


@lru_cache()
def load_policy(policy_path: str | None = None) -> PolicyConfig:
    """Load authorization policy from YAML file.
    
    Args:
        policy_path: Path to policy.yaml file. If None, uses default location.
        
    Returns:
        PolicyConfig object with parsed policy rules.
    """
    if policy_path is None:
        # Default to config/policy.yaml relative to project root
        policy_path = Path(__file__).parent.parent.parent / "config" / "policy.yaml"
    else:
        policy_path = Path(policy_path)
    
    if not policy_path.exists():
        # Return default deny-all policy if file doesn't exist
        return PolicyConfig()
    
    with open(policy_path, "r") as f:
        data = yaml.safe_load(f)
    
    return PolicyConfig(**data)


def get_allowed_tools_for_user(claims: UserClaims, policy: PolicyConfig | None = None) -> set[str]:
    """Determine which tools a user can access based on their claims.
    
    Args:
        claims: User claims from JWT token.
        policy: Policy config (loads default if not provided).
        
    Returns:
        Set of tool names the user is allowed to access.
    """
    if policy is None:
        policy = load_policy()
    
    allowed_tools: set[str] = set()
    denied_tools: set[str] = set()
    
    # 1. Collect allowed tools from all user roles
    for role in claims.roles:
        role_config = policy.roles.get(role, {})
        role_allowed = role_config.get("allowed_tools", [])
        
        if role_allowed == ["*"]:
            # Wildcard: allow all tools
            allowed_tools.add("*")
        else:
            allowed_tools.update(role_allowed)
    
    # 2. Apply workspace restrictions if applicable
    if claims.workspace:
        workspace_config = policy.workspaces.get(claims.workspace, {})
        
        # Add workspace-specific allowed tools
        ws_allowed = workspace_config.get("allowed_tools", [])
        if ws_allowed == ["*"]:
            allowed_tools.add("*")
        elif ws_allowed:
            # Workspace allowlist overrides role allowlist
            allowed_tools = set(ws_allowed)
        
        # Remove workspace-denied tools
        ws_denied = workspace_config.get("denied_tools", [])
        denied_tools.update(ws_denied)
    
    # 3. Remove denied tools (unless user has wildcard access and is admin)
    if "*" not in allowed_tools:
        allowed_tools -= denied_tools
    elif "admin" not in claims.roles:
        allowed_tools -= denied_tools
    
    return allowed_tools


def check_tool_permission(
    claims: UserClaims,
    tool_name: str,
    policy: PolicyConfig | None = None
) -> bool:
    """Check if a user has permission to use a specific tool.
    
    Args:
        claims: User claims from JWT.
        tool_name: Name of the tool to check.
        policy: Policy config (loads default if not provided).
        
    Returns:
        True if user can use the tool, False otherwise.
    """
    if policy is None:
        policy = load_policy()
    
    allowed_tools = get_allowed_tools_for_user(claims, policy)
    
    # Wildcard allows everything
    if "*" in allowed_tools:
        return True
    
    # Check tool-specific required roles
    tool_config = policy.tools.get(tool_name, {})
    required_roles = tool_config.get("required_roles", [])
    
    if required_roles:
        # Tool requires specific roles
        if not any(role in claims.roles for role in required_roles):
            return False
    
    return tool_name in allowed_tools


def enforce_tool_permission(claims: UserClaims, tool_name: str) -> None:
    """Enforce tool permission, raising exception if denied.
    
    Args:
        claims: User claims from JWT.
        tool_name: Name of the tool to check.
        
    Raises:
        ToolNotAllowedError: If user is not permitted to use the tool.
    """
    if not check_tool_permission(claims, tool_name):
        raise ToolNotAllowedError(tool_name=tool_name, user_id=claims.user_id)
