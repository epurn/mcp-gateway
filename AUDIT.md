# System Audit Report

**Date:** 2026-02-07
**Auditor:** Agent (Self-Audit + External Review)
**Scope:** Architecture, Security, and Rule Compliance

## 1. System Overview
The MCP Gateway is a containerized application acting as the single endpoint for LLM-tool interactions. It implements a **Meta-Tool Pattern** (`find_tools`, `call_tool`) to dynamically route requests to backend tool containers (`calculator`, `document_generator`).

## 2. Compliance with .agent/rules/rules.md

### 2.1 Architecture & Infrastructure
- [x] **Docker-First**: All services defined in `docker/docker-compose.yml`. No local execution required.
- [x] **Container Isolation**: Tools run in separate containers (`docker-calculator-1`, `docker-document_generator-1`).
- [x] **Service Independence**: Gateway communicates via HTTP (Calculator) and JSON-RPC (DocGen).
- [x] **Offline-First**: Embeddings use `sentence-transformers` (local), PGVector (local), and `pandoc` (local). No external API calls.

### 2.2 Security & Access Control
- [ ] **Authentication**: JWT validation enforced on most endpoints, but `/debug-headers` is unauthenticated in `src/mcp_transport/sse.py`, violating the "all endpoints except health" rule.
- [x] **Least Privilege**: 
  - `document_generator` runs as `appuser` (UID 1000).
  - Database access scoped to `mcp_user`.
- [ ] **Strict User Isolation**: `/files/{user_id}/{filename}` exists, but `user_id` is not validated for path safety in `src/files/router.py`, and `tools/document_generator/app.py` trusts `X-User-ID` directly when writing to `/app/output`. Also, `verify_downloads.py` was referenced but not found in the repo.
- [x] **Arbitrary Execution**: No shell execution features exposed. `pandoc` is the only external process spawned, with strict argument control.

### 2.3 Tool Patterns
- [x] **Meta-Tool Pattern**: `find_tools` and `call_tool` implemented in `src/registry` and `src/gateway`.
- [x] **Stateless Tools**: Tools persist state to DB/Filesystem, not memory.

### 2.4 Development Standards
- [x] **Automated Setup**: `init-files` container handles volume permissions automatically on startup.
- [x] **Build Optimization**: `document_generator` uses `pandoc/extra` base image, reducing build time to ~5s.

## 3. Security Architecture Review

### Attack Surface
- **Public Endpoints**: `/sse`, `/messages`, `/files/{u}/{f}`, `/debug-headers`. `/debug-headers` is currently unauthenticated.
- **Internal Network**: All containers on `mcp-internal` network. `gateway` is the only ingress.

### Data Protection
- **Transit**: HTTP (Internal). HTTPS termination expected at load balancer level (out of scope for Docker Compose).
- **At Rest**: Files stored in Docker volume `gateway_files`. Database `postgres_data` volume.

### Known Risks & Mitigations
- **Risk**: Malicious Markdown could potentially exploit Pandoc.
  - *Mitigation*: Input size limits (`MAX_CONTENT_SIZE`) and strict content validation (strip emojis for LaTeX).
- **Risk**: Token leakage.
  - *Mitigation*: User isolation checks exist, but rely on safe `user_id` values; see strict user isolation findings for hardening needs.
- **Risk**: Unauthenticated debug endpoint (`/debug-headers`) exposes request headers and violates auth requirements.
  - *Mitigation*: Remove in production or require JWT + admin role; avoid logging `Authorization`.
- **Risk**: User ID path traversal could escape per-user directories.
  - *Mitigation*: Validate `user_id` against a strict allowlist and enforce resolved paths are under `/app/static/files` and `/app/output`.
- **Risk**: Missing `X-User-ID` defaults to a shared `anonymous` bucket.
  - *Mitigation*: Require header presence in tool container and return an error if missing.

## 4. Recommendations for Next Agent

1.  **Remove or secure `/debug-headers`**: This endpoint is unauthenticated and violates the auth rule. Gate it behind JWT + admin role or delete it.
2.  **Harden user ID handling**: Validate `user_id` (allowlist pattern) and enforce resolved paths are under `/app/static/files` and `/app/output` to prevent traversal.
3.  **Require `X-User-ID` in tools**: Do not default to `anonymous`; fail closed if missing.
4.  **Audit Logs**: Ensure `audit_logs` table captures *file download* events, not just tool invocations.
5.  **Dependency Scanning**: Periodic scan of `pandoc/extra` and `python:slim` images for vulnerabilities.

## 5. External Assessment (2026-02-07)

### High
1. **Unauthenticated debug endpoint** (`/debug-headers`)
   - **Evidence**: `src/mcp_transport/sse.py` defines `/debug-headers` without `get_current_user`.
   - **Impact**: Breaks "all endpoints except health require JWT". Also returns and logs headers, including `Authorization`, which risks token exposure.

### Medium
2. **User ID path traversal risk**
   - **Evidence**: `src/files/router.py` validates `filename` only; `tools/document_generator/app.py` uses `X-User-ID` to build `/app/output/<user_id>`.
   - **Impact**: If `user_id` includes path separators or `..`, a user could escape per-user directories and access/write files outside their sandbox, including other users' files.
3. **Shared `anonymous` output bucket**
   - **Evidence**: `tools/document_generator/app.py` falls back to `user_id = "anonymous"` when header missing.
   - **Impact**: If the gateway fails to forward `X-User-ID` (misconfig/bug), users could read each other's generated files via the shared directory.

### Low
4. **No explicit output size cap for generated files**
   - **Evidence**: Input size is capped, but generated file size is not enforced.
   - **Impact**: Potential disk exhaustion if output grows unexpectedly (e.g., embedded resources).
