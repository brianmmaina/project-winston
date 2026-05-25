#!/usr/bin/env python3
"""Thin entrypoint kept for Docker `python scripts/verify_persistence.py` (delegates to app package)."""

from app.scripts.verify_persistence import main

if __name__ == "__main__":
    main()
