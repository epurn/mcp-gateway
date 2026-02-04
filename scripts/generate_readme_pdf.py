"""Generate PDF of README.md using document_generate tool."""

import requests
import base64
from pathlib import Path

# JWT token
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkZXZlbG9wZXIiLCJyb2xlcyI6WyJkZXZlbG9wZXIiXSwiYWxsb3dlZF90b29scyI6WyIqIl0sImV4cCI6MTgwMTc1ODMyMSwiaWF0IjoxNzcwMjIyMzIxfQ.fewNla9MQSy8ijjAfrvLplgx3XukRqKm-tbHSdRwak4"

# Read README.md
readme_path = Path(__file__).parent.parent / "README.md"
content = readme_path.read_text(encoding="utf-8")

print("📄 Generating PDF of README.md...")
print(f"   Content length: {len(content)} characters")

# Call document_generate via Gateway
response = requests.post(
    "http://localhost:8000/mcp/invoke",
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    },
    json={
        "tool_name": "document_generate",
        "arguments": {
            "content": content,
            "format": "pdf",
            "title": "MCP Gateway Documentation"
        }
    }
)

if response.status_code == 200:
    data = response.json()
    
    result = data.get("result")
    if result:
        # The document_generator returns 'content' for the base64 data
        pdf_data = result.get("content") or result.get("output")
        if pdf_data:
            # Decode base64 PDF
            pdf_bytes = base64.b64decode(pdf_data)
            output_path = Path(__file__).parent.parent / "README.pdf"
            output_path.write_bytes(pdf_bytes)
            print(f"\n✅ PDF generated successfully!")
            print(f"   Size: {len(pdf_bytes):,} bytes")
            print(f"   Saved to: {output_path}")
        else:
            print(f"\n❌ No content in result:")
            print(result)
    elif "error" in data:
        print(f"\n❌ Error from Gateway:")
        print(f"   {data.get('error')}")
    else:
        print(f"\n❌ Unexpected response format:")
        print(data)
else:
    print(f"\n❌ HTTP Error: {response.status_code}")
    print(response.text)
