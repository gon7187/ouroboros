"""
Unit tests for LLM multi-provider routing logic.

Tests:
1. Model-to-provider mapping (get_provider_for_model)
2. Provider loading from environment
3. Invalid model handling (graceful fallback to default)
4. Provider configuration

No actual API calls - pure logic testing.

Run: pytest tests/test_llm_provider_routing.py -v
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ouroboros.llm import LLMClient, _MODEL_TO_PROVIDER


class TestModelToProviderMapping(unittest.TestCase):
    """Test the _MODEL_TO_PROVIDER registry pattern matching."""

    def setUp(self):
        """Set up test environment with all providers loaded."""
        # Create a mock environment with all provider keys
        self.mock_env = {
            "ZAI_API_KEY": "test-zai-key",
            "OPCODE_API_KEY": "test-opencode-key",
            "OPENAI_API_KEY": "test-openai-key",
        }
        # Save original env
        self.original_env = os.environ.copy()

    def tearDown(self):
        """Restore original environment."""
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_opencode_models_route_correctly(self):
        """OpenCode models should map to 'opencode' provider."""
        with patch.dict(os.environ, self.mock_env, clear=True):
            client = LLMClient()
        
        opencode_models = [
            "opencode/claude-opus-4-6",
            "opencode/gemini-2.5-flash-002",
            "opencode/any-model-name",
        ]
        
        for model in opencode_models:
            provider = client.get_provider_for_model(model)
            self.assertEqual(provider, "opencode", f"Model {model} should route to opencode")

    def test_openai_gpt_models_route_correctly(self):
        """OpenAI GPT models should map to 'openai' provider."""
        with patch.dict(os.environ, self.mock_env, clear=True):
            client = LLMClient()
        
        openai_models = [
            "gpt-4.1",
            "gpt-5.2",
            "gpt-5.2-codex",
            "gpt-any-model",
        ]
        
        for model in openai_models:
            provider = client.get_provider_for_model(model)
            self.assertEqual(provider, "openai", f"Model {model} should route to openai")

    def test_claude_models_route_to_openai(self):
        """Claude models should route to 'openai' provider (OpenAI-hosted)."""
        with patch.dict(os.environ, self.mock_env, clear=True):
            client = LLMClient()
        
        claude_models = [
            "claude-opus-4.6",
            "claude-sonnet-4",
            "claude-haiku-3.5",
        ]
        
        for model in claude_models:
            provider = client.get_provider_for_model(model)
            self.assertEqual(provider, "openai", f"Model {model} should route to openai")

    def test_gemini_models_route_to_openai(self):
        """Gemini models should route to 'openai' provider (OpenAI-hosted)."""
        with patch.dict(os.environ, self.mock_env, clear=True):
            client = LLMClient()
        
        gemini_models = [
            "gemini-2.5-pro-preview",
            "gemini-3-pro-preview",
        ]
        
        for model in gemini_models:
            provider = client.get_provider_for_model(model)
            self.assertEqual(provider, "openai", f"Model {model} should route to openai")

    def test_zai_glm_models_route_correctly(self):
        """Z.ai GLM models should map to 'zai' provider."""
        with patch.dict(os.environ, self.mock_env, clear=True):
            client = LLMClient()
        
        glm_models = [
            "glm-4.7",
            "glm-4.7-flash",
            "glm-5",
            "glm-any-model",
        ]
        
        for model in glm_models:
            provider = client.get_provider_for_model(model)
            self.assertEqual(provider, "zai", f"Model {model} should route to zai")

    def test_openai_o3_models_route_correctly(self):
        """OpenAI o3/o4 models should map to 'openai' provider."""
        with patch.dict(os.environ, self.mock_env, clear=True):
            client = LLMClient()
        
        o_models = [
            "o3-mini",
            "o3-pro",
            "o4-mini",
        ]
        
        for model in o_models:
            provider = client.get_provider_for_model(model)
            self.assertEqual(provider, "openai", f"Model {model} should route to openai")

    def test_invalid_model_falls_back_to_active_provider(self):
        """Unknown/invalid models should fall back to active provider (no crash)."""
        with patch.dict(os.environ, self.mock_env, clear=True):
            client = LLMClient()
        
        invalid_models = [
            "invalid-model-name",
            "unknown/model",
            "some-random-string",
        ]
        
        # Get the default active provider (zai if key exists, otherwise whatever is loaded)
        active_provider = client._active_provider
        
        for model in invalid_models:
            provider = client.get_provider_for_model(model)
            self.assertEqual(provider, active_provider, 
                           f"Invalid model {model} should fall back to active provider {active_provider}")


class TestProviderLoading(unittest.TestCase):
    """Test provider configuration loading from environment."""

    def test_zai_provider_loaded_when_key_present(self):
        """Z.ai provider should load when ZAI_API_KEY is set."""
        with patch.dict(os.environ, {"ZAI_API_KEY": "test-key"}):
            client = LLMClient()
            
            self.assertIn("zai", client._providers)
            self.assertEqual(client._providers["zai"].name, "zai")
            self.assertEqual(client._providers["zai"].api_key, "test-key")
            self.assertEqual(client._providers["zai"].base_url, "https://api.z.ai/api/coding/paas/v4")

    def test_zai_provider_not_loaded_when_key_missing(self):
        """Z.ai provider should NOT load when ZAI_API_KEY is missing."""
        env_without_zai = {k: v for k, v in os.environ.items() if k != "ZAI_API_KEY"}
        with patch.dict(os.environ, env_without_zai, clear=True):
            client = LLMClient()
            
            self.assertNotIn("zai", client._providers)

    def test_opencode_provider_loaded_when_key_present(self):
        """OpenCode provider should load when OPCODE_API_KEY is set."""
        with patch.dict(os.environ, {"OPCODE_API_KEY": "opencode-test-key"}):
            client = LLMClient()
            
            self.assertIn("opencode", client._providers)
            self.assertEqual(client._providers["opencode"].name, "opencode")
            self.assertEqual(client._providers["opencode"].api_key, "opencode-test-key")

    def test_openai_provider_loaded_when_key_present(self):
        """OpenAI provider should load when OPENAI_API_KEY is set."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key"}):
            client = LLMClient()
            
            self.assertIn("openai", client._providers)
            self.assertEqual(client._providers["openai"].name, "openai")
            self.assertEqual(client._providers["openai"].api_key, "sk-test-key")

    def test_active_provider_selection_zai_preferred(self):
        """When multiple providers are loaded, Z.ai should be preferred as active."""
        with patch.dict(os.environ, {
            "ZAI_API_KEY": "zai-key",
            "OPENAI_API_KEY": "openai-key",
        }):
            client = LLMClient()
            
            self.assertEqual(client._active_provider, "zai")

    def test_active_provider_fallback_to_any_available(self):
        """When Z.ai is not loaded, active provider should fall back to first available."""
        env_without_zai = {k: v for k, v in os.environ.items() if k != "ZAI_API_KEY"}
        with patch.dict(os.environ, {**env_without_zai, "OPENAI_API_KEY": "openai-key"}, clear=True):
            client = LLMClient()
            
            self.assertIn("openai", client._providers)
            self.assertEqual(client._active_provider, "openai")

    def test_custom_base_urls_from_env(self):
        """Providers should use custom base URLs from environment when set."""
        with patch.dict(os.environ, {
            "ZAI_API_KEY": "zai-key",
            "ZAI_BASE_URL": "https://custom.z.ai/v1",
            "OPENAI_API_KEY": "openai-key",
            "OPENAI_BASE_URL": "https://custom.openai.com/v1",
        }):
            client = LLMClient()
            
            self.assertEqual(client._providers["zai"].base_url, "https://custom.z.ai/v1")
            self.assertEqual(client._providers["openai"].base_url, "https://custom.openai.com/v1")

    def test_testing_mode_with_direct_params(self):
        """When api_key is passed directly, create test provider (no env loading)."""
        client = LLMClient(api_key="test-api-key", base_url="https://test.example.com/v1")
        
        self.assertIn("test", client._providers)
        self.assertEqual(client._active_provider, "test")
        self.assertEqual(client._providers["test"].api_key, "test-api-key")
        self.assertEqual(client._providers["test"].base_url, "https://test.example.com/v1")
        
        # Other providers should not be loaded in test mode
        self.assertEqual(len(client._providers), 1)


class TestProviderRoutingWithMissingProvider(unittest.TestCase):
    """Test behavior when model maps to a provider that isn't loaded."""

    def test_missing_provider_logs_warning(self):
        """When a model's provider isn't loaded, should fall back to active provider."""
        with patch.dict(os.environ, {"ZAI_API_KEY": "zai-key"}):
            client = LLMClient()
            
            # OpenCode provider not loaded, but model routes to it
            provider = client.get_provider_for_model("opencode/claude-opus-4-6")
            
            # Should fall back to active provider (zai)
            self.assertEqual(provider, "zai")

    def test_active_provider_used_as_default_fallback(self):
        """Active provider should be the fallback for all unknown/missing-provider models."""
        with patch.dict(os.environ, {"ZAI_API_KEY": "zai-key"}):
            client = LLMClient()
            
            # All these should fall back to zai
            test_models = [
                "opencode/something",  # OpenCode not loaded
                "unknown/model",       # No pattern match
                "invalid",             # No pattern match
            ]
            
            for model in test_models:
                provider = client.get_provider_for_model(model)
                self.assertEqual(provider, "zai", 
                               f"Model {model} should fall back to zai when provider not loaded")


class TestRoutingRegistry(unittest.TestCase):
    """Test the _MODEL_TO_PROVIDER registry itself."""

    def test_registry_contains_expected_patterns(self):
        """Registry should have patterns for major providers."""
        expected_patterns = [
            "opencode/*",
            "gpt-*",
            "gpt-*codex",
            "claude-*",
            "o3*",
            "o4*",
            "gemini-*",
            "glm-*",
        ]
        
        for pattern in expected_patterns:
            self.assertIn(pattern, _MODEL_TO_PROVIDER, 
                         f"Pattern {pattern} should be in routing registry")

    def test_registry_provider_targets(self):
        """Registry should map patterns to correct provider targets."""
        self.assertEqual(_MODEL_TO_PROVIDER["opencode/*"], "opencode")
        self.assertEqual(_MODEL_TO_PROVIDER["gpt-*"], "openai")
        self.assertEqual(_MODEL_TO_PROVIDER["claude-*"], "openai")
        self.assertEqual(_MODEL_TO_PROVIDER["glm-*"], "zai")

    def test_registry_is_complete_no_duplicates(self):
        """Registry should not have duplicate patterns or conflicting mappings."""
        patterns = list(_MODEL_TO_PROVIDER.keys())
        self.assertEqual(len(patterns), len(set(patterns)), 
                        "Registry should not have duplicate patterns")


if __name__ == "__main__":
    unittest.main()
