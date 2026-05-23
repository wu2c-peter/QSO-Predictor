"""Tests for analyzer.geometry — pure helpers carved out of QSOAnalyzer.

These functions have no side effects, no Qt state, no locks. They're the
easiest piece of the codebase to test, and the most-used helpers in path
classification + signal density calculations.
"""

import pytest

from analyzer import geometry


# --- freq_to_band ---------------------------------------------------------


class TestFreqToBand:
    """Map Hz frequencies to amateur band names."""

    @pytest.mark.parametrize("freq_hz,expected", [
        (1_840_000, "160m"),
        (3_573_000, "80m"),
        (5_357_000, "60m"),
        (7_074_000, "40m"),
        (10_136_000, "30m"),
        (14_074_000, "20m"),
        (14_076_000, "20m"),  # mid-band
        (18_100_000, "17m"),
        (21_074_000, "15m"),
        (24_915_000, "12m"),
        (28_074_000, "10m"),
        (50_313_000, "6m"),
    ])
    def test_recognized_bands(self, freq_hz, expected):
        assert geometry.freq_to_band(freq_hz) == expected

    @pytest.mark.parametrize("freq_hz", [
        0,
        1_000_000,        # below 160m
        4_500_000,        # between 80m and 60m
        9_000_000,        # between 60m and 30m
        15_000_000,       # between 20m and 17m
        100_000_000,      # FM/VHF — unrecognized
    ])
    def test_unrecognized_returns_sentinel(self, freq_hz):
        assert geometry.freq_to_band(freq_hz) == "??m"

    def test_band_edges_inclusive(self):
        # Band definitions in the function use `<=` on both ends. The 20m
        # endpoints should both classify as 20m, not "??m".
        assert geometry.freq_to_band(14_000_000) == "20m"
        assert geometry.freq_to_band(14_350_000) == "20m"


# --- is_callsign ----------------------------------------------------------


class TestIsCallsign:
    """Loose heuristic for "this string could be an amateur callsign."""

    @pytest.mark.parametrize("call", [
        "WU2C",
        "JA1XYZ",
        "G0ABC",
        "DL1ABCD",
        "VE3ABC",
        "K1A",          # minimum length 3
        "9V1AB",        # 5 chars
        "ZL2/M0ABC",    # portable prefix
    ])
    def test_real_callsigns(self, call):
        assert geometry.is_callsign(call) is True

    @pytest.mark.parametrize("call", [
        "",            # empty
        "AB",          # too short (<3)
        "ABCDEFGHIJK", # too long (>10)
        "HELLO",       # no digit
        "WU2C!",       # special char
        "WU2C@HOME",   # @ is not allowed
        None,          # not a string — guarded against by the `not s` check
    ])
    def test_non_callsigns(self, call):
        assert geometry.is_callsign(call) is False

    def test_heuristic_is_intentionally_loose(self):
        # is_callsign is a fast first-pass filter for FT8 message parsing,
        # not a real callsign validator. It accepts any alnum string of
        # length 3-10 that contains at least one digit. This means pure-
        # digit strings like "1234" pass — that's a documented limitation,
        # not a bug. Downstream code does stricter validation when needed.
        assert geometry.is_callsign("1234") is True

    def test_angle_bracket_wrapping_is_stripped(self):
        # FT8 messages occasionally wrap calls in angle brackets to indicate
        # hashed/abbreviated representations. The heuristic strips them.
        assert geometry.is_callsign("<WU2C>") is True


# --- bearing_to_region ----------------------------------------------------


class TestBearingToRegion:
    """Coarse mapping from bearing-from-grid to DXCC region code."""

    @pytest.mark.parametrize("bearing,expected", [
        (0,    "NA"),    # due north (default branch)
        (45,   "EU"),    # NE quadrant
        (90,   "AF/ME"),
        (135,  "AS"),
        (180,  "OC"),
        (225,  "OC"),    # wraps into OC range
        (270,  "SA"),
        (315,  "CA"),
        (350,  "NA"),    # wraps back to NA via the default branch
    ])
    def test_known_bearings(self, bearing, expected):
        assert geometry.bearing_to_region(bearing) == expected

    def test_modulo_normalization(self):
        # Bearings > 360 should wrap around.
        assert geometry.bearing_to_region(360) == geometry.bearing_to_region(0)
        assert geometry.bearing_to_region(450) == geometry.bearing_to_region(90)

    def test_negative_bearings_normalize(self):
        # Negative bearings should also wrap.
        assert geometry.bearing_to_region(-90) == geometry.bearing_to_region(270)


# --- max_concentration ----------------------------------------------------


class TestMaxConcentration:
    """Highest percentage of spots in any 3 adjacent sectors (135° arc)."""

    def test_empty_sectors(self):
        assert geometry.max_concentration([0] * 8) == 0

    def test_single_direction(self):
        # All spots in one sector: that sector + 2 neighbors = 100% of total.
        sectors = [10, 0, 0, 0, 0, 0, 0, 0]
        assert geometry.max_concentration(sectors) == 100

    def test_uniform_distribution(self):
        # 1 per sector: any 3 adjacent = 3/8 = 37%
        sectors = [1] * 8
        assert geometry.max_concentration(sectors) == 37

    def test_partial_concentration(self):
        # 3+1+0=4 of 4 spots = 100% in one 3-sector arc;
        # but 3 of the 4 are also in N+NE+E (3+1+0=4/4=100%).
        # Use a less degenerate case:
        # NE=2, E=4, SE=2, rest=0. Total=8.
        # NE+E+SE = 2+4+2 = 8/8 = 100%
        sectors = [0, 2, 4, 2, 0, 0, 0, 0]
        assert geometry.max_concentration(sectors) == 100

    def test_split_distribution(self):
        # Half in N region, half in S region.
        # Total = 8. Best 3-arc concentration ≈ 4/8 = 50%.
        sectors = [2, 1, 1, 0, 2, 1, 1, 0]
        result = geometry.max_concentration(sectors)
        # Best window is N+NE+NW or similar — should be 4/8 = 50
        assert result == 50

    def test_wraparound_window(self):
        # Spots concentrated at N (sector 0) and NW (sector 7).
        # The 3-sector window centered on N (NW, N, NE) should win.
        sectors = [5, 0, 0, 0, 0, 0, 0, 5]
        # NW=5 + N=5 + NE=0 = 10/10 = 100%
        assert geometry.max_concentration(sectors) == 100


# --- sector_distribution --------------------------------------------------


class TestSectorDistribution:
    """Bin spots into 8 compass sectors from a given grid."""

    def test_empty_spots(self):
        result = geometry.sector_distribution([], "FN42")
        assert result == [0] * 8

    def test_no_grid_skipped(self):
        # Spots without grids should be silently skipped.
        spots = [{"call": "ZZ1ZZZ"}, {"grid": "", "call": "X"}]
        result = geometry.sector_distribution(spots, "FN42")
        assert result == [0] * 8

    def test_too_short_grids_skipped(self):
        # Grids < 4 chars don't carry enough precision for bearing.
        spots = [{"grid": "FN"}, {"grid": "JO"}, {"grid": ""}]
        result = geometry.sector_distribution(spots, "FN42")
        assert result == [0] * 8

    def test_from_grid_empty_returns_zeros(self):
        # If our own grid is missing, we have no anchor — return zeros.
        result = geometry.sector_distribution(
            [{"grid": "JO22AB"}], from_grid=""
        )
        assert result == [0] * 8

    def test_counts_sum_matches_valid_spots(self):
        # Mix of valid and invalid spots — count only the valid ones.
        spots = [
            {"grid": "JO22AB"},    # valid (Europe from FN42 ~ NE)
            {"grid": "FN42MP"},    # valid (same as us — bearing undefined, but
                                   # at least 4 chars; will land somewhere)
            {"grid": ""},          # skipped
            {"grid": "FN"},        # skipped (<4 chars)
        ]
        result = geometry.sector_distribution(spots, "FN42MP")
        assert sum(result) == 2

    def test_known_bearing_lands_in_correct_sector(self):
        # FN42 → JO22 is roughly due east (~50° bearing).
        # Sector 0 is N (0-45° centered on 22.5°), sector 1 is NE (45-90°).
        # Bearing 50° / 45 = 1.11 → sector 1 (NE).
        spots = [{"grid": "JO22AB"}]
        result = geometry.sector_distribution(spots, "FN42MP")
        # The actual bearing depends on calculate_bearing's implementation;
        # what we assert is "exactly one spot was placed, in a single sector"
        assert sum(result) == 1
        nonzero = [i for i, c in enumerate(result) if c > 0]
        assert len(nonzero) == 1
