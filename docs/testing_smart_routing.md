# Testing Smart Routing with a Real LLM

This guide shows you how to test the dynamic tool registry with an actual LLM client.

## Option 1: Test with Antigravity (Current Setup) ✅

You're already connected! The Gateway's SSE endpoint implements smart routing via `handle_tools_list_smart()`.

### How It Works

When Antigravity (or any MCP client) connects:
1. Client sends `tools/list` request
2. Gateway extracts context from your conversation
3. Smart routing filters tools based on strategy (default: `hybrid`)
4. LLM only sees relevant tools

### Test It Now

**In this Antigravity session**, try asking:

```
"Can you generate a PDF report for me?"
```

The Gateway should:
- Extract keywords: "generate", "PDF", "report"
- Use semantic search to find `document_generate`
- Return only relevant tools to the LLM
- LLM calls `document_generate` with appropriate parameters

### View What Tools Are Exposed

Check your MCP config to see what tools Antigravity sees:

```json
{
  "mcpServers": {
    "gateway": {
      "command": "npx",
      "args": [
        "-y",
        "@nimbletools/mcp-http-bridge",
        "--endpoint",
        "http://localhost:8000/sse",
        "--token",
        "YOUR_JWT_HERE"
      ]
    }
  }
}
```

## Option 2: Test with Claude Desktop

### Setup

1. **Install Claude Desktop** (if not already installed)

2. **Configure MCP** in `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "mcp-gateway": {
      "command": "npx",
      "args": [
        "-y",
        "@nimbletools/mcp-http-bridge",
        "--endpoint",
        "http://localhost:8000/sse",
        "--token",
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkZXZlbG9wZXIiLCJyb2xlcyI6WyJkZXZlbG9wZXIiXSwiYWxsb3dlZF90b29scyI6WyIqIl0sImV4cCI6MTgwMTc1ODMyMSwiaWF0IjoxNzcwMjIyMzIxfQ.fewNla9MQSy8ijjAfrvLplgx3XukRqKm-tbHSdRwak4"
      ]
    }
  }
}
```

3. **Restart Claude Desktop**

4. **Test queries**:
   - "Calculate 123.45 + 678.90 with high precision"
   - "Generate a PDF report about quarterly sales"
   - "Convert 5 kilometers to miles"

## Option 3: Test with Continue (VS Code)

### Setup

1. **Install Continue extension** in VS Code

2. **Configure** in `.continue/config.json`:

```json
{
  "mcpServers": [
    {
      "command": "npx",
      "args": [
        "-y",
        "@nimbletools/mcp-http-bridge",
        "--endpoint",
        "http://localhost:8000/sse",
        "--token",
        "YOUR_JWT_HERE"
      ]
    }
  ]
}
```

## Option 4: Direct HTTP Testing (Manual)

### Test Tool Discovery

```bash
# Get JWT token
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkZXZlbG9wZXIiLCJyb2xlcyI6WyJkZXZlbG9wZXIiXSwiYWxsb3dlZF90b29scyI6WyIqIl0sImV4cCI6MTgwMTc1ODMyMSwiaWF0IjoxNzcwMjIyMzIxfQ.fewNla9MQSy8ijjAfrvLplgx3XukRqKm-tbHSdRwak4"

# Test with document-related context
curl -X POST http://localhost:8000/sse \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list",
    "params": {
      "_meta": {
        "progressToken": "test-1"
      }
    }
  }'
```

## Monitoring Smart Routing

### Check Gateway Logs

```bash
docker compose logs -f gateway | grep "tools/list"
```

You should see:
- Context extraction
- Category matching
- Semantic search results
- Final tool list returned

### Environment Variables

Control routing behavior in `.env`:

```bash
# Strategy: all, rule, rag, hybrid (default)
TOOL_FILTER_STRATEGY=hybrid

# Maximum tools to return
MAX_TOOLS_PER_REQUEST=15
```

## Expected Behavior

### Query: "Generate a PDF report"

**Smart Routing Process:**
1. Extract categories: `["core"]` (no math/filesystem keywords)
2. Semantic search: `document_generate` (high similarity)
3. Return: `["document_generate", "git_readonly", ...]`

**LLM sees:**
- `document_generate` ✅ (relevant)
- Core tools ✅ (always included)
- Calculator tools ❌ (filtered out - not relevant)

### Query: "Calculate the average of 1, 2, 3"

**Smart Routing Process:**
1. Extract categories: `["math"]` (keyword: "calculate", "average")
2. Category match: All calculator tools
3. Return: `["exact_calculate", "exact_statistics", ...]`

**LLM sees:**
- Calculator tools ✅ (relevant)
- Core tools ✅ (always included)
- `document_generate` ❌ (filtered out - not relevant)

## Debugging

### Enable Debug Logging

In `.env`:
```bash
DEBUG=True
LOG_LEVEL=DEBUG
```

### Test Script

Run the registry test to verify embeddings:
```bash
docker compose exec gateway python scripts/test_registry.py
```

### Check Database

```bash
docker compose exec db psql -U mcp_user -d mcp_gateway -c "SELECT name, categories, embedding IS NOT NULL as has_embedding FROM tools;"
```

## Success Criteria

✅ **Smart routing works if:**
- Document queries return `document_generate`
- Math queries return calculator tools
- LLM successfully calls the correct tool
- Irrelevant tools are filtered out

❌ **Issues to watch for:**
- All tools returned regardless of context (strategy=all)
- Embeddings missing (run `seed_registry.py`)
- Threshold too high (no semantic matches)
