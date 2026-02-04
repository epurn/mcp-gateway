# Document Generator Tool

Deterministic document generation service using Pandoc. Converts Markdown to PDF, DOCX, or HTML with professional formatting.

## Features

- **Multiple Formats**: Generate PDF, DOCX, or HTML documents
- **Markdown Input**: Write content in Markdown with full formatting support
- **Deterministic Output**: Same input always produces the same output
- **MCP Integration**: Exposes standard MCP JSON-RPC 2.0 endpoint
- **Security**: Runs as non-root user with resource limits

## API

### Health Check
```bash
GET /health
```

Returns `{"status": "ok"}`

### MCP Tool Endpoint
```bash
POST /mcp
```

**Request** (JSON-RPC 2.0):
```json
{
  "jsonrpc": "2.0",
  "id": "req-1",
  "method": "tools/call",
  "params": {
    "name": "document_generate",
    "arguments": {
      "content": "# My Document\n\nContent here...",
      "format": "pdf",
      "title": "Optional Title"
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-1",
  "result": {
    "format": "pdf",
    "size_bytes": 12345,
    "content": "base64-encoded-document..."
  }
}
```

## Configuration

Environment variables:
- `MAX_CONTENT_SIZE`: Maximum input size in bytes (default: 524288 = 512KB)
- `REQUEST_TIMEOUT_SEC`: Pandoc execution timeout (default: 30 seconds)

## Supported Formats

- **PDF**: Generated via pdflatex with 1-inch margins
- **DOCX**: Microsoft Word format
- **HTML**: Standalone HTML document

## Dependencies

- Python 3.11
- FastAPI + Uvicorn
- Pandoc
- TeX Live (for PDF generation)

## Docker

Built and deployed as part of the MCP Gateway stack:

```bash
docker compose up -d --build document_generator
```

Internal endpoint: `http://document_generator:8000/mcp`
