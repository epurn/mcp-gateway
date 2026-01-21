# MCP Gateway - Project Board

## Epic 1: Project Setup & Infrastructure ✅
**Goal**: Establish the foundational infrastructure for the MCP Gateway.

### Stories
- [x] **1.1**: Set up project directory structure and `.agent` configurations
- [x] **1.2**: Create `docker-compose.yml` with PostgreSQL service
- [x] **1.3**: Define `requirements.txt` with core dependencies
- [x] **1.4**: Implement `src/config.py` using Pydantic Settings
- [x] **1.5**: Implement `src/database.py` with SQLAlchemy AsyncEngine
- [x] **1.6**: Create basic FastAPI app in `src/main.py` with health check
- [x] **1.7**: Add database migration tooling (Alembic)
- [x] **1.8**: Create `.env.example` file with all required environment variables

---

## Epic 2: Authentication & Authorization ✅
**Goal**: Implement JWT-based authentication and user identity extraction.

### Stories
- [x] **2.1**: Create `src/auth/exceptions.py` with custom auth exceptions
- [x] **2.2**: Implement `src/auth/models.py` with Pydantic models for User/Claims
- [x] **2.3**: Implement `src/auth/utils.py` with JWT decode and validation functions
- [x] **2.4**: Create `src/auth/dependencies.py` with FastAPI dependency for current user
- [x] **2.5**: Write unit tests for JWT validation (valid/invalid/expired tokens)
- [x] **2.6**: Add authorization policy framework (YAML-based for MVP)
- [x] **2.7**: Implement permission checking logic (user → allowed tools)

---

## Epic 3: Tool Registry & Discovery ✅
**Goal**: Build a registry to store tool definitions and expose filtered discovery.

### Stories
- [x] **3.1**: Design database schema for Tool registry (table + columns)
- [x] **3.2**: Create SQLAlchemy model in `src/registry/models.py`
- [x] **3.3**: Create Pydantic schemas in `src/registry/schemas.py`
- [x] **3.4**: Implement `src/registry/repository.py` for DB access
- [x] **3.5**: Implement `src/registry/service.py` with filtering logic
- [x] **3.6**: Create `src/registry/router.py` with discovery endpoint
- [x] **3.7**: Seed database with 3-5 sample tools for testing
- [x] **3.8**: Write integration tests for tool discovery with different user roles

---

## Epic 4: Gateway Router & Proxying ✅
**Goal**: Handle MCP tool invocation requests and proxy them to backends.

### Stories
- [x] **4.1**: Define MCP protocol request/response schemas
- [x] **4.2**: Implement `src/gateway/exceptions.py` for gateway-specific errors
- [x] **4.3**: Create `src/gateway/proxy.py` to forward requests to backend MCP servers
- [x] **4.4**: Implement `src/gateway/service.py` with validation and routing logic
- [x] **4.5**: Create `src/gateway/router.py` with main MCP endpoint (`POST /mcp/invoke`)
- [x] **4.6**: Add request timeout handling
- [x] **4.7**: Add payload size validation
- [x] **4.8**: Propagate trace/correlation IDs to backends
- [x] **4.9**: Write integration tests with mock MCP backend

---

## Epic 5: Rate Limiting & Quotas ✅
**Goal**: Prevent abuse and enforce usage limits per user/tool.

### Stories
- [x] **5.1**: Choose rate limiting strategy (in-memory token bucket)
- [x] **5.2**: Implement per-user rate limiter (1000 req/min)
- [x] **5.3**: Implement per-tool rate limiter (100 req/min)
- [x] **5.4**: Add concurrency caps for expensive tools
- [x] **5.5**: Implement circuit breaker for failing backends
- [x] **5.6**: Add rate limit headers to responses
- [x] **5.7**: Write tests for rate limiting behavior

---

## Epic 6: Audit Logging ✅
**Goal**: Log every tool invocation for security and compliance.

### Stories
- [x] **6.1**: Design audit log schema (metadata only)
- [x] **6.2**: Create SQLAlchemy model in `src/audit/models.py`
- [x] **6.3**: Implement async audit logger in `src/audit/logger.py`
- [x] **6.4**: Add structured JSON logging with `structlog`
- [x] **6.5**: Ensure `request_id` and `user_id` are in every log entry
- [x] **6.6**: Add audit log query endpoint (for admins)
- [x] **6.7**: Write tests for audit logging

---

## Epic 7: Async Jobs (MVP-lite) ✅
**Goal**: Support long-running operations with job tracking.

### Stories
- [x] **7.1**: Design job schema (job_id, status, created_at, result)
- [x] **7.2**: Create SQLAlchemy model for jobs
- [x] **7.3**: Implement job creation and status tracking
- [x] **7.4**: Create endpoints: `get_job_status`, `get_job_result`
- [x] **7.5**: Integrate simple worker (background task or separate process)
- [x] **7.6**: Add job cleanup/expiration logic
- [x] **7.7**: Write tests for job lifecycle

---

## Epic 8: Testing & Documentation ✅
**Goal**: Ensure code quality and provide usage documentation.

### Stories
- [x] **8.1**: Set up `pytest` with async support
- [x] **8.2**: Create `conftest.py` with DB fixtures
- [x] **8.3**: Achieve >80% code coverage for core modules
- [x] **8.4**: Write API documentation (OpenAPI/Swagger)
- [x] **8.5**: Create README.md with setup instructions
- [x] **8.6**: Document deployment guide (Docker, environment variables)
- [x] **8.7**: Add example `.env` and policy YAML files

---

## Current Focus
**Active Epic**: V1 Demo Tools (Calculator, Git Read-Only, Document Generation)
**Next Story**: Seed and wire tool registry definitions for v1 demos

