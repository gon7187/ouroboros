#!/usr/bin/env python3
"""
Test OpenCode LLM provider with simple query.
"""
import requests
import json
import os
import sys

# OpenCode credentials
OPENCODE_API_KEY = os.environ.get('OPENCODE_API_KEY', 'sk-kKxq8nwze33meTFd982shUdJ8sNdozU5aIP2F4RidtcDeGsAMVBiqXWFsklf0ZJO')
OPENCODE_BASE_URL = os.environ.get('OPENCODE_BASE_URL', 'https://api.opencode.ai/v1')

print(f"Testing OpenCode API...")
print(f"Base URL: {OPENCODE_BASE_URL}")
print(f"API Key: {OPENCODE_API_KEY[:20]}...")
print()

# Try simple chat completion request
headers = {
    'Content-Type': 'application/json',
    'Authorization': f'Bearer {OPENCODE_API_KEY}'
}

# Try with different model names (common patterns)
models_to_test = [
    'gpt-4',
    'gpt-3.5-turbo',
    'claude-3-sonnet',
    'llama-3-70b',
    'model'
]

payload = {
    'messages': [
        {'role': 'user', 'content': 'Hello! Please respond with "OpenCode test successful"'}
    ],
    'max_tokens': 50
}

for model in models_to_test:
    print(f"Trying model: {model}")
    
    try:
        response = requests.post(
            f"{OPENCODE_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=10
        )
        
        print(f"  Status: {response.status_code}")
        
        if response.status_code == 200:
            print(f"  ✅ SUCCESS!")
            data = response.json()
            print(f"  Response: {json.dumps(data, indent=2)[:500]}...")
            sys.exit(0)  # Exit on first success
        else:
            print(f"  Response: {response.text[:200]}...")
            
    except Exception as e:
        print(f"  Error: {e}")
    
    print()

print("All models failed. Trying to list available models...")

# Try to list models
try:
    response = requests.get(
        f"{OPENCODE_BASE_URL}/models",
        headers=headers,
        timeout=10
    )
    
    print(f"Models endpoint status: {response.status_code}")
    print(f"Response: {response.text[:500]}...")
    
except Exception as e:
    print(f"Models endpoint error: {e}")

print("\nOpenCode test completed.")
