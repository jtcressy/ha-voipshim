#!/usr/bin/env python3
"""Compatibility wrapper for running the canonical add-on shim locally."""

from __future__ import annotations

from pathlib import Path
import runpy


if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).with_name("voipshim-addon") / "shim.py"),
        run_name="__main__",
    )
