#!/usr/bin/env python3
"""Test OpenCode provider API connectivity and format"""

import json
import sys
import os

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# API Key (from clawbot config)
OPENCODE_API_KEY = "sk-kKxq8nwze33meTFd982shUdJ8sNdozU5aIP2F4RidtcDeGsAMVBiqXWFsklf0ZJO"

# Try common base URLs for OpenAI-style APIs
POSSIBLE_BASE_URLS = [
    "https://api.opencode.ai/v1",
    "https://api.opencode.com/v1", 
    "https://opencode.ai/api/v1",
    "https://opencode.com/api/v1",
]

# Headers
HEADERS = {
    "Authorization": f"Bearer {OPENCODE_API_KEY}",
    "Content-Type": "application/json"
}

def test_url(base_url, url_suffix="/chat/completions"):
    """Test a single URL endpoint"""
    try:
        import urllib.request
        import urllib.error
        
        full_url = base_url + url_suffix
        
        # Try a simple list models request first
        list_url = base_url + "/models"
        
        req = urllib.request.Request(list_url, headers=HEADERS, method="GET")
        
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                print(f"✅ {list_url} - Status: {response.status}")
                data = json.loads(response.read().decode())
                print(f"   Response: {json.dumps(data, indent=2)[:200]}...")
                return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(f"❌ {list_url} - Not found (404)")
            elif e.code == 401:
                print(f"❌ {list_url} - Unauthorized (401)")
            else:
                print(f"❌ {list_url} - Error: {e.code} {e.reason}")
            return False
        except Exception as e:
            print(f"❌ {list_url} - {type(e).__name__}: {e}")
            return False
            
    except Exception as e:
        print(f"❌ Failed to test {base_url}: {e}")
        return False

def main():
    print("=" * 60)
    print("Testing OpenCode API - Endpoint Discovery")
    print("=" * 60)
    print(f"API Key: {OPENCODE_API_KEY[:20]}... (length: {len(OPENCODE_API_KEY)})")
    print()
    
    results = []
    for base_url in POSSIBLE_BASE_URLS:
        print(f"\nTesting: {base_url}")
        result = test_url(base_url)
        results.append((base_url, result))
    
    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)
    for url, success in results:
        status = "✅ WORKING" if success else "❌ FAILED"
        print(f"{status}: {url}")
    
    # If any URL worked, return success
    if any(success for _, success in results):
        print("\n✅ Found working endpoint!")
        return 0
    else:
        print("\n❌ No working endpoints found. OpenCode may use different API format.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
