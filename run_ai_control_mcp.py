#!/usr/bin/env python3
"""
WhatsApp AI Control with MCP Architecture
Run with --mcp flag to enable MCP mode
"""

import sys
import os
import argparse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.client.whatsapp_ai_control_mcp import main

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WhatsApp AI Control with optional MCP")
    parser.add_argument("--mcp", "-m", action="store_true",
                      help="Enable MCP mode (connects to MCP server)")
    parser.add_argument("--mcp-url", default="ws://localhost:8002",
                      help="MCP server URL (default: ws://localhost:8002)")

    args = parser.parse_args()

    # Pass MCP flag to main
    if args.mcp:
        sys.argv.append("--mcp")

    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped by user")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)