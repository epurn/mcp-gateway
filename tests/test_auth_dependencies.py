"""Tests for auth dependencies."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import HTTPException

from src.auth.dependencies import get_token_from_header, get_current_user_claims, get_current_user
from src.auth.exceptions import InvalidTokenError
from src.auth.models import UserClaims

@pytest.mark.asyncio
async def test_get_token_valid():
    """Test valid Bearer token extraction."""
    token = await get_token_from_header("Bearer abc.123.xyz")
    assert token == "abc.123.xyz"

@pytest.mark.asyncio
async def test_get_token_missing_header():
    """Test missing header raises error."""
    with pytest.raises(InvalidTokenError):
        await get_token_from_header(None)

@pytest.mark.asyncio
async def test_get_token_invalid_format():
    """Test invalid header format raises error."""
    with pytest.raises(InvalidTokenError):
        await get_token_from_header("Basic 123")

    with pytest.raises(InvalidTokenError):
        await get_token_from_header("Bearer")


@pytest.mark.asyncio
async def test_get_current_user_claims_valid():
    """Test getting user claims from token."""
    with patch("src.auth.dependencies.extract_user_claims") as mock_extract:
        expected = UserClaims(user_id="u1", roles=[])
        mock_extract.return_value = expected
        
        result = await get_current_user_claims("token")
        assert result == expected
        mock_extract.assert_called_once_with("token")

@pytest.mark.asyncio
async def test_get_current_user():
    """Test getting full authenticated user."""
    claims = UserClaims(user_id="u1", roles=["admin"])
    
    with patch("src.auth.dependencies.get_allowed_tools_for_user") as mock_policy:
        mock_policy.return_value = {"*"}
        
        user = await get_current_user(claims)
        
        assert user.user_id == "u1"
        assert user.allowed_tools == {"*"}
        mock_policy.assert_called_once_with(claims)
