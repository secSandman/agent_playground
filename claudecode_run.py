#!/usr/bin/env python3
"""
ClaudeCode Sandbox Launcher - Root wrapper

This script delegates to the actual launcher in cmd/claudecode/run.py
"""

import sys
from pathlib import Path

# Add cmd/claudecode to path so we can import run module
cmd_claudecode_path = Path(__file__).parent / "cmd" / "claudecode"
sys.path.insert(0, str(cmd_claudecode_path))

# Import and run the main launcher
from run import main

if __name__ == "__main__":
    main()
