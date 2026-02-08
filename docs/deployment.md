# Deployment Guide

## Docker Deployment
The easiest way to deploy the MCP Gateway is via Docker.

### 1. Build Image
```bash
docker build -t mcp-gateway .
```

### 2. Environment Variables
Configure these in your orchestrator (Kubernetes, ECS, etc.) or `.env` file.
Use `.env.example` as the single template; `.env.development` is optional for local use and ignored by git.

| Variable | Description | Default |
|----------|-------------|---------|
| `APP_NAME` | Name of the service | `MCP Gateway` |
| `DEBUG` | Enable debug mode | `False` |
| `DATABASE_URL` | Postgres connection string | `postgresql+asyncpg://...` |
| `JWT_SECRET_KEY` | Key for JWT signing | **REQUIRED** |
| `JWT_ALGORITHM` | JWT Algorithm | `HS256` |
| `JWT_ALLOWED_ALGORITHMS` | Comma-separated allow-list | `HS256` |
| `JWT_ISSUER` | Expected issuer (`iss`) | **REQUIRED** |
| `JWT_AUDIENCE` | Expected audience (`aud`) | **REQUIRED** |
| `JWT_MAX_TOKEN_AGE_MINUTES` | Max token age (0 disables) | `60` |
| `JWT_CLOCK_SKEW_SECONDS` | Clock skew allowance | `60` |
| `JWT_USER_ID_CLAIM` | User ID claim name | `sub` |
| `JWT_EXP_CLAIM` | Expiration claim name | `exp` |
| `JWT_IAT_CLAIM` | Issued-at claim name | `iat` |
| `JWT_TENANT_CLAIM` | Workspace/tenant claim name | `workspace` |
| `JWT_API_VERSION_CLAIM` | API version claim name | `v` |
| `JWT_ALLOWED_API_VERSIONS` | Comma-separated allow-list | *(empty = no check)* |
| `JWT_ISSUER_ADMIN_TOKEN` | Optional admin token for dummy issuer `/token` endpoint | *(empty = no header check)* |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token validity duration | `30` |
| `TOOL_GATEWAY_SHARED_SECRET` | Shared secret for tool auth | **REQUIRED** |
| `GATEWAY_PUBLIC_URL` | Base URL for file links | `http://localhost:8000` |

### 3. Database Migrations
Run migrations before starting the main application container.
```bash
alembic upgrade head
```

## MCP Endpoint Model (v2)
The gateway now exposes scoped MCP SSE endpoints:

- `POST /calculator/sse`
- `POST /git/sse`
- `POST /docs/sse`

Each endpoint requires JWT auth and only exposes tools in that scope.

### Hard Breaks from v1
- Unified `POST /sse` is removed.
- `POST /messages` is removed.
- Meta-tools `find_tools` and `call_tool` are removed from `tools/list` and cannot be called.

## Tool Authentication
Tools require the `X-Gateway-Auth` header matching `TOOL_GATEWAY_SHARED_SECRET`.
Ensure the gateway and tool containers share the same secret.

## Reverse Proxy
Use Nginx as the external ingress and route paths to the gateway:

- `/calculator/sse` -> `gateway:8000/calculator/sse`
- `/git/sse` -> `gateway:8000/git/sse`
- `/docs/sse` -> `gateway:8000/docs/sse`
- `/health` -> `gateway:8000/health`

Do not expose tool containers directly to the host network.

## VS Code MCP Config Example
Use `.vscode/mcp.json` with one server per scope. A tracked example is provided at:

- `docs/examples/vscode.mcp.json`

## Near-Prod JWT E2E Testing
Use `docker/docker-compose.auth-test.yml` to add a dummy JWT issuer service for integration tests:

```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml -f docker/docker-compose.auth-test.yml up -d --build
```

The issuer listens on `http://localhost:8010/token` and signs JWTs with your configured claim mapping (`JWT_USER_ID_CLAIM`, `JWT_EXP_CLAIM`, `JWT_TENANT_CLAIM`, `JWT_API_VERSION_CLAIM`).

## Authorization Policy
The gateway uses a `policy.yaml` file to define roles and default permissions (if configured). 
See `config/policy.yaml.example` for details.
