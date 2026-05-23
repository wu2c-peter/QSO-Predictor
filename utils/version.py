"""Version detection and comparison helpers.

Previously lived at the top of main_v2.py. Moved here so threads (notably
the update-checker worker) can read version info without re-importing
the main module — `from main_v2 import …` re-executes module-level code
because main_v2 is loaded as `__main__`, which doubles logger setup and
other startup side effects.

Copyright (C) 2025 Peter Hirst (WU2C)
"""

import ctypes
import subprocess
import sys
from pathlib import Path


def _base_path() -> Path:
    """Resolve the directory containing VERSION (frozen build or repo)."""
    if getattr(sys, 'frozen', False):
        # Running as compiled exe (PyInstaller sets _MEIPASS)
        return Path(sys._MEIPASS)
    # Running from source — VERSION lives next to this package's parent
    return Path(__file__).resolve().parent.parent


def get_version() -> str:
    """Get version from git tag or VERSION file."""
    base_path = _base_path()

    # Try git first (works for developers running from repo)
    if not getattr(sys, 'frozen', False):
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--always"],
                capture_output=True, text=True, cwd=base_path
            )
            if result.returncode == 0:
                return result.stdout.strip().lstrip('v')
        except Exception:
            pass

    # Fall back to VERSION file (works for zip downloads and frozen exe)
    try:
        return (base_path / "VERSION").read_text().strip()
    except Exception:
        return "dev"


def compare_versions(current: str, latest: str) -> bool:
    """Compare version strings. Returns True if `latest` > `current`."""
    try:
        # Handle versions like "1.2.3" or "1.2.3-5-gabcdef"
        def parse(v):
            # Take only the numeric part before any dash
            v = v.split('-')[0]
            return [int(x) for x in v.split('.')]

        curr_parts = parse(current)
        latest_parts = parse(latest)

        # Pad shorter list with zeros
        max_len = max(len(curr_parts), len(latest_parts))
        curr_parts += [0] * (max_len - len(curr_parts))
        latest_parts += [0] * (max_len - len(latest_parts))

        return latest_parts > curr_parts
    except Exception:
        # If parsing fails, do simple string comparison
        return latest != current and latest > current


def is_packaged_install() -> bool:
    """Detect if running from MSIX/AppX package (e.g. Microsoft Store install).

    Microsoft Store handles updates for Store-installed apps automatically,
    so the in-app GitHub-based update check is redundant (and worse, points
    users somewhere they cannot install from). When this returns True, callers
    should skip update checks and hide update-related UI.

    Uses the Windows GetCurrentPackageFullName API — the canonical way per
    Microsoft documentation. Returns ERROR_INSUFFICIENT_BUFFER (122) for
    packaged apps (telling caller the buffer needs sizing) or
    APPMODEL_ERROR_NO_PACKAGE (15700) for non-packaged processes.

    Defensive: any unexpected error returns False, meaning "treat as
    non-packaged, show update notifications." That's the safe default —
    if detection fails, source/GitHub users are not affected, and at worst
    MSIX users see a slightly noisy notification (the status quo before
    this function existed).
    """
    if sys.platform != 'win32':
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        length = ctypes.c_uint(0)
        result = kernel32.GetCurrentPackageFullName(ctypes.byref(length), None)
        return result == 122  # ERROR_INSUFFICIENT_BUFFER = packaged
    except Exception:
        return False
