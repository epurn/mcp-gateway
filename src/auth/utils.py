"""JWT utilities for token validation and decoding."""

from jose import JWTError, jwt
from datetime import datetime, timezone

from ..config import get_settings
from .exceptions import InvalidTokenError, ExpiredTokenError
from .models import UserClaims


def decode_jwt(token: str) -> dict:
    """Decode and validate a JWT token.
    
    Args:
        token: JWT token string (without 'Bearer ' prefix).
        
    Returns:
        Decoded JWT payload as a dictionary.
        
    Raises:
        InvalidTokenError: If token is malformed or signature is invalid.
        ExpiredTokenError: If token has expired.
    """
    settings = get_settings()
    
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={
                # Explicitly reject alg=none to prevent CVE-2025-61152
                "verify_signature": True,
                "verify_exp": True,
                "verify_aud": False,  # We don't use audience claim in MVP
            }
        )
        return payload
    except jwt.ExpiredSignatureError as e:
        raise ExpiredTokenError("JWT token has expired") from e
    except JWTError as e:
        raise InvalidTokenError(f"Invalid JWT token: {str(e)}") from e


def extract_user_claims(token: str) -> UserClaims:
    """Extract user claims from a JWT token.
    
    Args:
        token: JWT token string.
        
    Returns:
        UserClaims object with extracted information.
        
    Raises:
        InvalidTokenError: If token is invalid or missing required claims.
        ExpiredTokenError: If token has expired.
    """
    payload = decode_jwt(token)
    
    # Extract standard and custom claims
    try:
        claims = UserClaims(
            user_id=payload.get("sub") or payload.get("user_id"),
            email=payload.get("email"),
            roles=payload.get("roles", []),
            groups=payload.get("groups", []),
            workspace=payload.get("workspace") or payload.get("tenant"),
        )
    except Exception as e:
        raise InvalidTokenError(f"Failed to parse JWT claims: {str(e)}") from e
    
    if not claims.user_id:
        raise InvalidTokenError("JWT token missing required 'sub' or 'user_id' claim")
    
    return claims


def create_test_jwt(
    user_id: str,
    roles: list[str] | None = None,
    groups: list[str] | None = None,
    workspace: str | None = None,
    expire_minutes: int = 30
) -> str:
    """Create a test JWT token (for development/testing only).
    
    Args:
        user_id: User identifier.
        roles: User roles.
        groups: User groups.
        workspace: Workspace/tenant ID.
        expire_minutes: Token expiration time in minutes.
        
    Returns:
        Encoded JWT token string.
    """
    settings = get_settings()
    
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": f"{user_id}@example.com",
        "roles": roles or [],
        "groups": groups or [],
        "workspace": workspace,
        "iat": int(now.timestamp()),
        "exp": int((now.timestamp()) + (expire_minutes * 60)),
    }
    
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
