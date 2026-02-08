"""JWT utilities for token validation and decoding."""

from jose import JWTError, jwt
from datetime import datetime, timezone

from ..config import get_settings
from .exceptions import InvalidTokenError, ExpiredTokenError
from .models import UserClaims


def _get_allowed_algorithms(settings) -> list[str]:
    raw = settings.JWT_ALLOWED_ALGORITHMS
    if isinstance(raw, str):
        items = [item.strip() for item in raw.split(",") if item.strip()]
    else:
        items = []

    normalized = [item.upper() for item in items]
    if not normalized or "NONE" in normalized:
        raise InvalidTokenError("JWT allowed algorithms misconfigured")

    if settings.JWT_ALGORITHM.upper() not in normalized:
        raise InvalidTokenError("JWT algorithm not in allowed list")

    return normalized


def _parse_csv_list(raw: str) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _get_claim(payload: dict, name: str) -> object | None:
    return payload.get(name) if name else None


def _get_required_claim(payload: dict, name: str) -> object:
    value = _get_claim(payload, name)
    if value is None:
        raise InvalidTokenError(f"JWT token missing required '{name}' claim")
    return value


def _coerce_int(value: object, name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise InvalidTokenError(f"JWT token has invalid '{name}' claim")


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

    if not settings.JWT_ISSUER or not settings.JWT_AUDIENCE:
        raise InvalidTokenError("JWT issuer/audience not configured")

    allowed_algorithms = _get_allowed_algorithms(settings)
    allowed_versions = _parse_csv_list(settings.JWT_ALLOWED_API_VERSIONS)

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=allowed_algorithms,
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
            options={
                # Explicitly reject alg=none to prevent CVE-2025-61152
                "verify_signature": True,
                "verify_exp": True,
                "verify_aud": True,
                "verify_iss": True,
            }
        )
        exp_claim = settings.JWT_EXP_CLAIM
        exp_value = _get_required_claim(payload, exp_claim)
        exp_ts = _coerce_int(exp_value, exp_claim)
        if "iss" not in payload:
            raise InvalidTokenError("JWT token missing required 'iss' claim")
        if "aud" not in payload:
            raise InvalidTokenError("JWT token missing required 'aud' claim")

        now_ts = int(datetime.now(timezone.utc).timestamp())
        skew = max(0, int(settings.JWT_CLOCK_SKEW_SECONDS))

        if now_ts - skew > exp_ts:
            raise ExpiredTokenError("JWT token has expired")

        not_before = payload.get("nbf")
        if not_before is not None and now_ts + skew < int(not_before):
            raise InvalidTokenError("JWT token not yet valid")

        max_age_minutes = int(settings.JWT_MAX_TOKEN_AGE_MINUTES)
        if max_age_minutes > 0:
            issued_at = payload.get(settings.JWT_IAT_CLAIM)
            if issued_at is None:
                raise InvalidTokenError(f"JWT token missing required '{settings.JWT_IAT_CLAIM}' claim")
            issued_at = _coerce_int(issued_at, settings.JWT_IAT_CLAIM)
            if issued_at > now_ts + skew:
                raise InvalidTokenError(f"JWT token has invalid '{settings.JWT_IAT_CLAIM}' claim")
            max_age_seconds = max_age_minutes * 60
            if now_ts - skew > issued_at + max_age_seconds:
                raise InvalidTokenError("JWT token too old")

        if allowed_versions:
            version = payload.get(settings.JWT_API_VERSION_CLAIM)
            if version is None:
                raise InvalidTokenError(
                    f"JWT token missing required '{settings.JWT_API_VERSION_CLAIM}' claim"
                )
            if str(version) not in allowed_versions:
                raise InvalidTokenError("JWT token has unsupported api version")

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
    
    settings = get_settings()

    # Extract standard and custom claims
    try:
        user_id_claim = settings.JWT_USER_ID_CLAIM
        user_id = payload.get(user_id_claim)
        if not user_id and user_id_claim == "sub":
            user_id = payload.get("user_id")

        tenant_claim = settings.JWT_TENANT_CLAIM
        workspace = payload.get(tenant_claim) if tenant_claim else None
        if workspace is None and tenant_claim in ("workspace", "tenant"):
            alt = "tenant" if tenant_claim == "workspace" else "workspace"
            workspace = payload.get(alt)

        claims = UserClaims(
            user_id=user_id,
            email=payload.get("email"),
            roles=payload.get("roles", []),
            groups=payload.get("groups", []),
            workspace=workspace,
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
    api_version: str | None = None,
    expire_minutes: int = 30
) -> str:
    """Create a test JWT token (for development/testing only).
    
    Args:
        user_id: User identifier.
        roles: User roles.
        groups: User groups.
        workspace: Workspace/tenant ID.
        api_version: Optional API version claim value.
        expire_minutes: Token expiration time in minutes.
        
    Returns:
        Encoded JWT token string.
    """
    settings = get_settings()
    allowed_versions = _parse_csv_list(settings.JWT_ALLOWED_API_VERSIONS)
    if api_version is None and allowed_versions:
        api_version = allowed_versions[0]
    
    now = datetime.now(timezone.utc)
    payload = {
        settings.JWT_USER_ID_CLAIM: user_id,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "email": f"{user_id}@example.com",
        "roles": roles or [],
        "groups": groups or [],
        settings.JWT_TENANT_CLAIM: workspace,
        settings.JWT_IAT_CLAIM: int(now.timestamp()),
        settings.JWT_EXP_CLAIM: int((now.timestamp()) + (expire_minutes * 60)),
    }
    if api_version is not None:
        payload[settings.JWT_API_VERSION_CLAIM] = api_version
    
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
