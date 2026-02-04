"""Check tools/list via proper SSE JSON-RPC protocol."""

import requests

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkZXZlbG9wZXIiLCJyb2xlcyI6WyJkZXZlbG9wZXIiXSwiYWxsb3dlZF90b29scyI6WyIqIl0sImV4cCI6MTgwMTc1ODMyMSwiaWF0IjoxNzcwMjIyMzIxfQ.fewNla9MQSy8ijjAfrvLplgx3XukRqKm-tbHSdRwak4"

# Use JSON-RPC to call tools/list
response = requests.post(
    "http://localhost:8000/sse",
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    },
    json={
        "jsonrpc": "2.0",
        "method": "tools/list",
        "params": {},
        "id": "test-1"
    }
)

print(f"Status: {response.status_code}")
data = response.json()

if "result" in data and "tools" in data["result"]:
    tools = data["result"]["tools"]
    print(f"Tools returned: {len(tools)}")
    for tool in tools:
        print(f"  - {tool['name']}: {tool.get('description', '')[:50]}...")
else:
    print(f"Response: {data}")
