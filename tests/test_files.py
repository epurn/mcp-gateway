"""Tests for secure file downloads."""

from pathlib import Path
import uuid

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

from src.auth.models import AuthenticatedUser, UserClaims
from src.files import router as files_router


def _make_files_root() -> Path:
    base = Path(".pytest_files_tmp").resolve()
    run_dir = base / uuid.uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


@pytest.mark.asyncio
async def test_download_rejects_invalid_user_id(monkeypatch):
    base_dir = _make_files_root()
    monkeypatch.setattr(files_router, "FILES_DIR", base_dir)
    user = AuthenticatedUser(
        claims=UserClaims(user_id="..", roles=[]),
        allowed_tools=set(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await files_router.download_file("..", "report.txt", user=user)

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_download_returns_file_for_valid_user(monkeypatch):
    base_dir = _make_files_root()
    monkeypatch.setattr(files_router, "FILES_DIR", base_dir)
    user = AuthenticatedUser(
        claims=UserClaims(user_id="user1", roles=[]),
        allowed_tools=set(),
    )

    user_dir = base_dir / "user1"
    user_dir.mkdir()
    (user_dir / "report.txt").write_text("ok", encoding="utf-8")

    response = await files_router.download_file("user1", "report.txt", user=user)
    assert isinstance(response, FileResponse)
