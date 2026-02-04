import requests
import json
import base64

# Test request (InvokeToolRequest schema)
payload = {
    "tool_name": "document_generate",
    "arguments": {
        "content": "# Test Document\n\nThis is a **test** document with:\n\n- Bullet points\n- *Italic text*\n- **Bold text**\n\n## Section 2\n\nSome paragraph text.",
        "format": "pdf",
        "title": "Test PDF"
    }
}

# Send request via Gateway
# Note: gateway container port is 8000
response = requests.post(
    "http://localhost:8000/mcp/invoke",
    json=payload,
    headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkZXZlbG9wZXIiLCJyb2xlcyI6WyJkZXZlbG9wZXIiXSwiYWxsb3dlZF90b29scyI6WyIqIl0sImV4cCI6MTgwMTc1ODMyMSwiaWF0IjoxNzcwMjIyMzIxfQ.fewNla9MQSy8ijjAfrvLplgx3XukRqKm-tbHSdRwak4"}
)

print(f"Status: {response.status_code}")
try:
    data = response.json()
    # Print full response for debugging
    print(f"Response: {json.dumps(data, indent=2)}")
    
    # If successful, save the PDF
    if response.status_code == 200:
        if "result" in data and data["result"] is not None:
            if "content" in data["result"]:
                pdf_data = base64.b64decode(data["result"]["content"])
                with open("test_output.pdf", "wb") as f:
                    f.write(pdf_data)
                print("\n✓ PDF saved to test_output.pdf")
        elif "error" in data:
            print(f"\n❌ Error: {data['error']['message']}")
            if 'data' in data['error'] and data['error']['data']:
                print(f"Error Data: {data['error']['data']}")
except Exception as e:
    print(f"Failed to parse response: {e}")
    print(f"Raw response: {response.text}")
