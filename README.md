# MCP Gateway

**A production-ready, secure gateway for the Model Context Protocol (MCP).**

## 🚀 What is this?
The **MCP Gateway** is a centralized middleware server designed to manage, secure, and observe interactions between Large Language Model (LLM) agents and your infrastructure tools.

Instead of giving agents direct, unchecked access to your internal APIs or databases, you route them through the Gateway. This allows you to enforce permissions, rate limits, and audit all tool usage.

## 🎯 Who is this for?
- **Enterprise Engineering Teams**: Who need to expose internal tools to AI agents safely within a corporate environment.
- **Platform Engineers**: Building "Agent Platforms" who need a standard way to govern tool access across many different agents.
- **Security Teams**: Who demand audit trails (logging every tool call) and strict RBAC (Role-Based Access Control) for AI systems.

## ✨ Key Features
- **🛡️ Granular Security**:
  - **RBAC**: Define exactly which user/agent roles can access which tools.
  - **JWT Authentication**: Validate upstream-authenticated tokens.
- **🚦 Traffic Control**:
  - **Rate Limiting**: Prevent abuse with per-user and per-tool quotas.
  - **Load Protection**: Payload size limits and backend timeouts.
- **🔍 Observability**:
  - **Audit Logging**: Every single tool invocation is logged to the database for compliance.
  - **Structured Logging**: JSON-formatted logs for easy ingestion into Splunk/Datadog.
- **⚡ Asynchronous Jobs**:
  - Support for long-running tool executions with status polling.
- **🔌 Standard MCP Support**:
  - Proxies JSON-RPC 2.0 requests to compliant MCP tool servers.

## 🏗️ Architecture
Nginx is the external ingress, and the gateway enforces scoped MCP access before routing to tool backends:

```mermaid
graph LR
    Client[AI Agent / MCP Client] -->|JWT + JSON-RPC| Nginx[Nginx Ingress :8000]
    Nginx -->|POST /calculator/sse| Gateway[MCP Gateway]
    Nginx -->|POST /git/sse| Gateway
    Nginx -->|POST /docs/sse| Gateway

    Gateway -->|Audit log| DB[(PostgreSQL)]
    Gateway -->|MCP + X-Gateway-Auth + X-User-ID| ToolA[Calculator MCP]
    Gateway -->|MCP + X-Gateway-Auth + X-User-ID| ToolB[Git Read-Only MCP]
    Gateway -->|MCP + X-Gateway-Auth + X-User-ID| ToolC[Document Generator MCP]
```

## 🧰 v1 Tool Set
Exactly three tool categories are supported in v1:
- **Calculator**: Deterministic math, statistics, unit conversion (✅ Implemented).
- **Git**: Read-only repository history and search (Planned).
- **Document Generator**: Deterministic PDF/DOCX/HTML generation (✅ Implemented).

Each tool is a separate containerized service and exposes:
- `GET /health`
- `POST /mcp` (JSON-RPC 2.0 tool call endpoint)

## 🔌 Scoped MCP Endpoints (v2)

The gateway exposes separate MCP SSE endpoints per tool scope:

- `POST /calculator/sse`
- `POST /git/sse`
- `POST /docs/sse`

When a client connects to one endpoint, `tools/list` only returns tools in that scope (subject to user permissions), and `tools/call` is enforced to that same scope.

### v2 Hard Breaks
- Unified `POST /sse` is removed.
- `POST /messages` is removed.
- Meta-tools `find_tools` and `call_tool` are removed.

## 🗂️ Tool Registry (Static)
Tool definitions live in `config/tools.yaml` and are synced into the registry at gateway startup. Access is filtered by `config/policy.yaml`.

By default, `config/tools.yaml` uses Docker Compose service names. If you run tools outside Docker, update `backend_url` values to reachable hostnames/ports.

**Note:** Tools removed from `config/tools.yaml` are **marked inactive** on startup (history is preserved). Add them back to re‑enable.

## 🧪 Development Deployment (Docker Compose)

### Prerequisites
- Docker & Docker Compose

### 1) Configure
```bash
cp .env.example .env
```
Set `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_ALLOWED_ALGORITHMS`, `JWT_ISSUER`, and `JWT_AUDIENCE` to match your upstream auth system. Set `JWT_MAX_TOKEN_AGE_MINUTES` (0 disables) and `JWT_CLOCK_SKEW_SECONDS` to enforce token freshness. Set `TOOL_GATEWAY_SHARED_SECRET` to a strong value for tool authentication.

If your upstream JWT uses non-standard claim names, configure:
`JWT_USER_ID_CLAIM`, `JWT_EXP_CLAIM`, `JWT_IAT_CLAIM`, `JWT_TENANT_CLAIM`, `JWT_API_VERSION_CLAIM`, and optional `JWT_ALLOWED_API_VERSIONS`. If your tokens do not include `iat`, set `JWT_MAX_TOKEN_AGE_MINUTES=0`.

For local development, you can copy `.env.example` to `.env.development` and use the dev compose override; `.env.development` is ignored by git.

### 2) Build and Start (Locked Networking)
```bash
docker compose -f docker/docker-compose.yml up -d --build
```
This brings up:
- `nginx` (exposed on port 8000)
- `gateway` (internal network only)
- `db` (internal network only)
- `calculator` (internal network only)
- `document_generator` (internal network only)

Tools are not exposed to the host; Nginx is the only external entrypoint.

### 3) Build and Start (Dev Overrides)
```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml up -d --build
```
This applies development environment overrides while keeping the same network exposure model.

### 3b) Optional: Start Dummy JWT Issuer (Near-Prod Auth Testing)
```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml -f docker/docker-compose.auth-test.yml up -d --build jwt_issuer
```
This adds `jwt_issuer` on `http://localhost:8010` for end-to-end JWT flow testing.
If `JWT_ISSUER_ADMIN_TOKEN` is set, include `X-Issuer-Token` when requesting tokens.

Issue a token (PowerShell):
```powershell
$body = @{
  user_id = "demo"
  roles = @("developer")
  workspace = "demo"
  api_version = "1.1"
  expires_in_seconds = 3600
} | ConvertTo-Json

$headers = @{ "X-Issuer-Token" = "dev_issuer_admin_token" }
$token = (Invoke-RestMethod -Method Post -Uri "http://localhost:8010/token" -Headers $headers -ContentType "application/json" -Body $body).access_token
$token
```

### 4) Invoke a Tool (Example)
Generate a test JWT (development only):
```bash
python -c "from src.auth.utils import create_test_jwt; print(create_test_jwt(user_id='demo', roles=['developer']))"
```

Then call the gateway:
```bash
TOKEN="YOUR_JWT_TOKEN_HERE"
curl -sS -X POST "http://localhost:8000/mcp/invoke" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tool_name":"exact_calculate","arguments":{"operator":"add","operands":["1.2","2.3"],"precision":28}}'
```

### 5) Connect via MCP Clients (Scoped Endpoints)
Use the repo bridge script to connect stdio MCP clients to a scoped SSE endpoint. The bridge auto-issues a short-lived JWT from the dummy issuer.

For a single scope, pass the scoped endpoint explicitly:
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
    }
  }
}
```
*Note: schema keys differ by client; VS Code uses `servers` (see below).*

### VS Code / Continue Example
Use the workspace `.vscode/mcp.json` format with one server per scope:
```json
{
  "servers": {
    "gateway-calculator": {
      "type": "stdio",
      "command": "node",
      "args": ["scripts/mcp_http_bridge.js", "--endpoint", "http://localhost:8000/calculator/sse", "--issuer-url", "http://localhost:8010/token", "--user-id", "demo", "--roles", "developer", "--workspace", "demo"]
    },
    "gateway-git": {
      "type": "stdio",
      "command": "node",
      "args": ["scripts/mcp_http_bridge.js", "--endpoint", "http://localhost:8000/git/sse", "--issuer-url", "http://localhost:8010/token", "--user-id", "demo", "--roles", "developer", "--workspace", "demo"]
    },
    "gateway-docs": {
      "type": "stdio",
      "command": "node",
      "args": ["scripts/mcp_http_bridge.js", "--endpoint", "http://localhost:8000/docs/sse", "--issuer-url", "http://localhost:8010/token", "--user-id", "demo", "--roles", "developer", "--workspace", "demo"]
    }
  }
}
```
Tracked example file: `docs/examples/vscode.mcp.json`.

### 6) Test with a Real LLM (MCP Client)
Use any MCP-compatible client (e.g., Claude Desktop, Continue, or your own MCP client) that supports stdio-based MCP servers.

1. Start the stack (Docker Compose).
2. Configure one or more scoped MCP servers using the bridge script.
3. Prompt your LLM in each server context:
   - Calculator: “Calculate the average of 1, 2, and 3.”
   - Docs: “Generate a short PDF report in Markdown.”

## 🧪 Development Deployment (Local Python)

### Prerequisites
- Python 3.11+
- Docker & Docker Compose (for Postgres and tools)

### 1) Configure
```bash
cp .env.example .env
```
Update `DATABASE_URL` to point at your local Postgres (for example `localhost:5432`), and set `JWT_SECRET_KEY`/`JWT_ALGORITHM`/`JWT_ALLOWED_ALGORITHMS`/`JWT_ISSUER`/`JWT_AUDIENCE`/`JWT_MAX_TOKEN_AGE_MINUTES`/`JWT_CLOCK_SKEW_SECONDS`/`TOOL_GATEWAY_SHARED_SECRET` plus any claim-mapping settings. For local dev, prefer `.env.development` (ignored by git) with `docker-compose.dev.yml`.

If the gateway runs on the host, update `config/tools.yaml` to point at `http://localhost:8091/mcp` (and future tool ports) or mount a host-specific config file.

### 2) Start Infrastructure and Tools
```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml up -d db calculator document_generator
```

### 3) Run Gateway
```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements-dev.txt

alembic upgrade head
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

## 🏭 Production Deployment

### Gateway
1. Build the gateway image:
   ```bash
   docker build -t mcp-gateway .
   ```
2. Run Postgres externally and point `DATABASE_URL` to it.
3. Run the gateway with production env:
   - `DEBUG=False`
   - `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_ALLOWED_ALGORITHMS`, `JWT_ISSUER`, `JWT_AUDIENCE`, `JWT_MAX_TOKEN_AGE_MINUTES`, `JWT_CLOCK_SKEW_SECONDS`, and `TOOL_GATEWAY_SHARED_SECRET` set to production values
   - `DATABASE_URL` set to your production database
4. Mount `config/tools.yaml` and `config/policy.yaml` as read-only in the container.
5. Run `alembic upgrade head` during deploys to apply schema changes.

### Tools
- Build and deploy each tool as its own container image.
- Ensure each tool exposes `POST /mcp` and is reachable at the `backend_url` configured in `config/tools.yaml`.
- Keep tools stateless and offline-safe; no auth logic inside tools.

## 📖 Documentation
- [Deployment Guide](docs/deployment.md)
- [V2 Release Checklist](docs/release_checklist_v2_scoped_endpoints.md)
- Interactive API docs are available from the gateway service directly (`/docs`) when exposed in your environment.

## 🧪 Testing
Run the test suite with coverage reporting:
```bash
pip install -r requirements-dev.txt
python -m pytest -p no:cacheprovider --cov=src
```
