# MCP Gateway Handoff Notes

## Current Goal
Fix MCP tool discovery in VS Code MCP flow.  
Current behavior: gateway connects/authenticates, but `tools/list` returns zero tools.  
Expected behavior: at least `find_tools` and `call_tool` are always discoverable.

## What Is Working
- VS Code MCP connection now uses local stdio bridge:
  - `.vscode/mcp.json` runs `node scripts/mcp_http_bridge.js`
- Bridge is stable for VS Code:
  - newline-delimited JSON-RPC stdio input/output supported
  - token auto-issued from dummy auth service (`jwt_issuer`)
- Auth path is working (401 issue resolved).
- Gateway SSE endpoint is reachable and handles `initialize`.

## Confirmed Problem
- `tools/list` returns `{"tools":[]}`.
- No tools shown to MCP client.

## Most Likely Root Cause
- `src/mcp_transport/service.py` defaults to `TOOL_FILTER_STRATEGY=minimal`.
- `minimal` path returns only `get_core_tools(db)`.
- `get_core_tools` (`src/registry/repository.py`) filters tools where categories overlap `["core"]`.
- `sync_tools_from_config` (`src/registry/service.py`) does not assign categories, and `config/tools.yaml` does not include meta-tools (`find_tools`, `call_tool`).
- Result: no rows match core filter, so empty tool list.

## Constraints (Do Not Violate)
- Keep gateway thin.
- Keep v1 locked tool set unchanged (Git, Calculator, Document Generator as real tools).
- Meta-tool pattern remains (`find_tools`, `call_tool`).
- Prefer minimal diffs.
- Rerun tests after changes.

## Suggested Fix Direction
1. Ensure `find_tools` and `call_tool` are always returned in `handle_tools_list` / `handle_tools_list_smart`, independent of DB core categories.
2. Keep DB-backed tools for discovered real tools unchanged.
3. Add tests to assert `tools/list` includes meta-tools even when registry has no `core` categories.
4. Do not expand v1 real tool set.

## Acceptance Criteria
- In VS Code MCP, `tools/list` includes:
  - `find_tools`
  - `call_tool`
- Existing auth and SSE flow still works.
- Existing tests pass plus new/updated tests for tool listing behavior.

## Known Good Commands
- Run tests:
  - `python -m pytest -p no:cacheprovider`
- Start stack with auth test service:
  - `docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml -f docker/docker-compose.auth-test.yml up -d`

## New Context Starting Prompt (Copy/Paste)
Use this exact prompt in a fresh context:

```text
Use HANDOFF_NOTES.md as authoritative context.

Task: Fix MCP discovery so tools/list always exposes the two gateway meta-tools: find_tools and call_tool. Right now VS Code connects but sees zero tools.

Constraints:
- Keep architecture thin and aligned with AGENTS.md.
- Do not expand v1 real tool set.
- Keep changes minimal and security-safe.
- Do not run end-to-end tool invocations yet unless I explicitly ask.

Implementation requirements:
1) Update the MCP tool-listing path so find_tools and call_tool are always present.
2) Preserve existing DB-backed discovery behavior for real tools.
3) Add/adjust tests to prevent regression.
4) Run test suite at end.

Then report:
- Files changed
- Why zero-tools happened
- Exact behavior after fix
```
