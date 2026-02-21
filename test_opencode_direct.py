#!/usr/bin/env python3
"""Direct test of OpenCode API without OpenAI client wrapper."""

import json
import httpx

OPENCODE_KEY = "sk-kKxq8nwze33meTFd982shUdJ8sNdozU5aIP2F4RidtcDeGsAMVBiqXWFsklf0ZJO"

# Try different possible endpoints
ENDPOINTS = [
    "https://api.opencode.com/v1/chat/completions",
    "https://opencode.com/api/v1/chat/completions", 
    "https://api.openai.com/v1/chat/completions",  # Maybe it's a proxy
]

def test_endpoint(endpoint):
    """Test a single endpoint."""
    print(f"\nTesting: {endpoint}")
    
    try:
        headers = {
            "Authorization": f"Bearer {OPENCODE_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "claude-opus-4-6",  # From clawbot config
            "messages": [
                {"role": "user", "content": "Say 'Hello' in one word."}
            ],
            "max_tokens": 10
        }
        
        response = httpx.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=30.0
        )
        
        print(f"  Status: {response.status_code}")
        print(f"  Response: {response.text[:200]}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                if "choices" in data:
                    print(f"  ✓ SUCCESS! Response: {data['choices'][0]['message']['content']}")
                    return endpoint
            except:
                pass
        
        return None
        
    except Exception as e:
        print(f"  ✗ Error: {str(e)[:100]}")
        return None

def test_models_endpoint(endpoint):
    """Test /models endpoint if it exists."""
    print(f"\nTesting models endpoint: {endpoint}")
    
    try:
        headers = {
            "Authorization": f"Bearer {OPENCODE_KEY}",
        }
        
        response = httpx.get(
            endpoint,
            headers=headers,
            timeout=10.0
        )
        
        print(f"  Status: {response.status_code}")
        print(f"  Response: {response.text[:300]}")
        
    except Exception as e:
        print(f"  ✗ Error: {str(e)[:100]}")

if __name__ == "__main__":
    print("=== OpenCode API Discovery ===")
    print(f"Key: {OPENCODE_KEY[:15]}... (len={len(OPENCODE_KEY)})")
    
    # First try models endpoints
    models_endpoints = [
        "https://api.opencode.com/v1/models",
        "https://opencode.com/api/v1/models",
    ]
    
    for endpoint in models_endpoints:
        test_models_endpoint(endpoint)
    
    # Then try chat completions
    for endpoint in ENDPOINTS:
        working = test_endpoint(endpoint)
        if working:
            print(f"\n✅ Found working endpoint: {working}")
            break
    else:
        print("\n❌ No working endpoint found")
