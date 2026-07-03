# QSO Predictor
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

"""Parsers for UI display strings (pure stdlib, no Qt).

The canonical home for extracting structured values back out of strings
the analyzer formats for display. Consolidates parsers that previously
lived as private copies in main_v2.py and insights_panel.py.
"""

import re
from typing import Optional, Tuple

_COMPETITION_COUNT = re.compile(r'\((\d+)\)')


def parse_competition(comp_str: str) -> Tuple[int, Optional[str]]:
    """Parse an analyzer competition string into (count, source).

    Formats produced by analyzer/core.py: "Low (2)", "Medium (3) + QRM",
    "High (4) local", "PILEUP (8)", "Clear", "Unknown", "--", "".

    Returns:
        (count, source) where source is 'local' when the count came from
        local decode evidence (the "local" suffix), 'target' when it came
        from target-side perspective data, and None when there is no count
        at all ("Clear"/"Unknown"/empty).
    """
    if not comp_str:
        return 0, None
    m = _COMPETITION_COUNT.search(comp_str)
    if not m:
        return 0, None
    src = 'local' if 'local' in comp_str.lower() else 'target'
    return int(m.group(1)), src
