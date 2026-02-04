import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from .config import get_settings
from .database import engine, Base, AsyncSessionLocal
from .auth.exceptions import (
    AuthenticationError,
    AuthorizationError,
    MCPGatewayError
)
from .registry import router as registry_router
from .registry.service import sync_tools_from_config, clear_tool_cache
from .registry.models import Tool  # noqa: F401 - Import so Base.metadata sees it
from src.gateway.router import router as gateway_router
from src.jobs.router import router as jobs_router
from src.jobs.router import router as jobs_router
from src.audit.router import router as audit_router
from src.mcp_transport.sse import router as mcp_sse_router


from .audit.models import AuditLog  # noqa: F401 - Import so Base.metadata sees it
from .gateway.exceptions import (
    ToolNotFoundError,
    BackendTimeoutError,
    BackendUnavailableError,
    PayloadTooLargeError,
    BackendError,
)
from .ratelimit import RateLimitExceededError

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create tables (simplistic migration for MVP)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        await sync_tools_from_config(session)
    clear_tool_cache()
    
    # Initialize global HTTP client for connection pooling
    # timeouts=None removes global default timeout, allowing per-request timeouts
    app.state.http_client = httpx.AsyncClient(timeout=None)
    
    yield
    
    # Shutdown: Close database connection and HTTP client
    await app.state.http_client.aclose()
    await engine.dispose()

app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan,
    debug=settings.DEBUG
)

# Global exception handlers
@app.exception_handler(AuthenticationError)
async def authentication_exception_handler(request: Request, exc: AuthenticationError):
    return JSONResponse(
        status_code=401,
        content={"error": exc.code, "message": exc.message}
    )

@app.exception_handler(AuthorizationError)
async def authorization_exception_handler(request: Request, exc: AuthorizationError):
    return JSONResponse(
        status_code=403,
        content={"error": exc.code, "message": exc.message}
    )

@app.exception_handler(MCPGatewayError)
async def gateway_exception_handler(request: Request, exc: MCPGatewayError):
    return JSONResponse(
        status_code=500,
        content={"error": exc.code, "message": exc.message}
    )

@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.APP_NAME}

# Include routers
app.include_router(registry_router)
app.include_router(gateway_router)
app.include_router(audit_router)
app.include_router(audit_router)
app.include_router(jobs_router)
app.include_router(mcp_sse_router)



# Gateway-specific exception handlers
@app.exception_handler(ToolNotFoundError)
async def tool_not_found_handler(request: Request, exc: ToolNotFoundError):
    return JSONResponse(
        status_code=404,
        content={"error": exc.code, "message": exc.message}
    )


@app.exception_handler(BackendTimeoutError)
async def backend_timeout_handler(request: Request, exc: BackendTimeoutError):
    return JSONResponse(
        status_code=504,
        content={"error": exc.code, "message": exc.message}
    )


@app.exception_handler(BackendUnavailableError)
async def backend_unavailable_handler(request: Request, exc: BackendUnavailableError):
    return JSONResponse(
        status_code=502,
        content={"error": exc.code, "message": exc.message}
    )


@app.exception_handler(PayloadTooLargeError)
async def payload_too_large_handler(request: Request, exc: PayloadTooLargeError):
    return JSONResponse(
        status_code=413,
        content={"error": exc.code, "message": exc.message}
    )


@app.exception_handler(BackendError)
async def backend_error_handler(request: Request, exc: BackendError):
    return JSONResponse(
        status_code=502,
        content={"error": exc.code, "message": exc.message}
    )


@app.exception_handler(RateLimitExceededError)
async def rate_limit_handler(request: Request, exc: RateLimitExceededError):
    return JSONResponse(
        status_code=429,
        content={"error": exc.code, "message": exc.message},
        headers={"Retry-After": str(int(exc.retry_after) + 1)}
    )
