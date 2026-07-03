# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""utils.parsing — the shared competition-string parser.

Consolidates what were previously three private copies (main_v2,
insights_panel, and the schema-v2 capture sites). The 'local' suffix
carries provenance: target-side rivals vs locally-heard callers are
distinct phenomena (see v2.2.1 dedup rule).
"""

import pytest

from utils.parsing import parse_competition


@pytest.mark.parametrize("comp_str, count, src", [
    ("Low (2)", 2, 'target'),
    ("Medium (3) + QRM", 3, 'target'),
    ("High (4) local", 4, 'local'),
    ("PILEUP (8)", 8, 'target'),
    ("Low (1) local", 1, 'local'),
    ("Clear", 0, None),
    ("Unknown", 0, None),
    ("--", 0, None),
    ("", 0, None),
    ("Heard by Target", 0, None),   # path string used as placeholder in bulk rows
])
def test_parse_competition(comp_str, count, src):
    assert parse_competition(comp_str) == (count, src)
