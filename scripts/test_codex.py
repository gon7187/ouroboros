#!/usr/bin/env python3
"""
Test script for Codex backend API.

This script tests whether the Codex backend API is working with OAuth tokens.
"""

import sys
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ouroboros.auth.token_loader import load_openai_oauth_with_account_id
from ouroboros.auth.codex_client import create_codex_client

# Set up logging
logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)


def main():
    """Test Codex backend API."""
    print("=== Testing Codex Backend API ===\n")

    # Load OAuth token
    print("1. Loading OAuth token...")
    result = load_openai_oauth_with_account_id()

    if not result:
        print("❌ Failed to load OAuth token from auth.json")
        return 1

    access_token, account_id = result
    print(f"✅ OAuth token loaded (length: {len(access_token)} chars)")
    if account_id:
        print(f"✅ Account ID: {account_id}")
    else:
        print("⚠️  Account ID not found, will extract from JWT")

    # Create Codex client
    print("\n2. Creating Codex client...")
    try:
        client = create_codex_client(access_token, account_id)
        print("✅ Codex client created")
    except Exception as e:
        print(f"❌ Failed to create Codex client: {e}")
        return 1

    # Make a test request
    print("\n3. Making test request...")
    messages = [
        {"role": "user", "content": "Hello! Can you write a Python function to calculate the factorial of a number?"}
    ]

    try:
        response = client.chat(messages=messages, model="gpt-5.3-codex")

        print("✅ Request successful!")
        print(f"\nResponse content:\n{response['content']}")
        print(f"\nUsage: {response.get('usage', {})}")

    except Exception as e:
        print(f"❌ Request failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        client.close()

    print("\n=== Test Complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
