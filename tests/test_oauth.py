"""Tests for OAuth module."""

import pytest
from ouroboros.auth.oauth import (
    generate_code_verifier,
    generate_code_challenge,
    OpenAIClient,
    OAuthConfig,
    OAuthTokens,
    parse_redirect_url,
    PKCEError,
    TokenExchangeError,
)


def test_generate_code_verifier():
    """Test code verifier generation."""
    verifier = generate_code_verifier()
    
    # Should be a string
    assert isinstance(verifier, str)
    
    # Should be in the right length range (43-128 chars after base64)
    assert len(verifier) >= 43
    assert len(verifier) <= 128


def test_generate_code_challenge():
    """Test code challenge generation."""
    verifier = generate_code_verifier()
    challenge = generate_code_challenge(verifier)
    
    # Challenge should be a string
    assert isinstance(challenge, str)
    
    # Challenge should be deterministic
    challenge2 = generate_code_challenge(verifier)
    assert challenge == challenge2


def test_parse_redirect_url():
    """Test redirect URL parsing."""
    url = "http://localhost:3000/callback?code=abc123&state=xyz789&scope=read"
    params = parse_redirect_url(url)
    
    assert params["code"] == "abc123"
    assert params["state"] == "xyz789"
    assert params["scope"] == "read"


def test_oauth_config():
    """Test OAuth configuration."""
    config = OAuthConfig(
        client_id="test_client_id",
        authorization_endpoint="https://example.com/authorize",
        token_endpoint="https://example.com/token",
        redirect_uri="http://localhost:3000/callback",
        scopes=["openid", "profile"],
    )
    
    assert config.client_id == "test_client_id"
    assert config.authorization_endpoint == "https://example.com/authorize"
    assert config.token_endpoint == "https://example.com/token"
    assert config.redirect_uri == "http://localhost:3000/callback"
    assert config.scopes == ["openid", "profile"]


def test_oauth_tokens():
    """Test OAuth tokens dataclass."""
    tokens = OAuthTokens(
        access_token="test_access_token",
        refresh_token="test_refresh_token",
        token_type="Bearer",
        expires_in=3600,
    )
    
    assert tokens.access_token == "test_access_token"
    assert tokens.refresh_token == "test_refresh_token"
    assert tokens.token_type == "Bearer"
    assert tokens.expires_in == 3600


def test_openai_client_initialization():
    """Test OpenAI client initialization."""
    client = OpenAIClient(
        client_id="test_client_id",
        redirect_uri="http://localhost:3000/callback",
    )
    
    assert client.config.client_id == "test_client_id"
    assert client.config.redirect_uri == "http://localhost:3000/callback"
    assert client.config.authorization_endpoint == OpenAIClient.AUTHORIZATION_ENDPOINT
    assert client.config.token_endpoint == OpenAIClient.TOKEN_ENDPOINT


def test_openai_client_generate_auth_url():
    """Test authorization URL generation."""
    client = OpenAIClient(client_id="test_client_id")
    auth_url = client.get_authorization_url()
    
    # URL should contain required parameters
    assert "https://auth.openai.com/authorize" in auth_url
    assert "response_type=code" in auth_url
    assert "client_id=test_client_id" in auth_url
    assert "redirect_uri=" in auth_url
    assert "scope=" in auth_url
    assert "code_challenge=" in auth_url
    assert "code_challenge_method=S256" in auth_url
    assert "state=" in auth_url


def test_openai_client_state_generation():
    """Test that state is generated and stored."""
    client = OpenAIClient(client_id="test_client_id")
    
    # First call should generate a state
    auth_url1 = client.get_authorization_url()
    state1 = client._state
    
    # Second call should generate a different state
    auth_url2 = client.get_authorization_url()
    state2 = client._state
    
    # States should be different
    assert state1 is not None
    assert state2 is not None
    assert state1 != state2


def test_openai_client_custom_state():
    """Test custom state parameter."""
    client = OpenAIClient(client_id="test_client_id")
    custom_state = "my_custom_state_123"
    
    auth_url = client.get_authorization_url(state=custom_state)
    
    assert client._state == custom_state
    assert f"state={custom_state}" in auth_url


def test_openai_client_pkce_pair_generation():
    """Test PKCE pair generation."""
    client = OpenAIClient(client_id="test_client_id")
    
    verifier, challenge = client.generate_pkce_pair()
    
    assert client._verifier == verifier
    assert client._challenge == challenge
    
    # Verify challenge matches verifier
    challenge2 = generate_code_challenge(verifier)
    assert challenge == challenge2


def test_openai_client_decode_jwt():
    """Test JWT decoding."""
    client = OpenAIClient(client_id="test_client_id")
    
    # Create a simple JWT (header.payload.signature)
    # Note: signature is invalid, but we don't verify
    import base64
    import json
    
    payload = {"sub": "user123", "exp": 1234567890, "aud": ["api1", "api2"]}
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    
    header = {"alg": "RS256", "typ": "JWT"}
    header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    
    # Create fake JWT (signature is just "sig")
    token = f"{header_b64}.{payload_b64}.sig"
    
    decoded = client.decode_jwt(token)
    
    assert decoded["sub"] == "user123"
    assert decoded["exp"] == 1234567890
    assert decoded["aud"] == ["api1", "api2"]


def test_openai_client_is_token_expired():
    """Test token expiration checking."""
    client = OpenAIClient(client_id="test_client_id")
    
    # Create a token that is expired
    import base64
    import json
    import time
    
    expired_payload = {"sub": "user", "exp": int(time.time()) - 1000}  # Expired 1000s ago
    expired_payload_b64 = base64.urlsafe_b64encode(json.dumps(expired_payload).encode()).decode().rstrip("=")
    header_b64 = base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()).decode().rstrip("=")
    expired_token = f"{header_b64}.{expired_payload_b64}.sig"
    
    # Create a token that is not expired
    valid_payload = {"sub": "user", "exp": int(time.time()) + 3600}  # Expires in 1 hour
    valid_payload_b64 = base64.urlsafe_b64encode(json.dumps(valid_payload).encode()).decode().rstrip("=")
    valid_token = f"{header_b64}.{valid_payload_b64}.sig"
    
    assert client.is_token_expired(expired_token) is True
    assert client.is_token_expired(valid_token) is False


def test_openai_client_is_token_expired_no_exp():
    """Test token without expiration claim."""
    client = OpenAIClient(client_id="test_client_id")
    
    # Create a token without exp claim
    import base64
    import json
    
    payload = {"sub": "user", "aud": ["api1"]}
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    header_b64 = base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()).decode().rstrip("=")
    token = f"{header_b64}.{payload_b64}.sig"
    
    # Should return False (not expired) when no exp claim
    assert client.is_token_expired(token) is False


def test_openai_client_exchange_code_without_verifier():
    """Test that token exchange fails without PKCE verifier."""
    client = OpenAIClient(client_id="test_client_id")
    
    # Don't call get_authorization_url(), so no verifier
    with pytest.raises(PKCEError, match="PKCE verifier not generated"):
        client.exchange_code_for_tokens(
            "http://localhost:3000/callback?code=test_code&state=test_state"
        )


def test_openai_client_exchange_code_missing_code():
    """Test that token exchange fails with missing code."""
    client = OpenAIClient(client_id="test_client_id")
    client.get_authorization_url()  # Generate verifier
    
    # URL without code parameter
    with pytest.raises(TokenExchangeError, match="No code found in redirect URL"):
        client.exchange_code_for_tokens(
            "http://localhost:3000/callback?state=test_state"
        )


def test_openai_client_exchange_code_state_mismatch():
    """Test that token exchange fails with state mismatch."""
    client = OpenAIClient(client_id="test_client_id")
    client.get_authorization_url()  # Generates state1
    
    # URL with different state
    with pytest.raises(TokenExchangeError, match="State mismatch"):
        client.exchange_code_for_tokens(
            "http://localhost:3000/callback?code=test_code&state=different_state"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
