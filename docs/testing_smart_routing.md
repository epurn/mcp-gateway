# Testing Scoped MCP Endpoints with a Real LLM

This guide shows how to test the v2 scoped MCP endpoint model with real MCP clients.

## Endpoint Model

Use one scoped endpoint per client/server config:

- `http://localhost:8000/calculator/sse`
- `http://localhost:8000/git/sse`
- `http://localhost:8000/docs/sse`

Each endpoint requires JWT auth and only exposes tools in that scope.

## v2 Behavior to Validate

- `tools/list` returns only tools for the endpoint scope (and user permissions).
- `tools/call` for an out-of-scope tool is denied.
- Unified `/sse` and `/messages` are not available.
- `find_tools` and `call_tool` are removed.

## Option 1: Antigravity (or Similar MCP Client)

Use one bridge instance per scope.

```json
{
  "mcpServers": {
    "gateway-calculator": {
      "command": "node",
      "args": [
        "scripts/mcp_http_bridge.js",
        "--endpoint",
        "http://localhost:8000/calculator/sse",
        "--issuer-url",
        "http://localhost:8010/token",
        "--user-id",
        "demo",
        "--roles",
        "developer",
        "--workspace",
        "demo"
      ]
    },
    "gateway-docs": {
      "command": "node",
      "args": [
        "scripts/mcp_http_bridge.js",
        "--endpoint",
        "http://localhost:8000/docs/sse",
        "--issuer-url",
        "http://localhost:8010/token",
        "--user-id",
        "demo",
        "--roles",
        "developer",
        "--workspace",
        "demo"
      ]
    }
  }
}
```

## Option 2: Claude Desktop

Configure one server per scope in `claude_desktop_config.json`.

```json
{
  "mcpServers": {
    "gateway-calculator": {
      "command": "node",
      "args": [
        "scripts/mcp_http_bridge.js",
        "--endpoint",
        "http://localhost:8000/calculator/sse",
        "--issuer-url",
        "http://localhost:8010/token",
        "--user-id",
        "demo",
        "--roles",
        "developer",
        "--workspace",
        "demo"
      ]
    },
    "gateway-git": {
      "command": "node",
      "args": [
        "scripts/mcp_http_bridge.js",
        "--endpoint",
        "http://localhost:8000/git/sse",
        "--issuer-url",
        "http://localhost:8010/token",
        "--user-id",
        "demo",
        "--roles",
        "developer",
        "--workspace",
        "demo"
      ]
    },
    "gateway-docs": {
      "command": "node",
      "args": [
        "scripts/mcp_http_bridge.js",
        "--endpoint",
        "http://localhost:8000/docs/sse",
        "--issuer-url",
        "http://localhost:8010/token",
        "--user-id",
        "demo",
        "--roles",
        "developer",
        "--workspace",
        "demo"
      ]
    }
  }
}
```

## Option 3: Continue / VS Code

Use workspace `.vscode/mcp.json` with top-level `servers`:

```json
{
  "servers": {
    "gateway-calculator": {
      "type": "stdio",
      "command": "node",
      "args": [
        "scripts/mcp_http_bridge.js",
        "--endpoint",
        "http://localhost:8000/calculator/sse",
        "--issuer-url",
        "http://localhost:8010/token",
        "--user-id",
        "demo",
        "--roles",
        "developer",
        "--workspace",
        "demo"
      ]
    },
    "gateway-git": {
      "type": "stdio",
      "command": "node",
      "args": [
        "scripts/mcp_http_bridge.js",
        "--endpoint",
        "http://localhost:8000/git/sse",
        "--issuer-url",
        "http://localhost:8010/token",
        "--user-id",
        "demo",
        "--roles",
        "developer",
        "--workspace",
        "demo"
      ]
    },
    "gateway-docs": {
      "type": "stdio",
      "command": "node",
      "args": [
        "scripts/mcp_http_bridge.js",
        "--endpoint",
        "http://localhost:8000/docs/sse",
        "--issuer-url",
        "http://localhost:8010/token",
        "--user-id",
        "demo",
        "--roles",
        "developer",
        "--workspace",
        "demo"
      ]
    }
  }
}
```

## Option 4: Direct HTTP Testing

Request a dev JWT first:

```bash
# curl -sS -X POST http://localhost:8010/token \
#   -H "X-Issuer-Token: dev_issuer_admin_token" \
#   -H "Content-Type: application/json" \
#   -d '{"user_id":"demo","roles":["developer"],"workspace":"demo","api_version":"1.1","expires_in_seconds":900}'
TOKEN="PASTE_ACCESS_TOKEN_HERE"
```

List calculator tools:

```bash
curl -sS -X POST http://localhost:8000/calculator/sse \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

Attempt out-of-scope call (expected deny):

```bash
curl -sS -X POST http://localhost:8000/calculator/sse \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"document_generate","arguments":{"content":"# test","format":"pdf"}}}'
```

## Success Criteria

- Calculator endpoint exposes calculator tools only.
- Docs endpoint exposes `document_generate` only.
- Cross-scope calls are denied with deterministic JSON-RPC errors.
- Calls to `find_tools`/`call_tool` fail as removed in v2.
