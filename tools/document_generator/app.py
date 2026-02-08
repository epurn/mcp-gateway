"""Document generation tool service using Pandoc."""

import base64
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Literal, Optional

import uuid
from fastapi import FastAPI, Request
from pydantic import BaseModel, Field, StrictStr, StrictInt, ConfigDict
from starlette.responses import JSONResponse

# Configuration
MAX_CONTENT_SIZE = int(os.getenv("MAX_CONTENT_SIZE", "524288"))  # 512KB
REQUEST_TIMEOUT_SEC = int(os.getenv("REQUEST_TIMEOUT_SEC", "30"))
USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{0,127}$")
GATEWAY_AUTH_HEADER = "X-Gateway-Auth"
GATEWAY_SHARED_SECRET = os.getenv("TOOL_GATEWAY_SHARED_SECRET", "")

# Emoji pattern for stripping (covers most emoji ranges)
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F700-\U0001F77F"  # alchemical
    "\U0001F780-\U0001F7FF"  # Geometric shapes
    "\U0001F800-\U0001F8FF"  # arrows
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FA6F"  # chess symbols
    "\U0001FA70-\U0001FAFF"  # symbols and pictographs
    "\U00002702-\U000027B0"  # dingbats
    "\U000024C2-\U0001F251"  # enclosed chars
    "]+",
    flags=re.UNICODE
)


def strip_emojis(text: str) -> str:
    """Remove emojis from text for LaTeX compatibility."""
    return EMOJI_PATTERN.sub("", text)


def validate_user_id(user_id: str) -> None:
    if not USER_ID_PATTERN.fullmatch(user_id):
        raise ValueError("Invalid user id")


app = FastAPI(title="Document Generator", version="1.0")


class StrictModel(BaseModel):
    """Base model that forbids unknown fields."""
    model_config = ConfigDict(extra="forbid")


class GenerateParams(StrictModel):
    """Parameters for document generation."""
    content: StrictStr = Field(..., description="Markdown content to convert")
    format: Literal["pdf", "docx", "html"] = Field(..., description="Output format")
    title: Optional[StrictStr] = Field(None, description="Document title")


class MCPToolCallParams(StrictModel):
    """Parameters for MCP tool invocation."""
    name: StrictStr
    arguments: dict = Field(default_factory=dict)


class MCPRequest(StrictModel):
    """JSON-RPC request envelope for MCP tool calls."""
    jsonrpc: Literal["2.0"] = Field(default="2.0")
    method: StrictStr
    params: MCPToolCallParams
    id: StrictStr | StrictInt


class MCPErrorDetail(StrictModel):
    """JSON-RPC error detail payload."""
    code: StrictInt
    message: StrictStr
    data: object | None = None


class MCPResponse(StrictModel):
    """JSON-RPC response envelope for MCP tool calls."""
    jsonrpc: Literal["2.0"] = Field(default="2.0")
    result: object | None = None
    error: MCPErrorDetail | None = None
    id: StrictStr | StrictInt

    @classmethod
    def success(cls, request_id: str | int, result: object) -> "MCPResponse":
        return cls(id=request_id, result=result)

    @classmethod
    def error_response(
        cls,
        request_id: str | int,
        code: int,
        message: str,
        data: object | None = None,
    ) -> "MCPResponse":
        return cls(id=request_id, error=MCPErrorDetail(code=code, message=message, data=data))


class MCPErrorCodes:
    """MCP/JSON-RPC error codes."""
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    TOOL_NOT_FOUND = -32001
    GENERATION_FAILED = -32002
    UNAUTHORIZED = -32004


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/mcp/tools")
async def list_mcp_tools() -> dict:
    """Return available MCP tools with their schemas."""
    return {
        "tools": [
            {
                "name": "document_generate",
                "description": "Generate professional documents in PDF or DOCX format with deterministic rendering",
                "category": "core",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "Markdown content to convert"
                        },
                        "format": {
                            "type": "string",
                            "enum": ["pdf", "docx", "html"],
                            "description": "Output document format"
                        },
                        "title": {
                            "type": "string",
                            "description": "Optional document title"
                        }
                    },
                    "required": ["content", "format"]
                }
            }
        ]
    }


@app.post("/mcp", response_model=MCPResponse)
async def mcp_tool_call(request: MCPRequest, fastapi_request: Request) -> MCPResponse:
    """Handle MCP tool invocations for document generation."""
    if request.method != "tools/call":
        return MCPResponse.error_response(
            request_id=request.id,
            code=MCPErrorCodes.METHOD_NOT_FOUND,
            message="Method not found",
        )

    if request.params.name != "document_generate":
        return MCPResponse.error_response(
            request_id=request.id,
            code=MCPErrorCodes.TOOL_NOT_FOUND,
            message=f"Tool not found: {request.params.name}",
        )

    try:
        if not GATEWAY_SHARED_SECRET:
            return MCPResponse.error_response(
                request_id=request.id,
                code=MCPErrorCodes.UNAUTHORIZED,
                message="Gateway authentication not configured",
            )

        gateway_auth = fastapi_request.headers.get(GATEWAY_AUTH_HEADER)
        if gateway_auth != GATEWAY_SHARED_SECRET:
            return MCPResponse.error_response(
                request_id=request.id,
                code=MCPErrorCodes.UNAUTHORIZED,
                message="Unauthorized gateway request",
            )

        # Validate parameters
        params = GenerateParams(**request.params.arguments)
        
        # Validate content size
        if len(params.content) > MAX_CONTENT_SIZE:
            return MCPResponse.error_response(
                request_id=request.id,
                code=MCPErrorCodes.INVALID_PARAMS,
                message="Content exceeds maximum size",
            )

        # Get user ID from header (Gateway forwards this)
        user_id = fastapi_request.headers.get("X-User-ID")
        if not user_id:
            return MCPResponse.error_response(
                request_id=request.id,
                code=MCPErrorCodes.INVALID_PARAMS,
                message="Missing X-User-ID header",
            )
        try:
            validate_user_id(user_id)
        except ValueError as e:
            return MCPResponse.error_response(
                request_id=request.id,
                code=MCPErrorCodes.INVALID_PARAMS,
                message=str(e),
            )
        
        # Get Gateway public URL
        gateway_url = os.getenv("GATEWAY_PUBLIC_URL", "http://localhost:8000")

        # Generate document
        result = await generate_document(params, user_id, gateway_url)
        return MCPResponse.success(request_id=request.id, result=result)

    except Exception as e:
        return MCPResponse.error_response(
            request_id=request.id,
            code=MCPErrorCodes.GENERATION_FAILED,
            message=f"Generation failed: {str(e)}",
        )


async def generate_document(params: GenerateParams, user_id: str, gateway_url: str) -> dict:
    """Generate a document using Pandoc."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Write input markdown (strip emojis for PDF to avoid LaTeX issues)
        input_file = tmp_path / "input.md"
        content = params.content
        if params.format == "pdf":
            content = strip_emojis(content)
        input_file.write_text(content, encoding="utf-8")
        
        # Determine output file
        output_ext = params.format
        filename = f"{uuid.uuid4()}.{output_ext}"
        output_file = tmp_path / filename
        
        # Build pandoc command
        cmd = [
            "pandoc",
            str(input_file),
            "-o", str(output_file),
            "--standalone",
        ]
        
        # Add title metadata if provided
        if params.title:
            cmd.extend(["-M", f"title={params.title}"])
        
        # Add format-specific options
        if params.format == "pdf":
            cmd.extend([
                "--pdf-engine=xelatex",
                "-V", "geometry:margin=1in",
            ])
        
        # Run pandoc
        try:
            subprocess.run(
                cmd,
                timeout=REQUEST_TIMEOUT_SEC,
                capture_output=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            raise ValueError(f"Pandoc error: {e.stderr.decode()}")
        except subprocess.TimeoutExpired:
            raise ValueError("Document generation timeout")
        
        # Persist file to shared volume with user isolation
        output_base = Path("/app/output").resolve()
        output_dir = (output_base / user_id).resolve()
        if not output_dir.is_relative_to(output_base):
            raise ValueError("Invalid output path")
        output_dir.mkdir(parents=True, exist_ok=True)
        final_path = output_dir / filename
        
        # Move file (shutil.move handles cross-device moves if necessary, checking simple rename first)
        import shutil
        shutil.move(str(output_file), str(final_path))
        
        # Get file size
        size_bytes = final_path.stat().st_size
        
        # Construct download URL
        download_url = f"{gateway_url}/files/{user_id}/{filename}"
        
        return {
            "format": params.format,
            "filename": filename,
            "size_bytes": size_bytes,
            "download_url": download_url,
        }


@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    """Handle unexpected errors."""
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )
