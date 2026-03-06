#!/usr/bin/env python3
"""
OpenCode Sandbox Launcher - Root wrapper

This script delegates to the actual launcher in cmd/opencode/run.py
"""

import sys
import os
from pathlib import Path

# Add cmd/opencode to path so we can import run module
cmd_opencode_path = Path(__file__).parent / "cmd" / "opencode"
sys.path.insert(0, str(cmd_opencode_path))

# Import and run the main launcher
from run import main

if __name__ == "__main__":
    main()
