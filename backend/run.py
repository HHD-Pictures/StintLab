#!/usr/bin/env python3
"""StintLab — run the backend server."""

import asyncio
import os
import sys

# Ensure the backend directory is always in the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n StintLab stopped.")