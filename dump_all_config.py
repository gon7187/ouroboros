#!/usr/bin/env python3
"""Dump full openclaw.json structure"""

import json

with open('/home/test/.openclaw/openclaw.json') as f:
    config = json.load(f)

print("=== Full openclaw.json Structure ===")
print(json.dumps(config, indent=2, ensure_ascii=False))
