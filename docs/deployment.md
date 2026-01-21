# Deployment Guide

## Docker Deployment
The easiest way to deploy the MCP Gateway is via Docker.

### 1. Build Image
```bash
docker build -t mcp-gateway .
```

### 2. Environment Variables
Configure these in your orchestrator (Kubernetes, ECS, etc.) or `.env` file.

| Variable | Description | Default |
|----------|-------------|---------|
| `APP_NAME` | Name of the service | `MCP Gateway` |
| `DEBUG` | Enable debug mode | `False` |
| `DATABASE_URL` | Postgres connection string | `postgresql+asyncpg://...` |
| `SECRET_KEY` | Key for JWT signing | **REQUIRED** |
| `ALGORITHM` | JWT Algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token validity duration | `30` |

### 3. Database Migrations
Run migrations before starting the main application container.
```bash
alembic upgrade head
```

## Authorization Policy
The gateway uses a `policy.yaml` file to define roles and default permissions (if configured). 
See `config/policy.yaml.example` for details.
