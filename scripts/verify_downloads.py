import requests
import json
import jwt
import datetime

GATEWAY_URL = "http://localhost:8000"
JWT_SECRET = "dev_secret_key_not_for_production"  # Must match .env (default: your-secret-key)
JWT_ALGO = "HS256"

def create_jwt(user_id, roles=["user"]):
    payload = {
        "sub": user_id,
        "roles": roles,
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

def test_secure_download():
    # 1. Create tokens for two users
    token_a = create_jwt("user_a")
    token_b = create_jwt("user_b")

    print(f"Token A (user_a): {token_a}")
    print(f"Token B (user_b): {token_b}")

    # 2. Invoke tool as User A
    print("\n[1] Generating document as User A...")
    response = requests.post(
        f"{GATEWAY_URL}/mcp/invoke",
        headers={"Authorization": f"Bearer {token_a}", "Content-Type": "application/json"},
        json={
            "tool_name": "document_generate",
            "arguments": {
                "content": "# Hello User A\nThis is a private doc.",
                "format": "pdf",
                "title": "User A Doc"
            }
        }
    )

    if response.status_code != 200:
        print(f"Failed to call tool: {response.text}")
        return

    result = response.json()
    # print(f"Tool Result: {json.dumps(result, indent=2)}")
    print("Tool invoked successfully.")
    
    # Extract download URL
    # format: {"jsonrpc": "2.0", "result": {...}, "id": ...}
    if result.get("error"):
        print(f"Error from tool: {result['error']}")
        return

    tool_output = result.get("result", {})
    if not tool_output:
        print(f"Error: No result in response: {result}")
        return

    download_url = tool_output.get("download_url")
    filename = tool_output.get("filename")
    
    if not download_url:
        print("Error: No download URL found in response")
        return

    print(f"\nDownload URL: {download_url}")

    # 3. Try to download as User A (Should Succeed)
    print("\n[2] Downloading as User A (Owner)...")
    resp_a = requests.get(download_url, headers={"Authorization": f"Bearer {token_a}"})
    if resp_a.status_code == 200:
        print("SUCCESS: User A downloaded the file.")
        print(f"File size: {len(resp_a.content)} bytes")
    else:
        print(f"FAILURE: User A could not download file. Status: {resp_a.status_code}")
        print(resp_a.text)

    # 4. Try to download as User B (Should Fail)
    print("\n[3] Downloading as User B (Attacker)...")
    resp_b = requests.get(download_url, headers={"Authorization": f"Bearer {token_b}"})
    if resp_b.status_code == 403:
        print("SUCCESS: User B was denied access (403 Forbidden).")
    else:
        print(f"FAILURE: User B got unexpected status: {resp_b.status_code}")
        print(resp_b.text)

    # 5. Try to download without token (Should Fail)
    print("\n[4] Downloading without token...")
    resp_anon = requests.get(download_url)
    if resp_anon.status_code == 401:
        print("SUCCESS: Anonymous request was denied (401 Unauthorized).")
    else:
        print(f"FAILURE: Anonymous request got unexpected status: {resp_anon.status_code}")

if __name__ == "__main__":
    try:
        test_secure_download()
    except Exception as e:
        print(f"Test failed with exception: {e}")
