# MCP Gateway - Junior Dev Stories

## Story 1: Remove/Lock Down Debug Headers Endpoint
**Status:** Done

**Goal**
Remove the unauthenticated `/debug-headers` endpoint and ensure we do not log Authorization headers.

**Why**
All endpoints (except health) must require JWT, and sensitive headers must not be logged.

**Acceptance Criteria**
- `/debug-headers` is removed or requires auth (JWT + admin).
- No log line prints `Authorization` values.
- `src/mcp_transport/sse.py` keeps only non-sensitive debug logging.

**Notes**
- Implemented by removing the endpoint and header logging.

---

## Story 2: Enforce Safe `user_id` and Require `X-User-ID`
**Status:** Done

**Goal**
Ensure user isolation by validating `user_id` and enforcing safe paths in downloads and doc generation. Require `X-User-ID` in the tool container.

**Why**
Path traversal via `user_id` can bypass per-user isolation, and a missing `X-User-ID` can cause cross-user mixing.

**Acceptance Criteria**
- `src/files/router.py` rejects unsafe `user_id` values (allowlist pattern).
- Download path resolves under `/app/static/files` even with crafted input.
- `tools/document_generator/app.py` rejects requests without `X-User-ID`.
- Output directory resolves under `/app/output` and cannot escape via `user_id`.
- Tests or minimal validation snippets cover path traversal cases.

**Notes**
- Implemented with allowlist validation, resolved-path checks, and required `X-User-ID`. Added basic validation tests.
