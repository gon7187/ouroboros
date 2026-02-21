"""Ouroboros auth module.

Handles authentication for various LLM providers via OAuth.
"""

from .oauth import OAuthClient, OpenAIClient

__all__ = ["OAuthClient", "OpenAIClient"]
