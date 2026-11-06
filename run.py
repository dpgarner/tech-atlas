#!/usr/bin/env python3
"""Entry point:  python run.py <command> [options]"""
import os
import sys

# Make the package importable no matter how Python was invoked (embedded
# distributions, safe-path mode, odd launchers, etc.).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from atlas.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
