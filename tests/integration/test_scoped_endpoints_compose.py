"""Docker Compose integration tests for scoped MCP endpoints."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid

import pytest


pytestmark = pytest.mark.integration

RUN_INTEGRATION = os.getenv("RUN_DOCKER_INTEGRATION") == "1"
BASE_URL = os.getenv("COMPOSE_GATEWAY_URL", "http://localhost:8000")
ISSUER_URL = os.getenv("COMPOSE_ISSUER_URL", "http://localhost:8010/token")
ISSUER_ADMIN_TOKEN = os.getenv("JWT_ISSUER_ADMIN_TOKEN", "dev_issuer_admin_token")

if not RUN_INTEGRATION:
    pytest.skip("Set RUN_DOCKER_INTEGRATION=1 to run Docker Compose integration tests.", allow_module_level=True)


def _request_json(
    method: str,
    url: str,
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 10.0,
) -> tuple[int, dict | str]:
    body_bytes = None
    req_headers = {"Accept": "application/json"}
    if payload is not None:
        body_bytes = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    if headers:
        req_headers.update(headers)

    request = urllib.request.Request(
        url,
        data=body_bytes,
        method=method,
        headers=req_headers,
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
            return response.getcode(), _parse_json(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        return exc.code, _parse_json(raw)


def _parse_json(raw: str) -> dict | str:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _issue_token(user_id: str, roles: list[str]) -> str:
    status, body = _request_json(
        method="POST",
        url=ISSUER_URL,
        payload={
            "user_id": user_id,
            "roles": roles,
            "workspace": "demo",
            "api_version": "1.1",
            "expires_in_seconds": 900,
        },
        headers={"X-Issuer-Token": ISSUER_ADMIN_TOKEN},
        timeout_seconds=10.0,
    )
    assert status == 200, body
    assert isinstance(body, dict), body
    token = body.get("access_token")
    assert isinstance(token, str) and token, body
    return token


def _jsonrpc_initialize() -> dict:
    return {
        "jsonrpc": "2.0",
        "id": "init-1",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "integration-test", "version": "1.0"},
        },
    }


def _jsonrpc_tool_call(name: str, arguments: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": "call-1",
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }


@pytest.fixture(scope="module", autouse=True)
def wait_for_stack() -> None:
    """Skip if the compose stack is not reachable for integration tests."""
    deadline = time.time() + 60
    last_error = None

    while time.time() < deadline:
        try:
            health_status, _ = _request_json("GET", f"{BASE_URL}/health", timeout_seconds=3.0)
            issuer_status, issuer_body = _request_json(
                "POST",
                ISSUER_URL,
                payload={
                    "user_id": "integration-health",
                    "roles": ["developer"],
                    "workspace": "demo",
                    "api_version": "1.1",
                    "expires_in_seconds": 60,
                },
                headers={"X-Issuer-Token": ISSUER_ADMIN_TOKEN},
                timeout_seconds=3.0,
            )
            if health_status == 200 and issuer_status == 200 and isinstance(issuer_body, dict):
                return
            last_error = f"health={health_status}, issuer={issuer_status}, issuer_body={issuer_body}"
        except Exception as exc:  # pragma: no cover - diagnostic only
            last_error = str(exc)
        time.sleep(2)

    pytest.skip(f"Compose integration stack is not reachable: {last_error}")


def test_auth_required_on_scoped_endpoints():
    for scope in ("calculator", "git", "docs"):
        status, body = _request_json(
            method="POST",
            url=f"{BASE_URL}/{scope}/sse",
            payload=_jsonrpc_initialize(),
        )
        assert status == 401, (scope, body)


def test_valid_in_scope_call_and_out_of_scope_denial():
    token = _issue_token(
        user_id=f"integration-dev-{uuid.uuid4().hex[:8]}",
        roles=["developer"],
    )
    auth_headers = {"Authorization": f"Bearer {token}"}

    success_status, success_body = _request_json(
        method="POST",
        url=f"{BASE_URL}/calculator/sse",
        payload=_jsonrpc_tool_call(
            "exact_calculate",
            {"operator": "add", "operands": ["1", "2"], "precision": 28},
        ),
        headers=auth_headers,
    )
    assert success_status == 200, success_body
    assert isinstance(success_body, dict), success_body
    assert success_body.get("error") is None, success_body
    assert success_body.get("result"), success_body

    denied_status, denied_body = _request_json(
        method="POST",
        url=f"{BASE_URL}/calculator/sse",
        payload=_jsonrpc_tool_call(
            "document_generate",
            {"content": "# Integration Test", "format": "pdf"},
        ),
        headers=auth_headers,
    )
    assert denied_status == 200, denied_body
    assert isinstance(denied_body, dict), denied_body
    assert denied_body.get("error", {}).get("code") == -32011, denied_body


def test_audit_path_persistence_for_scoped_endpoint():
    user_id = f"integration-audit-{uuid.uuid4().hex[:8]}"
    user_token = _issue_token(user_id=user_id, roles=["developer"])
    auth_headers = {"Authorization": f"Bearer {user_token}"}

    status, body = _request_json(
        method="POST",
        url=f"{BASE_URL}/calculator/sse",
        payload=_jsonrpc_tool_call(
            "exact_calculate",
            {"operator": "mul", "operands": ["7", "6"], "precision": 28},
        ),
        headers=auth_headers,
    )
    assert status == 200, body
    assert isinstance(body, dict), body
    assert body.get("error") is None, body

    admin_token = _issue_token(
        user_id=f"integration-admin-{uuid.uuid4().hex[:8]}",
        roles=["admin"],
    )

    deadline = time.time() + 20
    endpoint_path = None
    while time.time() < deadline:
        query_status, query_body = _request_json(
            method="GET",
            url=f"{BASE_URL}/admin/audit-logs?user_id={user_id}&tool_name=exact_calculate&limit=1",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert query_status == 200, query_body
        assert isinstance(query_body, dict), query_body
        items = query_body.get("items", [])
        if items:
            endpoint_path = items[0].get("endpoint_path")
            break
        time.sleep(1)

    assert endpoint_path == "/calculator/sse"
