
import requests
import json
import sys

BASE_URL = "http://127.0.0.1:8081"

def test_health():
    print("Testing /health...", end=" ")
    try:
        resp = requests.get(f"{BASE_URL}/health")
        resp.raise_for_status()
        assert resp.json() == {"status": "ok"}
        print("OK")
    except Exception as e:
        print(f"FAIL: {e}")
        sys.exit(1)

def test_arithmetic_mcp():
    print("Testing /mcp (arithmetic)...", end=" ")
    payload = {
        "jsonrpc": "2.0",
        "id": "req-1",
        "method": "tools/call",
        "params": {
            "name": "exact_compute",
            "arguments": {
                "operation": "arithmetic",
                "params": {
                    "operator": "add",
                    "operands": ["1.25", "2.75"],
                    "precision": 28
                }
            }
        }
    }
    try:
        resp = requests.post(f"{BASE_URL}/mcp", json=payload)
        resp.raise_for_status()
        data = resp.json()
        result = data.get("result", {})
        # The README says result is {"operation":"arithmetic","result":"4.0"}
        # But wait, the MCP response format wraps it in 'result'.
        # Response example in README:
        # {
        #   "jsonrpc": "2.0",
        #   "id": "req-1",
        #   "result": {"operation":"arithmetic","result":"4.0"}
        # }
        
        inner_result = result
        assert inner_result.get("operation") == "arithmetic"
        assert inner_result.get("result") == "4.0"
        print("OK")
    except Exception as e:
        print(f"FAIL: {e}")
        print(f"Response: {resp.text if 'resp' in locals() else 'None'}")
        sys.exit(1)

def test_statistics():
    print("Testing /v1/compute (statistics)...", end=" ")
    payload = {
        "operation": "statistics",
        "params": {
            "function": "mean",
            "values": ["1", "2", "3", "4"],
            "sample": False,
            "precision": 28
        }
    }
    try:
        resp = requests.post(f"{BASE_URL}/v1/compute", json=payload)
        resp.raise_for_status()
        data = resp.json()
        assert data.get("operation") == "statistics"
        assert data.get("result") == "2.5"
        print("OK")
    except Exception as e:
        print(f"FAIL: {e}")
        print(f"Response: {resp.text if 'resp' in locals() else 'None'}")
        sys.exit(1)

def test_unit_convert():
    print("Testing /v1/compute (unit convert)...", end=" ")
    payload = {
        "operation": "unit",
        "params": {
            "action": "convert",
            "value": "1500",
            "unit": "m",
            "to_unit": "km",
            "precision": 28
        }
    }
    try:
        resp = requests.post(f"{BASE_URL}/v1/compute", json=payload)
        resp.raise_for_status()
        data = resp.json()
        assert data.get("operation") == "unit"
        assert data.get("result") == "1.5"
        assert data.get("unit") == "km"
        print("OK")
    except Exception as e:
        print(f"FAIL: {e}")
        print(f"Response: {resp.text if 'resp' in locals() else 'None'}")
        sys.exit(1)

if __name__ == "__main__":
    test_health()
    test_arithmetic_mcp()
    test_statistics()
    test_unit_convert()
    print("All tests passed.")
