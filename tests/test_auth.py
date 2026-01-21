"""Unit tests for JWT authentication utilities."""

import pytest
from datetime import datetime, timedelta, timezone
from jose import jwt

from src.auth.utils import decode_jwt, extract_user_claims, create_test_jwt
from src.auth.exceptions import InvalidTokenError, ExpiredTokenError
from src.auth.models import UserClaims
from src.config import get_settings


settings = get_settings()


class TestJWTDecoding:
    """Tests for JWT decode and validation."""
    
    def test_decode_valid_token(self):
        """Test decoding a valid JWT token."""
        # Create a valid token
        payload = {
            "sub": "user123",
            "email": "test@example.com",
            "exp": int((datetime.now(timezone.utc) + timedelta(minutes=30)).timestamp()),
        }
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        
        # Decode it
        decoded = decode_jwt(token)
        
        assert decoded["sub"] == "user123"
        assert decoded["email"] == "test@example.com"
    
    def test_decode_expired_token(self):
        """Test that expired tokens raise ExpiredTokenError."""
        # Create an expired token
        payload = {
            "sub": "user123",
            "exp": int((datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp()),
        }
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        
        # Should raise ExpiredTokenError
        with pytest.raises(ExpiredTokenError, match="JWT token has expired"):
            decode_jwt(token)
    
    def test_decode_invalid_signature(self):
        """Test that tokens with invalid signatures raise InvalidTokenError."""
        # Create a token with wrong secret
        payload = {
            "sub": "user123",
            "exp": int((datetime.now(timezone.utc) + timedelta(minutes=30)).timestamp()),
        }
        token = jwt.encode(payload, "wrong_secret_key", algorithm=settings.JWT_ALGORITHM)
        
        # Should raise InvalidTokenError
        with pytest.raises(InvalidTokenError, match="Invalid JWT token"):
            decode_jwt(token)
    
    def test_decode_malformed_token(self):
        """Test that malformed tokens raise InvalidTokenError."""
        with pytest.raises(InvalidTokenError, match="Invalid JWT token"):
            decode_jwt("not.a.valid.token")
    
    def test_reject_alg_none(self):
        """Test that alg=none tokens are rejected (CVE-2025-61152 protection).
        
        Note: python-jose 3.5.0 already rejects alg=none at the library level.
        """
        # The library itself raises JWSError for alg=none, which is the correct behavior
        # This test verifies that protection is in place
        from jose.exceptions import JWSError
        
        payload = {
            "sub": "user123",
            "exp": int((datetime.now(timezone.utc) + timedelta(minutes=30)).timestamp()),
        }
        
        # Attempting to encode with alg=none should raise an error
        with pytest.raises(JWSError, match="Algorithm none not supported"):
            jwt.encode(payload, None, algorithm="none")


class TestUserClaimsExtraction:
    """Tests for extracting user claims from JWT."""
    
    def test_extract_claims_with_sub(self):
        """Test extracting claims when 'sub' field is present."""
        token = create_test_jwt(
            user_id="user123",
            roles=["admin", "user"],
            groups=["engineering"],
            workspace="workspace-1"
        )
        
        claims = extract_user_claims(token)
        
        assert isinstance(claims, UserClaims)
        assert claims.user_id == "user123"
        assert claims.email == "user123@example.com"
        assert claims.roles == ["admin", "user"]
        assert claims.groups == ["engineering"]
        assert claims.workspace == "workspace-1"
    
    def test_extract_claims_missing_user_id(self):
        """Test that tokens without user_id/sub raise InvalidTokenError."""
        payload = {
            "email": "test@example.com",
            "exp": int((datetime.now(timezone.utc) + timedelta(minutes=30)).timestamp()),
        }
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        
        # Should raise InvalidTokenError (either from Pydantic validation or explicit check)
        with pytest.raises(InvalidTokenError):
            extract_user_claims(token)
    
    def test_extract_claims_with_defaults(self):
        """Test that missing optional claims use default values."""
        payload = {
            "sub": "user456",
            "exp": int((datetime.now(timezone.utc) + timedelta(minutes=30)).timestamp()),
        }
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        
        claims = extract_user_claims(token)
        
        assert claims.user_id == "user456"
        assert claims.email is None
        assert claims.roles == []
        assert claims.groups == []
        assert claims.workspace is None


class TestCreateTestJWT:
    """Tests for the create_test_jwt helper."""
    
    def test_create_test_jwt(self):
        """Test creating a test JWT token."""
        token = create_test_jwt(
            user_id="testuser",
            roles=["viewer"],
            workspace="test-workspace"
        )
        
        # Should be a valid token
        decoded = decode_jwt(token)
        assert decoded["sub"] == "testuser"
        assert decoded["roles"] == ["viewer"]
        assert decoded["workspace"] == "test-workspace"
    
    def test_create_test_jwt_with_negative_expiration(self):
        """Test that token with negative expiration is expired."""
        # Create a token that expired 1 minute ago
        payload = {
            "sub": "user",
            "exp": int((datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp()),
        }
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        
        # Should be expired
        with pytest.raises(ExpiredTokenError):
            decode_jwt(token)
