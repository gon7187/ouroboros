#!/usr/bin/env python3
"""Test LLM multi-provider routing logic."""

import sys
sys.path.insert(0, '/home/test/.openclaw/workspace/ouroboros')

from ouroboros.llm import LLMClient


def test_routing():
    """Test that models route to correct providers."""
    client = LLMClient()
    
    # Test Z.ai models
    assert client.get_provider_for_model("glm-4.7") == "zai", "glm-4.7 should route to zai"
    assert client.get_provider_for_model("glm-4.7-flash") == "zai", "glm-4.7-flash should route to zai"
    assert client.get_provider_for_model("glm-5") == "zai", "glm-5 should route to zai"
    
    # Test OpenAI models (will fail gracefully if provider missing)
    provider = client.get_provider_for_model("gpt-4")
    assert provider in ["openai", "zai"], f"gpt-4 should route to openai or fall back to available provider, got {provider}"
    
    # Test OpenCode models
    provider = client.get_provider_for_model("opencode/claude-opus-4-6")
    assert provider in ["opencode", "zai"], f"opencode models should route to opencode or fall back, got {provider}"
    
    print("✅ All routing tests passed!")


if __name__ == "__main__":
    test_routing()
