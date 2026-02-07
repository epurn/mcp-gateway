# Handoff Notes

## Current Status
- **Secure File Downloads**: Implemented and verified.
  - Gateway serves files at `/files/{user_id}/{filename}`.
  - Strict ownership enforced: User A cannot access User B's files.
  - Files stored in `gateway_files` Docker volume.
- **Document Generator Optimization**:
  - Switched Dockerfile to use `pandoc/extra` (Alpine) base image.
  - MASSIVE build speed improvement (5s vs 70s).
- **Core Features**:
  - MCP Transport (SSE/JSON-RPC) working.
  - Authentication (JWT) working.
  - Call Tool meta-tool working.
- **Registry Sync**:
  - `sync_tools_from_config` now deactivates tools missing from `config/tools.yaml` (history preserved) and clears cache after sync.
  - Tool registry and policy updated to remove `git_readonly` and list the four calculator tools.
- **Local Test/Cache Hygiene**:
  - Pytest cache provider disabled to avoid permission issues (`-p no:cacheprovider`), temp dir pinned to `.pytest_tmp`.
  - Coverage scripts use `python -m coverage` with a repo-local coverage file.
  - Model cache lives in `model_cache/` and is wired via env vars in tests and docker compose.

## Deployment Notes
- The `gateway_files` volume permissions are automatically handled by the `init-files` service in `docker-compose.yml`. No manual intervention required.

## Next Steps
1. **Sandbox Service**: Design and implement secure sandbox for running untrusted code (Calculator/Python tools).
2. **Frontend**: Build a simple UI to test file generation and downloads.
3. **Usage Tracking**: Enhance `audit` logs to track file download events.

## Key Commands
- **Rebuild Services**: `docker compose -f docker/docker-compose.yml up -d --build`
- **Verify Downloads**: `python scripts/verify_downloads.py`
- **Check Logs**: `docker logs -f docker-gateway-1`
- **Coverage (Windows)**: `. .\.venv\Scripts\Activate.ps1; .\scripts\run_tests_cov.ps1`
- **Coverage (Unix)**: `./scripts/run_tests_cov.sh`
