#!/usr/bin/env python3
"""Test CodexBackendClient with real API call."""

import sys
sys.path.insert(0, '/home/test/.openclaw/workspace/ouroboros')

from ouroboros.auth.token_loader import load_openai_oauth_with_account_id
from ouroboros.auth.codex_client import CodexBackendClient

def main():
    # Load token
    creds = load_openai_oauth_with_account_id()
    if not creds:
        print("ERROR: No token found")
        return
    
    access_token, account_id = creds
    print(f"Token: {access_token[:50]}...")
    print(f"Account ID: {account_id}")
    
    # Create client
    client = CodexBackendClient(access_token, account_id)
    
    # Test simple request
    print("\nSending test request...")
    try:
        response = client.chat(
            model="gpt-5.3-codex",
            messages=[{"role": "user", "content": "Say 'Hello from Codex API!'"}],
            stream=True
        )
        
        print(f"\nResponse type: {type(response)}")
        
        if hasattr(response, 'status_code'):
            print(f"Response status: {response.status_code}")
            print(f"Headers: {dict(response.headers)}")
            print("\nContent:")
            for chunk in response.iter_content(chunk_size=100):
                print(chunk.decode('utf-8', errors='ignore'), end='')
        else:
            print(f"Response: {response}")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
