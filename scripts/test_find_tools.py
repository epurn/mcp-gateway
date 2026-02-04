"""Test find_tools meta-tool implementation."""

import requests
import json

# JWT token
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkZXZlbG9wZXIiLCJyb2xlcyI6WyJkZXZlbG9wZXIiXSwiYWxsb3dlZF90b29scyI6WyIqIl0sImV4cCI6MTgwMTc1ODMyMSwiaWF0IjoxNzcwMjIyMzIxfQ.fewNla9MQSy8ijjAfrvLplgx3XukRqKm-tbHSdRwak4"

print("=" * 60)
print("Testing find_tools Meta-Tool")
print("=" * 60)

# Test 1: List tools (should return minimal set)
print("\n1️⃣  Testing tools/list (should return core + find_tools)...")
response = requests.post(
    "http://localhost:8000/sse",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {}
    }
)

if response.status_code == 200:
    data = response.json()
    tools = data.get("result", {}).get("tools", [])
    print(f"✅ Received {len(tools)} tools:")
    for tool in tools:
        print(f"   - {tool['name']}")
    
    # Check if find_tools is present
    if any(t['name'] == 'find_tools' for t in tools):
        print("\n✅ find_tools is in the list!")
    else:
        print("\n❌ find_tools is NOT in the list!")
else:
    print(f"❌ Error: {response.status_code}")
    print(response.text)

# Test 2: Call find_tools
print("\n2️⃣  Testing find_tools('generate PDF')...")
response = requests.post(
    "http://localhost:8000/sse",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "find_tools",
            "arguments": {
                "query": "generate PDF document"
            }
        }
    }
)

if response.status_code == 200:
    data = response.json()
    result = data.get("result", {})
    content = result.get("content", [{}])[0].get("text", "")
    
    try:
        result_data = json.loads(content)
        print(f"✅ Found {result_data.get('found', 0)} tools:")
        for tool in result_data.get('tools', []):
            print(f"   - {tool['name']}: {tool['description'][:60]}...")
        
        # Check if document_generate is found
        if any(t['name'] == 'document_generate' for t in result_data.get('tools', [])):
            print("\n✅ document_generate was discovered!")
        else:
            print("\n⚠️  document_generate was NOT found")
    except json.JSONDecodeError:
        print(f"❌ Could not parse result: {content}")
else:
    print(f"❌ Error: {response.status_code}")
    print(response.text)

# Test 3: Call find_tools for math
print("\n3️⃣  Testing find_tools('calculate average')...")
response = requests.post(
    "http://localhost:8000/sse",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "find_tools",
            "arguments": {
                "query": "calculate average of numbers"
            }
        }
    }
)

if response.status_code == 200:
    data = response.json()
    result = data.get("result", {})
    content = result.get("content", [{}])[0].get("text", "")
    
    try:
        result_data = json.loads(content)
        print(f"✅ Found {result_data.get('found', 0)} tools:")
        for tool in result_data.get('tools', []):
            print(f"   - {tool['name']}")
    except json.JSONDecodeError:
        print(f"❌ Could not parse result: {content}")
else:
    print(f"❌ Error: {response.status_code}")
    print(response.text)

print("\n" + "=" * 60)
print("✅ Test complete!")
print("=" * 60)
