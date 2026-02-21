#!/usr/bin/env python3
"""Test LLM providers systematically."""

from ouroboros.llm import LLMClient
import time

def test_provider(client, model_name, provider_name):
    """Test a single provider/model combination."""
    print(f"\n{'='*60}")
    print(f"Testing {provider_name}: {model_name}")
    print('='*60)
    
    try:
        start = time.time()
        msg, usage = client.chat(
            [{'role': 'user', 'content': 'Say hello in one word.'}],
            model_name
        )
        elapsed = time.time() - start
        
        print(f"✅ SUCCESS")
        print(f"Response: {msg['content']}")
        print(f"Usage: {usage}")
        print(f"Time: {elapsed:.1f}s")
        return True
    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}")
        print(f"Message: {e}")
        return False

def main():
    client = LLMClient()
    
    results = {}
    
    # Test Z.ai models
    print("\n" + "="*60)
    print("Z.AI PROVIDER TESTS")
    print("="*60)
    
    for model in ['glm-4.7', 'glm-4.7-flash', 'glm-5', 'glm-4.7-flashx']:
        success = test_provider(client, model, 'Z.ai')
        results[f'zai/{model}'] = success
    
    # Test OpenCode models
    print("\n" + "="*60)
    print("OPencode PROVIDER TESTS")
    print("="*60)
    
    for model in ['opencode/claude-opus-4-6', 'opencode/kimi-k2.5-free']:
        success = test_provider(client, model, 'OpenCode')
        results[f'opencode/{model}'] = success
    
    # Test OpenAI Codex
    print("\n" + "="*60)
    print("OPENAI CODEX PROVIDER TESTS")
    print("="*60)
    
    for model in ['gpt-5.3-codex']:
        success = test_provider(client, model, 'OpenAI Codex')
        results[f'codex/{model}'] = success
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    working = [k for k, v in results.items() if v]
    failed = [k for k, v in results.items() if not v]
    
    print(f"\n✅ Working ({len(working)}):")
    for m in working:
        print(f"  - {m}")
    
    print(f"\n❌ Failed ({len(failed)}):")
    for m in failed:
        print(f"  - {m}")
    
    return results

if __name__ == '__main__':
    main()
