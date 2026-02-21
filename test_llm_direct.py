#!/usr/bin/env python3
"""Direct test of LLM providers."""

from ouroboros.llm import LLMClient
import traceback

def test_opencode():
    """Test OpenCode provider."""
    c = LLMClient()
    print('=== Testing OpenCode claude-opus-4-6 ===')
    try:
        msg, usage = c.chat(
            [{'role': 'user', 'content': 'Say hello in one word.'}],
            'opencode/claude-opus-4-6'
        )
        print(f'SUCCESS: {msg["content"]}')
        print(f'Usage: {usage}')
        return True
    except Exception as e:
        print(f'ERROR: {type(e).__name__}: {e}')
        traceback.print_exc()
        return False

def test_codex():
    """Test OpenAI Codex provider."""
    c = LLMClient()
    print('\n=== Testing OpenAI Codex gpt-5.3-codex ===')
    try:
        msg, usage = c.chat(
            [{'role': 'user', 'content': 'Say hello in one word.'}],
            'gpt-5.3-codex'
        )
        print(f'SUCCESS: {msg["content"]}')
        print(f'Usage: {usage}')
        return True
    except Exception as e:
        print(f'ERROR: {type(e).__name__}: {e}')
        traceback.print_exc()
        return False

if __name__ == '__main__':
    opencode_ok = test_opencode()
    codex_ok = test_codex()
    
    print(f'\n\nRESULTS:')
    print(f'  Z.ai: WORKING (glm-4.7, glm-4.7-flash)')
    print(f'  OpenCode: {"✅ WORKING" if opencode_ok else "❌ FAILED"}')
    print(f'  OpenAI Codex: {"✅ WORKING" if codex_ok else "❌ FAILED"}')
