#!/usr/bin/env python3
"""
Test OpenCode LLM provider - examine raw response format.
"""
import requests
import os
import sys

# OpenCode credentials
OPENCODE_API_KEY = os.environ.get('OPENCODE_API_KEY', 'sk-kKxq8nwze33meTFd982shUdJ8sNdozU5aIP2F4RidtcDeGsAMVBiqXWFsklf0ZJO')
OPENCODE_BASE_URL = os.environ.get('OPENCODE_BASE_URL', 'https://api.opencode.ai/v1')

print(f"Testing OpenCode API - Raw Response")
print(f"Base URL: {OPENCODE_BASE_URL}")
print()

# Try simple chat completion request
headers = {
    'Content-Type': 'application/json',
    'Authorization': f'Bearer {OPENCODE_API_KEY}'
}

payload = {
    'messages': [
        {'role': 'user', 'content': 'Hello! Please respond with "OpenCode test successful"'}
    ],
    'max_tokens': 50,
    'model': 'gpt-3.5-turbo'
}

print(f"Request payload: {payload}")
print()

try:
    response = requests.post(
        f"{OPENCODE_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        timeout=10
    )
    
    print(f"Status: {response.status_code}")
    print(f"Headers: {dict(response.headers)}")
    print()
    print(f"Raw Response:")
    print("-" * 50)
    print(response.text)
    print("-" * 50)
    print()
    
    # Try to parse as JSON
    try:
        data = response.json()
        print(f"Parsed JSON: {data}")
    except:
        print(f"Cannot parse as JSON - might be plain text or different format")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
