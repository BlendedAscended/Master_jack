#!/usr/bin/env python3
"""
Titan MCP Server Runner

Loads environment variables from .env and starts the MCP server.
This wrapper ensures env vars are available when running via MCP Inspector.
"""

import os
import sys

# Add the current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables from .env
from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(env_path)

print(f"[Titan] Loading environment from: {env_path}", file=sys.stderr)
print(f"[Titan] DEEPSEEK_API_KEY: {'✓ loaded' if os.environ.get('DEEPSEEK_API_KEY') else '✗ missing'}", file=sys.stderr)
print(f"[Titan] AIRTABLE_API_KEY: {'✓ loaded' if os.environ.get('AIRTABLE_API_KEY') else '✗ missing'}", file=sys.stderr)
print(f"[Titan] APOLLO_API_KEY: {'✓ loaded' if os.environ.get('APOLLO_API_KEY') else '✗ missing'}", file=sys.stderr)

# Now import and run the server
from server import main
import asyncio

if __name__ == "__main__":
    print("[Titan] Starting MCP Server...", file=sys.stderr)
    asyncio.run(main())
