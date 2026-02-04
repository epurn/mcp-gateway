# MCP Gateway - Handoff Notes

## Last Updated: February 4, 2026

## Session Summary

Implemented the **meta-tool pattern** for dynamic tool discovery:

### What Was Built

1. **`find_tools` meta-tool** - Semantic search across tool registry
   - Uses sentence-transformers embeddings + pgvector for similarity search
   - Returns full `inputSchema` for discovered tools
   
2. **`call_tool` meta-tool** - Generic invoker for discovered tools
   - Proxies calls to any tool in the registry
   - Works with schemas returned by `find_tools`

3. **Updated Registry Seeding**
   - Only `find_tools` and `call_tool` have `core` category
   - All other tools discoverable via semantic search

### Files Modified

- `scripts/seed_registry.py` - Added meta-tools and input_schema definitions
- `src/mcp_transport/sse.py` - Added handlers for find_tools and call_tool
- `src/mcp_transport/service.py` - Simplified handle_tools_list_smart
- `README.md` - Added Smart Routing documentation

## Next Session Tasks

### Priority 1: Document Generator Improvements

**Problem:** Currently returns base64 content that LLM can't directly share with user.

**Solution:** Update document_generator to:
1. Save generated files to a persistent volume
2. Return a download URL instead of base64
3. Gateway serves files at `/files/{id}` endpoint

**Example Response (Current):**
```json
{"content": "UEsDBBQAAggI...", "format": "docx"}
```

**Example Response (Improved):**
```json
{"download_url": "http://gateway:8000/files/abc123.docx", "format": "docx", "size_bytes": 12139}
```

### Priority 2: Additional Improvements

- [ ] Add caching for embedding model (slow first load)
- [ ] Add tool usage analytics endpoint
- [ ] Consider multi-turn conversation awareness for find_tools

## Environment State

- Docker services running: gateway, db, calculator, document_generator
- All 8 tools seeded with embeddings and input_schema
- JWT token for testing: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`

## Quick Test Commands

```bash
# Check tools/list returns only core tools
python scripts/check_tools.py

# Test find_tools + call_tool flow
python scripts/test_call_tool.py

# Re-seed registry after changes
docker compose exec gateway python scripts/seed_registry.py
```
