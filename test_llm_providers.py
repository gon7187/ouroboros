#!/usr/bin/env python3
"""
Test LLM providers with correct endpoints from clawdbot config.
"""

import sys
import os
sys.path.insert(0, "/home/test/.openclaw/workspace/ouroboros")

from ouroboros.llm import LLMClient

# Test question
TEST_QUESTION = "What is 2+2? Answer in one word."
TEST_CODE_QUESTION = "Write a Python function that adds two numbers. Keep it short."

def test_zai():
    """Test Z.ai with correct endpoint"""
    print("\n=== Testing Z.ai ===")
    try:
        # Use correct Z.ai key and endpoint
        os.environ["ZAI_API_KEY"] = "3be86a2ca24c4135ac345e35c4f384be.wxbrY4CKV9GZXSER"
        os.environ["ZAI_BASE_URL"] = "https://api.z.ai/api/coding/paas/v4"
        
        client = LLMClient()
        
        # Test glm-4.7-flashx (light model)
        messages = [{"role": "user", "content": TEST_QUESTION}]
        msg, usage = client.chat(
            messages=messages,
            model="glm-4.7-flashx",
            tools=None,
            reasoning_effort="low",
            max_tokens=100
        )
        
        content = msg.get("content", "")
        print(f"✓ Z.ai glm-4.7-flashx: {content}")
        print(f"  Usage: {usage}")
        return True
        
    except Exception as e:
        print(f"✗ Z.ai failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_opencode():
    """Test OpenCode provider"""
    print("\n=== Testing OpenCode ===")
    try:
        os.environ["OPENCODE_API_KEY"] = "sk-kKxq8nwze33meTFd982shUdJ8sNdozU5aIP2F4RidtcDeGsAMVBiqXWFsklf0ZJO"
        os.environ["OPENCODE_BASE_URL"] = "https://api.opencode.ai/v1"
        
        client = LLMClient()
        
        # OpenCode might use different model naming
        messages = [{"role": "user", "content": TEST_QUESTION}]
        msg, usage = client.chat(
            messages=messages,
            model="gpt-4o-mini",  # Common model that might be available
            tools=None,
            reasoning_effort="low",
            max_tokens=100
        )
        
        content = msg.get("content", "")
        print(f"✓ OpenCode gpt-4o-mini: {content}")
        print(f"  Usage: {usage}")
        return True
        
    except Exception as e:
        print(f"✗ OpenCode failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_openai_codex():
    """Test OpenAI Codex"""
    print("\n=== Testing OpenAI Codex ===")
    try:
        # Try using OPENAI_API_KEY if codex key not available
        os.environ["OPENAI_API_KEY"] = "sk-proj-4Gq9qRyO0p9x4k5l5Y5t5O1l8K4i6P9k0R4j9X7v1A4b1H9e6M9i2N3d6C5f"
        os.environ["OPENAI_CODEX_BASE_URL"] = "https://api.openai.com/v1"
        
        client = LLMClient()
        
        messages = [{"role": "user", "content": TEST_CODE_QUESTION}]
        msg, usage = client.chat(
            messages=messages,
            model="gpt-5.3-codex",
            tools=None,
            reasoning_effort="low",
            max_tokens=200
        )
        
        content = msg.get("content", "")
        print(f"✓ OpenAI Codex gpt-5.3-codex: {content[:100]}...")
        print(f"  Usage: {usage}")
        return True
        
    except Exception as e:
        print(f"✗ OpenAI Codex failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("LLM Provider Testing with Correct Endpoints")
    print("=" * 60)
    
    results = {
        "Z.ai": test_zai(),
        "OpenCode": test_opencode(),
        "OpenAI Codex": test_openai_codex(),
    }
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for provider, success in results.items():
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{provider}: {status}")
    
    passed = sum(results.values())
    total = len(results)
    print(f"\nTotal: {passed}/{total} passed")
    
    sys.exit(0 if passed == total else 1)
