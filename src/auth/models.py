"""Pydantic models for authentication and user identity."""

from pydantic import BaseModel, Field, ConfigDict


class UserClaims(BaseModel):
    """JWT claims extracted from the token.
    
    Attributes:
        user_id: Unique identifier for the user.
        email: User's email address (optional).
        roles: List of roles assigned to the user.
        groups: List of groups the user belongs to.
        workspace: Workspace/tenant identifier (optional).
    """
    
    user_id: str = Field(..., description="Unique user identifier")
    email: str | None = Field(None, description="User email address")
    roles: list[str] = Field(default_factory=list, description="User roles")
    groups: list[str] = Field(default_factory=list, description="User groups")
    workspace: str | None = Field(None, description="Workspace or tenant ID")
    
    # Allow extra fields from JWT without raising validation errors
    model_config = ConfigDict(extra="allow")


class AuthenticatedUser(BaseModel):
    """Represents an authenticated user with their permissions.
    
    Attributes:
        claims: JWT claims extracted from the token.
        allowed_tools: List of tool names this user can access.
    """
    
    claims: UserClaims
    allowed_tools: set[str] = Field(default_factory=set, description="Tools user can access")
    
    @property
    def user_id(self) -> str:
        """Convenience property to access user_id."""
        return self.claims.user_id
    
    @property
    def roles(self) -> list[str]:
        """Convenience property to access roles."""
        return self.claims.roles
    
    def can_use_tool(self, tool_name: str) -> bool:
        """Check if user has permission to use a specific tool.
        
        Args:
            tool_name: Name of the tool to check.
            
        Returns:
            True if user can use the tool, False otherwise.
        """
        return tool_name in self.allowed_tools
