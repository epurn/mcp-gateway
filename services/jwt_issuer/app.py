"""Dummy JWT issuer for end-to-end gateway testing."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from jose import jwt
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr


def _csv_values(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings(BaseModel):
    """Runtime settings loaded from environment."""

    model_config = ConfigDict(extra="forbid")

    jwt_secret_key: str = Field(default_factory=lambda: os.getenv("JWT_SECRET_KEY", ""))
    jwt_algorithm: str = Field(default_factory=lambda: os.getenv("JWT_ALGORITHM", "HS256"))
    jwt_issuer: str = Field(default_factory=lambda: os.getenv("JWT_ISSUER", ""))
    jwt_audience: str = Field(default_factory=lambda: os.getenv("JWT_AUDIENCE", ""))
    user_claim: str = Field(default_factory=lambda: os.getenv("JWT_USER_ID_CLAIM", "sub"))
    exp_claim: str = Field(default_factory=lambda: os.getenv("JWT_EXP_CLAIM", "exp"))
    iat_claim: str = Field(default_factory=lambda: os.getenv("JWT_IAT_CLAIM", "iat"))
    tenant_claim: str = Field(default_factory=lambda: os.getenv("JWT_TENANT_CLAIM", "workspace"))
    api_version_claim: str = Field(default_factory=lambda: os.getenv("JWT_API_VERSION_CLAIM", "v"))
    allowed_api_versions_raw: str = Field(
        default_factory=lambda: os.getenv("JWT_ALLOWED_API_VERSIONS", "")
    )
    issuer_admin_token: str = Field(default_factory=lambda: os.getenv("JWT_ISSUER_ADMIN_TOKEN", ""))

    @property
    def allowed_api_versions(self) -> list[str]:
        return _csv_values(self.allowed_api_versions_raw)


class TokenRequest(BaseModel):
    """Token issuance payload."""

    model_config = ConfigDict(extra="forbid")

    user_id: StrictStr
    roles: list[StrictStr] = Field(default_factory=list)
    workspace: StrictStr | None = None
    api_version: StrictStr | None = None
    expires_in_seconds: StrictInt = Field(default=3600, ge=60, le=86400)
    extra_claims: dict[str, Any] = Field(default_factory=dict)


class TokenResponse(BaseModel):
    """Token issuance response."""

    access_token: str
    token_type: str = "Bearer"
    expires_at_epoch: int
    claims: dict[str, Any]


app = FastAPI(title="Dummy JWT Issuer", version="1.0")
settings = Settings()


def _require_admin_token(issuer_token: str | None) -> None:
    if not settings.issuer_admin_token:
        return
    if issuer_token != settings.issuer_admin_token:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _resolve_api_version(requested: str | None) -> str | None:
    if requested:
        return requested
    if settings.allowed_api_versions:
        return settings.allowed_api_versions[0]
    return None


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/token", response_model=TokenResponse)
async def issue_token(
    request: TokenRequest,
    x_issuer_token: str | None = Header(default=None),
) -> TokenResponse:
    _require_admin_token(x_issuer_token)

    if not settings.jwt_secret_key:
        raise HTTPException(status_code=500, detail="JWT_SECRET_KEY is not configured")
    if not settings.jwt_issuer or not settings.jwt_audience:
        raise HTTPException(status_code=500, detail="JWT_ISSUER/JWT_AUDIENCE must be configured")

    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=request.expires_in_seconds)
    api_version = _resolve_api_version(request.api_version)

    claims: dict[str, Any] = {
        settings.user_claim: request.user_id,
        settings.exp_claim: int(exp.timestamp()),
        settings.iat_claim: int(now.timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "roles": request.roles,
    }

    if request.workspace is not None:
        claims[settings.tenant_claim] = request.workspace
    if api_version is not None:
        claims[settings.api_version_claim] = api_version
    claims.update(request.extra_claims)

    token = jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return TokenResponse(
        access_token=token,
        expires_at_epoch=int(exp.timestamp()),
        claims=claims,
    )
