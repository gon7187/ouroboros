#!/usr/bin/env python3
"""End-to-end test: verify routing works with actual API calls."""

import asyncio
import sys
import os
sys.path.insert(0, '..')

from ouroboros.llm import LLMClient

async def test_zai_routing():
    """Test that Z.ai models route correctly and make actual API calls."""
    
    print("=== Z.ai End-to-End Routing Test ===\n")
    
    # Initialize client
    client = LLMClient()
    
    # Verify providers are loaded
    print("Loaded providers:")
    for provider_id in client._providers.keys():
        print(f"  ✅ {provider_id}")
    
    print("\nTesting routing for Z.ai models:")
    
    test_models = [
        ("glm-4.7", "zai"),
        ("glm-4.7-flash", "zai"),
    ]
    
    results = []
    for model, expected_provider in test_models:
        print(f"\n--- Testing {model} ---")
        
        # Test routing
        provider = client.get_provider_for_model(model)
        print(f"Routing: {model} → {provider} (expected: {expected_provider})")
        
        if provider != expected_provider:
            print(f"❌ FAILED: Wrong provider!")
            results.append(False)
            continue
        
        # Test actual API call
        try:
            print(f"Making API call to {model}...")
            response = await client.chat(
                messages=[{"role": "user", "content": "Say 'Hello from Z.ai!'"}],
                model=model,
                max_tokens=50
            )
            
            content = response.choices[0].message.content
            print(f"Response: {content}")
            print(f"✅ SUCCESS: Routing and API call both work!")
            results.append(True)
            
        except Exception as e:
            print(f"❌ FAILED: API call error: {e}")
            results.append(False)
    
    print("\n=== Summary ===")
    print(f"Passed: {sum(results)}/{len(results)}")
    print(f"Failed: {len(results) - sum(results)}/{len(results)}")
    
    return all(results)

if __name__ == "__main__":
    success = asyncio.run(test_zai_routing())
    sys.exit(0 if success else 1)
