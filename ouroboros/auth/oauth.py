"""OAuth 2.0 client for OpenAI authorization.

Implements Authorization Code flow for obtaining access tokens
that can be used with OpenAI API.

This module handles:
1. Generating authorization URL
2. Exchanging authorization code for access token
3. Refreshing tokens using refresh token
4. Storing tokens securely

Usage example:
    client = OpenAIClient()
    
    # Step 1: Get authorization URL
    auth_url = client.get_authorization_url()
    print(f"Visit: {auth_url}")
    
    # Step 2: User visits URL and authorizes, gets redirect URL
    redirect_url = input("Paste redirect URL here: ")
    
    # Step 3: Exchange code for tokens
    tokens = client.exchange_code_for_tokens(redirect_url)
    
    # Step 4: Use access token
    access_token = tokens["access_token"]
"""

import base64
import json
import secrets
from dataclasses import dataclass
from typing import Optional, Dict, Any
from urllib.parse import urlparse, parse_qs, urlencode
import hashlib

import httpx


@dataclass
class OAuthConfig:
    """OAuth 2.0 configuration."""
    
    client_id: str
    authorization_endpoint: str
    token_endpoint: str
    redirect_uri: str
    scopes: list[str]
    
    # Optional: client secret (public clients use PKCE)
    client_secret: Optional[str] = None


@dataclass
class OAuthTokens:
    """OAuth tokens from authorization flow."""
    
    access_token: str
    refresh_token: Optional[str]
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    scope: Optional[str] = None
    expires_at: Optional[int] = None


class PKCEError(Exception):
    """PKCE flow error."""
    pass


class TokenExchangeError(Exception):
    """Token exchange error."""
    pass


class RefreshTokenError(Exception):
    """Refresh token error."""
    pass


def generate_code_verifier() -> str:
    """Generate a random code verifier for PKCE.
    
    Returns:
        Random 43-128 character string
    """
    return secrets.token_urlsafe(64)


def generate_code_challenge(verifier: str) -> str:
    """Generate code challenge from verifier for PKCE.
    
    Args:
        verifier: Code verifier string
        
    Returns:
        Base64URL-encoded SHA256 hash
    """
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


class OAuthClient:
    """Generic OAuth 2.0 client with PKCE support.
    
    Implements Authorization Code flow with PKCE for public clients.
    Suitable for applications that cannot safely store a client secret.
    """
    
    def __init__(self, config: OAuthConfig):
        """Initialize OAuth client.
        
        Args:
            config: OAuth configuration
        """
        self.config = config
        self._verifier: Optional[str] = None
        self._challenge: Optional[str] = None
        self._state: Optional[str] = None
    
    def generate_pkce_pair(self) -> tuple[str, str]:
        """Generate PKCE code verifier and challenge.
        
        Returns:
            Tuple of (verifier, challenge)
        """
        verifier = generate_code_verifier()
        challenge = generate_code_challenge(verifier)
        self._verifier = verifier
        self._challenge = challenge
        return verifier, challenge
    
    def get_authorization_url(self, state: Optional[str] = None) -> str:
        """Generate authorization URL for user to visit.
        
        Args:
            state: Optional state parameter for CSRF protection
            
        Returns:
            Full authorization URL
        """
        if not self._verifier or not self._challenge:
            self.generate_pkce_pair()
        
        if state is None:
            state = secrets.token_urlsafe(32)
        self._state = state
        
        params = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "scope": " ".join(self.config.scopes),
            "code_challenge": self._challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
        
        query_string = urlencode(params)
        return f"{self.config.authorization_endpoint}?{query_string}"
    
    def exchange_code_for_tokens(
        self,
        redirect_url: str,
    ) -> OAuthTokens:
        """Exchange authorization code for access token.
        
        Args:
            redirect_url: Full redirect URL with code and state parameters
            
        Returns:
            OAuth tokens
            
        Raises:
            TokenExchangeError: If token exchange fails
        """
        if not self._verifier:
            raise PKCEError("PKCE verifier not generated. Call get_authorization_url() first.")
        
        # Parse redirect URL to extract code and state
        parsed = urlparse(redirect_url)
        params = parse_qs(parsed.query)
        
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        
        if not code:
            raise TokenExchangeError(f"No code found in redirect URL: {redirect_url}")
        
        if state != self._state:
            raise TokenExchangeError(f"State mismatch. Expected {self._state}, got {state}")
        
        # Build token request
        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.config.redirect_uri,
            "client_id": self.config.client_id,
            "code_verifier": self._verifier,
        }
        
        if self.config.client_secret:
            token_data["client_secret"] = self.config.client_secret
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        
        # Exchange code for token
        with httpx.Client() as client:
            response = client.post(
                self.config.token_endpoint,
                data=token_data,
                headers=headers,
            )
        
        if response.status_code != 200:
            raise TokenExchangeError(
                f"Token exchange failed: {response.status_code} - {response.text}"
            )
        
        token_json = response.json()
        
        # Parse tokens
        access_token = token_json.get("access_token")
        if not access_token:
            raise TokenExchangeError("No access_token in response")
        
        refresh_token = token_json.get("refresh_token")
        token_type = token_json.get("token_type", "Bearer")
        expires_in = token_json.get("expires_in")
        scope = token_json.get("scope")
        
        # Calculate expiration timestamp if expires_in is present
        expires_at = None
        if expires_in:
            import time
            expires_at = int(time.time()) + int(expires_in)
        
        return OAuthTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type=token_type,
            expires_in=expires_in,
            scope=scope,
            expires_at=expires_at,
        )
    
    def refresh_tokens(self, refresh_token: str) -> OAuthTokens:
        """Refresh access token using refresh token.
        
        Args:
            refresh_token: Refresh token from previous exchange
            
        Returns:
            New OAuth tokens
            
        Raises:
            RefreshTokenError: If refresh fails
        """
        token_data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.config.client_id,
        }
        
        if self.config.client_secret:
            token_data["client_secret"] = self.config.client_secret
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        
        with httpx.Client() as client:
            response = client.post(
                self.config.token_endpoint,
                data=token_data,
                headers=headers,
            )
        
        if response.status_code != 200:
            raise RefreshTokenError(
                f"Token refresh failed: {response.status_code} - {response.text}"
            )
        
        token_json = response.json()
        
        access_token = token_json.get("access_token")
        if not access_token:
            raise RefreshTokenError("No access_token in refresh response")
        
        new_refresh_token = token_json.get("refresh_token", refresh_token)
        token_type = token_json.get("token_type", "Bearer")
        expires_in = token_json.get("expires_in")
        scope = token_json.get("scope")
        
        expires_at = None
        if expires_in:
            import time
            expires_at = int(time.time()) + int(expires_in)
        
        return OAuthTokens(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type=token_type,
            expires_in=expires_in,
            scope=scope,
            expires_at=expires_at,
        )


class OpenAIClient(OAuthClient):
    """OpenAI OAuth 2.0 client.
    
    Uses OpenAI's OAuth endpoints for obtaining tokens that work
    with both api.openai.com and chatgpt.com backend APIs.
    """
    
    # OpenAI OAuth endpoints
    AUTHORIZATION_ENDPOINT = "https://auth.openai.com/authorize"
    TOKEN_ENDPOINT = "https://auth.openai.com/oauth/token"
    
    # Default scopes
    DEFAULT_SCOPES = [
        "openid",
        "profile",
        "email",
        "offline_access",  # Enables refresh token
    ]
    
    # Default redirect URI (for local development)
    DEFAULT_REDIRECT_URI = "http://localhost:3000/callback"
    
    def __init__(
        self,
        client_id: str,
        client_secret: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        scopes: Optional[list[str]] = None,
    ):
        """Initialize OpenAI OAuth client.
        
        Args:
            client_id: OpenAI OAuth client ID
            client_secret: Optional client secret (for confidential clients)
            redirect_uri: OAuth redirect URI
            scopes: List of OAuth scopes
        """
        config = OAuthConfig(
            client_id=client_id,
            authorization_endpoint=self.AUTHORIZATION_ENDPOINT,
            token_endpoint=self.TOKEN_ENDPOINT,
            redirect_uri=redirect_uri or self.DEFAULT_REDIRECT_URI,
            scopes=scopes or self.DEFAULT_SCOPES,
            client_secret=client_secret,
        )
        super().__init__(config)
    
    def get_authorization_url(self, state: Optional[str] = None) -> str:
        """Generate OpenAI authorization URL.
        
        Args:
            state: Optional state parameter
            
        Returns:
            Full OpenAI authorization URL
        """
        return super().get_authorization_url(state)
    
    def get_access_token(self, redirect_url: str) -> str:
        """Get access token from redirect URL (convenience method).
        
        Args:
            redirect_url: Redirect URL from OAuth callback
            
        Returns:
            Access token string
        """
        tokens = self.exchange_code_for_tokens(redirect_url)
        return tokens.access_token
    
    def decode_jwt(self, token: str) -> Dict[str, Any]:
        """Decode JWT access token (without verification).
        
        Useful for inspecting token contents (claims, expiration, scopes).
        
        Args:
            token: JWT access token
            
        Returns:
            Decoded JWT payload as dict
        """
        # Split token into parts
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid JWT format")
        
        # Decode payload (middle part)
        payload_b64 = parts[1]
        
        # Add padding if needed
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        
        # Base64 decode
        payload_json = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_json)
    
    def is_token_expired(self, token: str) -> bool:
        """Check if JWT token is expired.
        
        Args:
            token: JWT access token
            
        Returns:
            True if token is expired, False otherwise
        """
        import time
        payload = self.decode_jwt(token)
        exp = payload.get("exp")
        if not exp:
            return False  # No expiration claim
        return int(time.time()) >= exp


def parse_redirect_url(redirect_url: str) -> Dict[str, str]:
    """Parse OAuth redirect URL to extract parameters.
    
    Args:
        redirect_url: Full redirect URL with query parameters
        
    Returns:
        Dict of query parameters
    """
    parsed = urlparse(redirect_url)
    params = parse_qs(parsed.query)
    
    # Convert lists to single values
    return {k: v[0] if v else "" for k, v in params.items()}
