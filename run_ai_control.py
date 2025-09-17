#!/usr/bin/env python3
"""
WhatsApp AI Control - Natural Language Interface

Control WhatsApp using natural language commands powered by Gemini AI.
Just type what you want to do - no special syntax needed!
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.client.whatsapp_ai_control import main

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped by user")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)