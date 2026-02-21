#!/usr/bin/env python3
"""OAuth authorization CLI tool.

Interactive tool for obtaining OAuth tokens from OpenAI.
Run this script, follow the prompts, and get your access token.

Usage:
    python scripts/oauth_auth.py

Requirements:
    - OpenAI OAuth client ID (get from OpenAI developer portal)
    - Python environment with httpx installed
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ouroboros.auth.oauth import OpenAIClient, parse_redirect_url


def main():
    """Run interactive OAuth flow."""
    print("=" * 60)
    print("OpenAI OAuth Authorization Tool")
    print("=" * 60)
    print()
    
    # Get client ID from user or use default from clawd bot
    print("Option 1: Enter your OpenAI OAuth client ID")
    print("Option 2: Use default from clawd bot config")
    choice = input("Choose (1 or 2) [2]: ").strip() or "2"
    
    if choice == "1":
        client_id = input("Enter OpenAI OAuth client ID: ").strip()
        if not client_id:
            print("❌ Client ID is required")
            return 1
    else:
        # Use client ID from clawd bot
        import json
        config_path = Path.home() / ".openclaw" / "openclaw.json"
        try:
            with open(config_path) as f:
                config = json.load(f)
            client_id = config.get("OPENAI_OAUTH_CLIENT_ID", "")
            if not client_id:
                print("❌ Could not find OPENAI_OAUTH_CLIENT_ID in config")
                return 1
            print(f"✅ Using client ID from config: {client_id}")
        except Exception as e:
            print(f"❌ Could not read config: {e}")
            return 1
    
    print()
    
    # Optional: custom redirect URI
    redirect_uri = input(
        "Enter redirect URI [default: http://localhost:3000/callback]: "
    ).strip() or None
    
    print()
    print("-" * 60)
    
    # Initialize OAuth client
    client = OpenAIClient(
        client_id=client_id,
        redirect_uri=redirect_uri,
    )
    
    # Generate authorization URL
    auth_url = client.get_authorization_url()
    
    print("Step 1: Visit this URL in your browser:")
    print()
    print(auth_url)
    print()
    print("-" * 60)
    print("Step 2: Authorize the application")
    print("-" * 60)
    print()
    print("You will be redirected to your redirect URI with an authorization code.")
    print("Copy the full redirect URL and paste it below.")
    print()
    
    # Get redirect URL from user
    redirect_url = input("Paste redirect URL here: ").strip()
    
    if not redirect_url:
        print("❌ Redirect URL is required")
        return 1
    
    print()
    print("-" * 60)
    
    try:
        # Exchange code for tokens
        tokens = client.exchange_code_for_tokens(redirect_url)
        
        print("✅ Authorization successful!")
        print()
        print("Access Token:")
        print(tokens.access_token)
        print()
        
        if tokens.refresh_token:
            print("Refresh Token:")
            print(tokens.refresh_token)
            print()
        
        if tokens.expires_at:
            import time
            expires_in = tokens.expires_at - int(time.time())
            expires_hours = expires_in / 3600
            print(f"Expires in: {expires_hours:.1f} hours")
            print()
        
        # Decode and show JWT payload
        print("JWT Payload (decoded):")
        payload = client.decode_jwt(tokens.access_token)
        print(json.dumps(payload, indent=2))
        print()
        
        # Save to file
        output_path = Path.home() / ".openclaw" / "agents" / "main" / "agent" / "auth-new.json"
        print("-" * 60)
        save = input(f"Save tokens to {output_path}? [y/N]: ").strip().lower()
        
        if save == "y":
            # Load existing auth file
            auth_data = {}
            if output_path.exists():
                with open(output_path) as f:
                    auth_data = json.load(f)
            
            # Add new tokens
            auth_data["openai-oauth"] = {
                "type": "oauth",
                "access": tokens.access_token,
                "refresh": tokens.refresh_token,
                "expires": tokens.expires_at,
            }
            
            # Save
            with open(output_path, "w") as f:
                json.dump(auth_data, f, indent=2)
            
            print(f"✅ Saved to {output_path}")
        else:
            print("Tokens not saved.")
        
        print()
        print("=" * 60)
        print("Done! You can now use the access token with OpenAI API.")
        print("=" * 60)
        
        return 0
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
