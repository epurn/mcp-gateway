"""Tests for document generator request validation."""

from fastapi.testclient import TestClient

from tools.document_generator.app import app


client = TestClient(app)


def _make_request(headers=None):
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "document_generate",
            "arguments": {
                "content": "hello",
                "format": "html",
            },
        },
        "id": "1",
    }
    return client.post("/mcp", json=payload, headers=headers or {})


def test_missing_user_id_header_returns_error():
    response = _make_request()
    body = response.json()
    assert response.status_code == 200
    assert body["error"]["code"] == -32602
    assert body["error"]["message"] == "Missing X-User-ID header"


def test_invalid_user_id_header_returns_error():
    response = _make_request(headers={"X-User-ID": "bad:id"})
    body = response.json()
    assert response.status_code == 200
    assert body["error"]["code"] == -32602
    assert body["error"]["message"] == "Invalid user id"
