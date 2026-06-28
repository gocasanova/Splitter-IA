#!/usr/bin/env python3
"""Main entry point for AI Band Practice Tool."""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path.parent))

from src.ui.main_window import main

if __name__ == "__main__":
    main()
