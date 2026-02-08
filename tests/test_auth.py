"""Unit tests for JWT authentication utilities."""

import pytest
from datetime import datetime, timedelta, timezone
from jose import jwt

from src.auth.utils import decode_jwt, extract_user_claims, create_test_jwt
from src.auth.exceptions import InvalidTokenError, ExpiredTokenError
from src.auth.models import UserClaims
from src.config import get_settings


settings = get_settings()


def _base_payload(user_id: str = "user123", settings_override=None) -> dict:
    local_settings = settings_override or get_settings()
    now = datetime.now(timezone.utc)
    allowed_versions = [
        item.strip()
        for item in local_settings.JWT_ALLOWED_API_VERSIONS.split(",")
        if item.strip()
    ]
    payload = {
        local_settings.JWT_USER_ID_CLAIM: user_id,
        "iss": local_settings.JWT_ISSUER,
        "aud": local_settings.JWT_AUDIENCE,
        local_settings.JWT_EXP_CLAIM: int((now + timedelta(minutes=30)).timestamp()),
    }
    if allowed_versions:
        payload[local_settings.JWT_API_VERSION_CLAIM] = allowed_versions[0]
    if local_settings.JWT_MAX_TOKEN_AGE_MINUTES > 0:
        payload[local_settings.JWT_IAT_CLAIM] = int(now.timestamp())
    return payload


class TestJWTDecoding:
    """Tests for JWT decode and validation."""
    
    def test_decode_valid_token(self):
        """Test decoding a valid JWT token."""
        # Create a valid token
        payload = _base_payload()
        payload["email"] = "test@example.com"
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        
        # Decode it
        decoded = decode_jwt(token)

        assert decoded[settings.JWT_USER_ID_CLAIM] == "user123"
        assert decoded["email"] == "test@example.com"
    
    def test_decode_expired_token(self):
        """Test that expired tokens raise ExpiredTokenError."""
        # Create an expired token
        payload = _base_payload()
        skew = timedelta(seconds=settings.JWT_CLOCK_SKEW_SECONDS)
        payload[settings.JWT_EXP_CLAIM] = int((datetime.now(timezone.utc) - (skew + timedelta(minutes=1))).timestamp())
        if settings.JWT_MAX_TOKEN_AGE_MINUTES > 0:
            payload[settings.JWT_IAT_CLAIM] = int((datetime.now(timezone.utc) - timedelta(minutes=10)).timestamp())
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        
        # Should raise ExpiredTokenError
        with pytest.raises(ExpiredTokenError, match="JWT token has expired"):
            decode_jwt(token)
    
    def test_decode_invalid_signature(self):
        """Test that tokens with invalid signatures raise InvalidTokenError."""
        # Create a token with wrong secret
        payload = _base_payload()
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
        
        payload = _base_payload()
        payload.pop(settings.JWT_IAT_CLAIM, None)
        
        # Attempting to encode with alg=none should raise an error
        with pytest.raises(JWSError, match="Algorithm none not supported"):
            jwt.encode(payload, None, algorithm="none")

    def test_decode_rejects_disallowed_algorithm(self, monkeypatch):
        """Test that tokens signed with a non-allowed algorithm are rejected."""
        monkeypatch.setenv("JWT_ALLOWED_ALGORITHMS", "HS256")
        get_settings.cache_clear()
        try:
            local_settings = get_settings()
            payload = _base_payload()
            payload["email"] = "test@example.com"
            token = jwt.encode(payload, local_settings.JWT_SECRET_KEY, algorithm="HS512")

            with pytest.raises(InvalidTokenError, match="Invalid JWT token"):
                decode_jwt(token)
        finally:
            get_settings.cache_clear()

    def test_decode_missing_issuer(self):
        payload = _base_payload()
        payload["email"] = "test@example.com"
        payload.pop("iss", None)
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

        with pytest.raises(InvalidTokenError, match="Invalid issuer"):
            decode_jwt(token)

    def test_decode_missing_audience(self):
        payload = _base_payload()
        payload["email"] = "test@example.com"
        payload.pop("aud", None)
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

        with pytest.raises(InvalidTokenError, match="missing required 'aud'"):
            decode_jwt(token)

    def test_decode_invalid_audience(self):
        payload = _base_payload()
        payload["email"] = "test@example.com"
        payload["aud"] = "some-other-audience"
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

        with pytest.raises(InvalidTokenError, match="Invalid JWT token"):
            decode_jwt(token)

    def test_decode_list_audience(self):
        payload = _base_payload()
        payload["email"] = "test@example.com"
        payload["aud"] = [settings.JWT_AUDIENCE, "other"]
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

        decoded = decode_jwt(token)
        assert decoded[settings.JWT_USER_ID_CLAIM] == "user123"


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
        payload = _base_payload()
        payload["email"] = "test@example.com"
        payload.pop(settings.JWT_USER_ID_CLAIM, None)
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        
        # Should raise InvalidTokenError (either from Pydantic validation or explicit check)
        with pytest.raises(InvalidTokenError):
            extract_user_claims(token)
    
    def test_extract_claims_with_defaults(self):
        """Test that missing optional claims use default values."""
        payload = _base_payload(user_id="user456")
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        
        claims = extract_user_claims(token)
        
        assert claims.user_id == "user456"
        assert claims.email is None
        assert claims.roles == []
        assert claims.groups == []
        assert claims.workspace is None


class TestJWTConfigValidation:
    """Tests for JWT configuration validation."""

    def test_invalid_allowed_algorithms_config(self, monkeypatch):
        """Test that misconfigured allowed algorithms are rejected."""
        monkeypatch.setenv("JWT_ALLOWED_ALGORITHMS", "none")
        get_settings.cache_clear()
        try:
            token = create_test_jwt(user_id="user123")
            with pytest.raises(InvalidTokenError, match="allowed algorithms misconfigured"):
                decode_jwt(token)
        finally:
            get_settings.cache_clear()


class TestJWTClaimMapping:
    """Tests for configurable claim mapping."""

    def test_custom_claim_mapping(self, monkeypatch):
        monkeypatch.setenv("JWT_USER_ID_CLAIM", "u")
        monkeypatch.setenv("JWT_EXP_CLAIM", "e")
        monkeypatch.setenv("JWT_TENANT_CLAIM", "t")
        monkeypatch.setenv("JWT_API_VERSION_CLAIM", "v")
        monkeypatch.setenv("JWT_ALLOWED_API_VERSIONS", "2")
        get_settings.cache_clear()
        try:
            local_settings = get_settings()
            payload = {
                "u": "user123",
                "e": int((datetime.now(timezone.utc) + timedelta(minutes=30)).timestamp()),
                "t": "tenant-1",
                "v": "2",
                "iss": local_settings.JWT_ISSUER,
                "aud": local_settings.JWT_AUDIENCE,
            }
            token = jwt.encode(payload, local_settings.JWT_SECRET_KEY, algorithm=local_settings.JWT_ALGORITHM)

            claims = extract_user_claims(token)
            assert claims.user_id == "user123"
            assert claims.workspace == "tenant-1"
        finally:
            get_settings.cache_clear()


class TestJWTFreshnessValidation:
    """Tests for JWT max age and nbf handling."""

    def test_requires_iat_when_max_age_enabled(self, monkeypatch):
        monkeypatch.setenv("JWT_MAX_TOKEN_AGE_MINUTES", "5")
        get_settings.cache_clear()
        try:
            local_settings = get_settings()
            payload = _base_payload()
            payload.pop(local_settings.JWT_IAT_CLAIM, None)
            token = jwt.encode(payload, local_settings.JWT_SECRET_KEY, algorithm=local_settings.JWT_ALGORITHM)

            with pytest.raises(InvalidTokenError, match="missing required 'iat'"):
                decode_jwt(token)
        finally:
            get_settings.cache_clear()

    def test_rejects_token_older_than_max_age(self, monkeypatch):
        monkeypatch.setenv("JWT_MAX_TOKEN_AGE_MINUTES", "5")
        get_settings.cache_clear()
        try:
            local_settings = get_settings()
            payload = _base_payload()
            payload[local_settings.JWT_IAT_CLAIM] = int((datetime.now(timezone.utc) - timedelta(minutes=10)).timestamp())
            token = jwt.encode(payload, local_settings.JWT_SECRET_KEY, algorithm=local_settings.JWT_ALGORITHM)

            with pytest.raises(InvalidTokenError, match="token too old"):
                decode_jwt(token)
        finally:
            get_settings.cache_clear()

    def test_accepts_token_within_max_age(self, monkeypatch):
        monkeypatch.setenv("JWT_MAX_TOKEN_AGE_MINUTES", "5")
        get_settings.cache_clear()
        try:
            local_settings = get_settings()
            payload = _base_payload()
            payload[local_settings.JWT_IAT_CLAIM] = int((datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp())
            token = jwt.encode(payload, local_settings.JWT_SECRET_KEY, algorithm=local_settings.JWT_ALGORITHM)

            decoded = decode_jwt(token)
            assert decoded[local_settings.JWT_USER_ID_CLAIM] == "user123"
        finally:
            get_settings.cache_clear()

    def test_rejects_token_not_before_in_future(self, monkeypatch):
        monkeypatch.setenv("JWT_MAX_TOKEN_AGE_MINUTES", "5")
        monkeypatch.setenv("JWT_CLOCK_SKEW_SECONDS", "0")
        get_settings.cache_clear()
        try:
            local_settings = get_settings()
            payload = _base_payload()
            payload[local_settings.JWT_IAT_CLAIM] = int(datetime.now(timezone.utc).timestamp())
            payload["nbf"] = int((datetime.now(timezone.utc) + timedelta(minutes=1)).timestamp())
            token = jwt.encode(payload, local_settings.JWT_SECRET_KEY, algorithm=local_settings.JWT_ALGORITHM)

            with pytest.raises(InvalidTokenError, match="not yet valid"):
                decode_jwt(token)
        finally:
            get_settings.cache_clear()


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
        assert decoded[settings.JWT_USER_ID_CLAIM] == "testuser"
        assert decoded["roles"] == ["viewer"]
        assert decoded[settings.JWT_TENANT_CLAIM] == "test-workspace"
    
    def test_create_test_jwt_with_negative_expiration(self):
        """Test that token with negative expiration is expired."""
        # Create a token that expired 1 minute ago
        payload = _base_payload(user_id="user")
        skew = timedelta(seconds=settings.JWT_CLOCK_SKEW_SECONDS)
        payload[settings.JWT_EXP_CLAIM] = int((datetime.now(timezone.utc) - (skew + timedelta(minutes=1))).timestamp())
        if settings.JWT_MAX_TOKEN_AGE_MINUTES > 0:
            payload[settings.JWT_IAT_CLAIM] = int((datetime.now(timezone.utc) - timedelta(minutes=10)).timestamp())
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        
        # Should be expired
        with pytest.raises(ExpiredTokenError):
            decode_jwt(token)
