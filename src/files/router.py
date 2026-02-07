from pathlib import Path
import re
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from src.auth.dependencies import get_current_user
from src.config import get_settings

router = APIRouter(prefix="/files", tags=["files"])
settings = get_settings()

FILES_DIR = Path("/app/static/files")
USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{0,127}$")


def _validate_user_id(user_id: str) -> None:
    if not USER_ID_PATTERN.fullmatch(user_id):
        raise HTTPException(status_code=400, detail="Invalid user id")

@router.get("/{user_id}/{filename}")
async def download_file(user_id: str, filename: str, user=Depends(get_current_user)):
    """
    Download a generated file.
    Requires a valid JWT token and matching user ID.
    """
    # Strict ownership check
    if user.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied: You can only download your own files")

    _validate_user_id(user_id)

    # Prevent directory traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    base_dir = FILES_DIR.resolve()
    file_path = (base_dir / user_id / filename).resolve()

    if not file_path.is_relative_to(base_dir):
        raise HTTPException(status_code=400, detail="Invalid path")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream"
    )
