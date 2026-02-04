# Handoff Notes: Smart Routing Complete -> Document Generator

## Status Summary
- **Smart Routing**: ✅ Complete & Verified
- **Calculator Tools**: ✅ Integrated & Tested
- **Tool Registry**: ✅ Cleaned up (removed `exact_compute`)
- **Infrastructure**: ✅ Production-ready (Security, Testing, Config)

## Next Task: Document Generator
The next phase is implementing the **Document / Report Generation** tool.

### Context
- **Placeholder**: Currently exists in registry as `document_generate` (check `scripts/seed_registry.py`).
- **Goal**: Implement a deterministic PDF/DOCX generator backed by Pandoc.
- **Integration**: Must respond to `/mcp/invoke` via the Gateway.

### Key Resources
- **Registry Seed**: `d:\Development\mcp-gateway\scripts\seed_registry.py`
- **Gateway Router**: `d:\Development\mcp-gateway\src\gateway\router.py`
- **Docker**: New service needed in `docker-compose.yml` (similar to `calculator`).

### Pending Actions
1. Create new `tools/document_generator` directory.
2. Implement Pandoc wrapper service.
3. Update `docker-compose.yml` to include the new service.
4. Update `backend_url` in registry for `document_generate`.
