"""Tests for utils.version — semver-ish comparison + version-string parsing.

compare_versions feeds the GitHub update checker: it has to return True
when a newer version is available, False when current is up-to-date or
newer. Off-by-one bugs here would either spam users with phantom update
notifications or hide real updates.
"""

import pytest

from utils.version import compare_versions, get_version, is_packaged_install


class TestCompareVersions:
    """compare_versions(current, latest) -> True iff latest > current."""

    @pytest.mark.parametrize("current,latest", [
        ("1.0.0", "1.0.1"),
        ("1.0.0", "1.1.0"),
        ("1.0.0", "2.0.0"),
        ("2.5.5", "2.5.6"),
        ("2.5.5.1", "2.5.6"),
        ("2.5", "2.5.1"),
        ("0.9.99", "1.0.0"),
    ])
    def test_newer_returns_true(self, current, latest):
        assert compare_versions(current, latest) is True

    @pytest.mark.parametrize("current,latest", [
        ("1.0.0", "1.0.0"),    # equal
        ("1.0.1", "1.0.0"),    # current newer
        ("2.0.0", "1.99.0"),   # current much newer
        ("2.5.6", "2.5.5"),
        ("2.5.6", "2.5.5.1"),
    ])
    def test_same_or_older_returns_false(self, current, latest):
        assert compare_versions(current, latest) is False

    def test_git_describe_format_handled(self):
        # `git describe --tags` produces "2.5.5-3-gabcdef" for HEAD that is
        # 3 commits past tag v2.5.5. The compare logic strips the suffix
        # before integer comparison, so "2.5.5-3-gabcdef" should be treated
        # as 2.5.5 for comparison purposes.
        # 2.5.6 is greater than 2.5.5 → True
        assert compare_versions("2.5.5-3-gabcdef", "2.5.6") is True
        # 2.5.5 vs 2.5.5-3-gabcdef → both parse to 2.5.5, equal → False
        assert compare_versions("2.5.5", "2.5.5-3-gabcdef") is False

    def test_unparseable_falls_back_to_string_compare(self):
        # Defensive fallback when version strings don't have integer parts.
        # The fallback rule: True iff `latest != current and latest > current`
        # (string comparison).
        assert compare_versions("alpha", "beta") is True
        assert compare_versions("beta", "alpha") is False
        assert compare_versions("alpha", "alpha") is False

    def test_different_length_versions(self):
        # 2.5 vs 2.5.0 should be equal (shorter padded with zeros).
        assert compare_versions("2.5", "2.5.0") is False
        assert compare_versions("2.5.0", "2.5") is False


class TestGetVersion:
    """get_version reads from git describe, then VERSION file, then 'dev'."""

    def test_returns_a_string(self):
        # Either git describe gives us "X.Y.Z[-N-gXXX]" or VERSION file gives
        # us "X.Y.Z" or we fall through to "dev". All are strings.
        v = get_version()
        assert isinstance(v, str)
        assert len(v) > 0

    def test_no_leading_v(self):
        # Tags are "v2.5.6" but get_version strips the prefix.
        v = get_version()
        assert not v.startswith("v"), (
            f"get_version() should strip leading 'v' from tag; got {v!r}"
        )


class TestIsPackagedInstall:
    """is_packaged_install is Windows-only; returns False everywhere else."""

    def test_returns_bool(self):
        # On a non-Windows host (CI Linux runner, dev Mac), this returns False
        # via the platform guard. On Windows, it returns True/False based on
        # the MSIX detection. Either way: must be a bool.
        result = is_packaged_install()
        assert isinstance(result, bool)

    def test_non_windows_returns_false(self):
        # The function's first line is `if sys.platform != 'win32': return False`.
        # This test verifies that contract on the platforms where it runs.
        import sys
        if sys.platform == 'win32':
            pytest.skip("Windows-specific behavior; test asserts non-Windows contract")
        assert is_packaged_install() is False
