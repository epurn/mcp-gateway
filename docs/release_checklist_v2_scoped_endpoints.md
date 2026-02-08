# V2 Scoped Endpoints Release Checklist

Use this checklist before marking v2 scoped endpoints ready for cutover.

## Required Evidence

- [x] Scoped endpoint tests pass.
- [x] No direct tool exposure from host network.
- [x] Audit endpoint-path coverage verified.
- [x] v2 migration and client docs updated.

## Verification Commands

### 1) Scoped endpoint tests

```bash
pytest -q
RUN_DOCKER_INTEGRATION=1 pytest -q tests/integration/test_scoped_endpoints_compose.py
```

### 2) Direct exposure check

```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml -f docker/docker-compose.auth-test.yml ps
```

Expected:
- `nginx` publishes `8000` to host.
- `jwt_issuer` publishes `8010` only in auth-test overlay.
- `gateway`, `calculator`, and `document_generator` publish no host ports.

### 3) Audit path persistence check

Run the integration suite and verify the audit assertion in:
- `tests/integration/test_scoped_endpoints_compose.py::test_audit_path_persistence_for_scoped_endpoint`

Expected:
- Stored `audit_logs.endpoint_path` equals `/calculator/sse` for scoped calls made through Nginx.

### 4) Docs updated check

Verify these files reflect v2 scoped behavior:
- `README.md`
- `docs/deployment.md`
- `docs/testing_smart_routing.md`
- `docs/examples/vscode.mcp.json`

## Sign-off Record

- Date: February 8, 2026
- Release candidate: v2 scoped endpoints
- Reviewer: Codex runbook verification
- Notes:
  - `pytest -q` -> `152 passed, 4 skipped`
  - `RUN_DOCKER_INTEGRATION=1 pytest -q tests/integration/test_scoped_endpoints_compose.py` -> `3 passed`
  - `docker compose ... ps` confirms only `nginx` (`8000`) and `jwt_issuer` (`8010`, dev-only overlay) publish host ports.
