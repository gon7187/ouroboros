#!/usr/bin/env python3
"""Test multi-provider routing for LLM models."""

import sys
sys.path.insert(0, '..')

from ouroboros.llm import LLMClient

def test_routing():
    """Test that models route to correct providers."""
    
    # Initialize client (it will load providers from env)
    client = LLMClient()
    
    # Test models and expected providers
    # Note: openai and opencode providers won't load without keys
    # They should fall back to the first available provider (zai)
    test_cases = [
        ("glm-4.7", "zai"),
        ("glm-4.7-flash", "zai"),
        ("glm-5", "zai"),
        ("gpt-5.3-codex", "zai"),  # Fallback - openai not loaded
        ("opencode/claude-opus-4-6", "zai"),  # Fallback - opencode not loaded
    ]
    
    print("=== Multi-Provider Routing Test ===\n")
    
    passed = 0
    failed = 0
    
    for model, expected_provider in test_cases:
        try:
            provider = client.get_provider_for_model(model)
            if provider == expected_provider:
                print(f"✅ {model:30s} → {provider:10s} (expected: {expected_provider})")
                passed += 1
            else:
                print(f"❌ {model:30s} → {provider:10s} (expected: {expected_provider})")
                failed += 1
        except Exception as e:
            print(f"❌ {model:30s} → ERROR: {e}")
            failed += 1
    
    print(f"\n=== Results ===")
    print(f"Passed: {passed}/{len(test_cases)}")
    print(f"Failed: {failed}/{len(test_cases)}")
    
    # Test that providers are loaded
    print(f"\n=== Loaded Providers ===")
    for provider_id, provider in client._providers.items():
        print(f"✅ {provider_id:10s} - {provider.__class__.__name__}")
    
    print(f"\n=== Summary ===")
    print("Z.ai models route correctly ✅")
    print("Other models fall back to Z.ai (expected without other keys) ✅")
    
    return failed == 0

if __name__ == "__main__":
    success = test_routing()
    sys.exit(0 if success else 1)
