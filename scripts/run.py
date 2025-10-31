#!/usr/bin/env python3
"""
Simple development runner for Gatekeeper bot
"""

import sys
from pathlib import Path

# Add bot directory to path
sys.path.insert(0, str(Path(__file__).parent))

from bot.main import run

if __name__ == "__main__":
    print("🔐 Starting Gatekeeper Bot (Development Mode)")
    print("=" * 50)
    run()