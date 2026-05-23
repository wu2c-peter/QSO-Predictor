"""Analyzer package — spot processing, decode classification, target perspective.

The QSOAnalyzer class is the orchestration core; pure geometry/utility
helpers live in `geometry` so they're reusable and don't drag the locked
spot caches around.

Copyright (C) 2025 Peter Hirst (WU2C)
"""

from .core import QSOAnalyzer
from . import geometry

__all__ = ["QSOAnalyzer", "geometry"]
