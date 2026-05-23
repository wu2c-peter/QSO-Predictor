"""Plain utility modules with no Qt/main-app dependencies.

Code that lives here must stay importable from controllers, widgets, and
worker threads without dragging in the main module — that's the seam
that prevents accidental re-execution of `main_v2.py` top-level code
when something does `from main_v2 import …` from a background thread.

Copyright (C) 2025 Peter Hirst (WU2C)
"""

from .version import get_version, compare_versions, is_packaged_install

__all__ = [
    "get_version",
    "compare_versions",
    "is_packaged_install",
]
