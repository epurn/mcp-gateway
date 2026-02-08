"""Tests for document generator request validation."""

import os
from fastapi.testclient import TestClient

os.environ.setdefault("TOOL_GATEWAY_SHARED_SECRET", "test_gateway_secret")

from tools.document_generator.app import app


client = TestClient(app)


def _make_request(headers=None, include_gateway_auth: bool = True):
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
    request_headers = dict(headers or {})
    if include_gateway_auth:
        request_headers.setdefault(
            "X-Gateway-Auth",
            os.environ["TOOL_GATEWAY_SHARED_SECRET"],
        )
    return client.post("/mcp", json=payload, headers=request_headers)


def test_missing_gateway_auth_header_returns_error():
    response = _make_request(include_gateway_auth=False)
    body = response.json()
    assert response.status_code == 200
    assert body["error"]["code"] == -32004
    assert body["error"]["message"] == "Unauthorized gateway request"


def test_invalid_gateway_auth_header_returns_error():
    response = _make_request(headers={"X-Gateway-Auth": "wrong"})
    body = response.json()
    assert response.status_code == 200
    assert body["error"]["code"] == -32004
    assert body["error"]["message"] == "Unauthorized gateway request"


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
