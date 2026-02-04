"""Test call_tool meta-tool to invoke exact_calculate."""

import requests

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkZXZlbG9wZXIiLCJyb2xlcyI6WyJkZXZlbG9wZXIiXSwiYWxsb3dlZF90b29scyI6WyIqIl0sImV4cCI6MTgwMTc1ODMyMSwiaWF0IjoxNzcwMjIyMzIxfQ.fewNla9MQSy8ijjAfrvLplgx3XukRqKm-tbHSdRwak4"

# Convert 1100 sq ft to sq m using call_tool
# 1 sq ft = 0.09290304 sq m
response = requests.post(
    "http://localhost:8000/sse",
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    },
    json={
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "call_tool",
            "arguments": {
                "name": "exact_calculate",
                "arguments": {
                    "operator": "mul",
                    "operands": ["1100", "0.09290304"],
                    "precision": 10
                }
            }
        },
        "id": "test-1"
    }
)

print(f"Status: {response.status_code}")
data = response.json()

if "result" in data:
    result = data["result"]
    if "content" in result:
        for item in result["content"]:
            if item.get("type") == "text":
                print(f"\n✅ Result: {item['text']}")
    else:
        print(f"Result: {result}")
else:
    print(f"Error: {data}")

print("\n📐 1100 sq ft = 102.19334 sq m")
