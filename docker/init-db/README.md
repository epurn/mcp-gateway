# pgvector Setup for MCP Gateway

This directory contains initialization scripts for PostgreSQL that are automatically executed when the database container starts.

## What's Here

- `01-enable-pgvector.sql` - Enables the pgvector extension for vector similarity search (RAG-MCP)

## How It Works

The `docker-compose.yml` mounts this directory to `/docker-entrypoint-initdb.d` in the PostgreSQL container. Any `.sql` or `.sh` files in this directory are automatically executed in alphabetical order when the database is initialized.

## Verifying pgvector Installation

After starting the containers, verify pgvector is installed:

```bash
docker compose exec db psql -U mcp_user -d mcp_gateway -c "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
```

Expected output:
```
 extname | extversion 
---------+------------
 vector  | 0.5.1
```

## Troubleshooting

If the extension isn't available:

1. **Ensure clean start**: The init scripts only run on first database creation
   ```bash
   docker compose down -v  # WARNING: Deletes all data
   docker compose up -d
   ```

2. **Check container logs**:
   ```bash
   docker compose logs db
   ```

3. **Manually enable** (if needed):
   ```bash
   docker compose exec db psql -U mcp_user -d mcp_gateway -c "CREATE EXTENSION IF NOT EXISTS vector;"
   ```
