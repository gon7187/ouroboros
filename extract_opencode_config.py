#!/usr/bin/env python3
"""Extract OpenCode configuration from openclaw.json"""

import json

# Read config
with open('/home/test/.openclaw/openclaw.json') as f:
    config = json.load(f)

# Find OpenCode provider
providers = config.get('providers', {})

print("=== All Providers in openclaw.json ===")
for name, provider in providers.items():
    base_url = provider.get('baseUrl', 'NO_BASE_URL')
    models = provider.get('models', [])
    print(f"\n{name}:")
    print(f"  baseUrl: {base_url}")
    if models:
        print(f"  models: {', '.join(models[:5])}{'...' if len(models) > 5 else ''}")

print("\n\n=== OpenCode Specific ===")
if 'opencode' in providers:
    oc = providers['opencode']
    print(f"Base URL: {oc.get('baseUrl', 'NOT SET')}")
    print(f"Models ({len(oc.get('models', []))}):")
    for m in oc.get('models', []):
        print(f"  - {m}")
else:
    print("OpenCode provider not found!")
