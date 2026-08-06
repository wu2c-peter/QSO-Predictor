"""Sweep-bias tilt for the frequency recommender.

Reproduces the 2026-08-06 OH0ERF session: the live pattern tracker
correctly detected METHODICAL_HIGH_LOW ("position at higher frequencies")
while the band-map recommender scored 1087 Hz at 100 and the winning
2508 Hz at 25 — the pattern never reached the recommendation. The fix is
a gentle multiplicative tilt (`analyzer.geometry.sweep_bias_multiplier`)
applied to the band map's score curve when a live picking pattern is
known with enough confidence: a weight, not an override.
"""

import pytest

from analyzer.geometry import sweep_bias_multiplier
from local_intel.models import PickingStyle


# The OH0ERF endgame, in numbers: two candidate offsets at opposite ends
# of the passband. Confidence from the session tracker is the |Spearman
# correlation| of the target's pickup order, > 0.5 by construction.
REC_FREQ = 1087
WIN_FREQ = 2508
CONFIDENCE = 0.86


class TestOH0ERFScenario:
    """The regression that motivated the feature."""

    def test_equal_scores_break_toward_sweep_direction(self):
        # Two regionally-quiet slots scored identically: with a high-to-low
        # sweep detected, the high slot must come out ahead.
        score = 82.0
        low = score * sweep_bias_multiplier(REC_FREQ, +1, CONFIDENCE)
        high = score * sweep_bias_multiplier(WIN_FREQ, +1, CONFIDENCE)
        assert high > low

    def test_tilt_is_a_weight_not_an_override(self):
        # A proven-ideal slot (100) at the "wrong" end must still beat a
        # regionally-quiet slot (82) at the favored end, even at full
        # confidence and full band separation.
        proven_wrong_end = 100.0 * sweep_bias_multiplier(200, +1, 1.0)
        quiet_favored_end = 82.0 * sweep_bias_multiplier(2800, +1, 1.0)
        assert proven_wrong_end > quiet_favored_end

    def test_low_high_pattern_mirrors(self):
        # A low-to-high sweeper favors the bottom of the passband.
        assert sweep_bias_multiplier(300, -1, CONFIDENCE) > \
               sweep_bias_multiplier(2700, -1, CONFIDENCE)


class TestMultiplierContract:
    def test_no_direction_is_identity(self):
        assert sweep_bias_multiplier(2508, 0, 0.9) == 1.0

    def test_zero_confidence_is_identity(self):
        assert sweep_bias_multiplier(2508, +1, 0.0) == 1.0

    def test_band_center_is_neutral(self):
        assert sweep_bias_multiplier(1500, +1, 1.0) == pytest.approx(1.0)

    def test_bounded_at_edges(self):
        # Max tilt is ±8% at full confidence; positions beyond the
        # passband clamp rather than extrapolate.
        assert sweep_bias_multiplier(2800, +1, 1.0) == pytest.approx(1.08)
        assert sweep_bias_multiplier(200, +1, 1.0) == pytest.approx(0.92)
        assert sweep_bias_multiplier(5000, +1, 1.0) == pytest.approx(1.08)
        assert sweep_bias_multiplier(-100, +1, 1.0) == pytest.approx(0.92)

    def test_confidence_clamped_to_one(self):
        assert sweep_bias_multiplier(2800, +1, 3.0) == \
               sweep_bias_multiplier(2800, +1, 1.0)

    def test_confidence_scales_tilt(self):
        full = sweep_bias_multiplier(2800, +1, 1.0)
        half = sweep_bias_multiplier(2800, +1, 0.5)
        assert 1.0 < half < full

    def test_direction_sign_only(self):
        # Any positive/negative magnitude behaves as +1/-1.
        assert sweep_bias_multiplier(2508, +3, 0.8) == \
               sweep_bias_multiplier(2508, +1, 0.8)


class TestPickingStyleMapping:
    """PickingStyle → sweep direction used by the band-map wiring."""

    def test_high_low_favors_high(self):
        assert PickingStyle.METHODICAL_HIGH_LOW.sweep_direction() == +1

    def test_low_high_favors_low(self):
        assert PickingStyle.METHODICAL_LOW_HIGH.sweep_direction() == -1

    @pytest.mark.parametrize("style", [
        PickingStyle.UNKNOWN, PickingStyle.LOUDEST_FIRST,
        PickingStyle.GEOGRAPHIC, PickingStyle.RANDOM,
    ])
    def test_non_directional_styles_are_neutral(self, style):
        assert style.sweep_direction() == 0
