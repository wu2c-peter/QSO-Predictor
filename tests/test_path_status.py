"""Tests for local_intel.models.PathStatus.

PathStatus is the canonical domain type for path classification. Its
display_label values are byte-identical to historic UI strings (and
therefore persisted by the outcome recorder), so the contract is:
  - display_label strings frozen
  - from_display(label) round-trips for known labels
  - from_display(garbage) returns UNKNOWN (defensive default)
"""

import pytest

from local_intel.models import PathStatus


# All canonical display labels — these strings are persisted by
# outcome_recorder.py to ~/.qso-predictor/outcome_history.jsonl. Changing
# them would break older log files.
CANONICAL_LABELS = {
    PathStatus.HEARD_BY_TARGET: "Heard by Target",
    PathStatus.REPORTED_IN_REGION: "Reported in Region",
    PathStatus.NOT_REPORTED_IN_REGION: "Not Reported in Region",
    PathStatus.NOT_TRANSMITTING: "Not Transmitting",
    PathStatus.NO_REPORTERS: "No Reporters in Region",
    PathStatus.UNKNOWN: "",
}


class TestDisplayLabels:
    """display_label strings are an external contract — verify each one."""

    @pytest.mark.parametrize("status,expected", list(CANONICAL_LABELS.items()))
    def test_display_label_frozen(self, status, expected):
        assert status.display_label == expected

    def test_all_states_have_display_label(self):
        # If a new state is added without a display_label entry, this fails.
        for status in PathStatus:
            assert status.display_label is not None


class TestFromDisplay:
    """from_display(label) parses display strings back to enum values."""

    @pytest.mark.parametrize("status,label", [
        (PathStatus.HEARD_BY_TARGET, "Heard by Target"),
        (PathStatus.REPORTED_IN_REGION, "Reported in Region"),
        (PathStatus.NOT_REPORTED_IN_REGION, "Not Reported in Region"),
        (PathStatus.NOT_TRANSMITTING, "Not Transmitting"),
        (PathStatus.NO_REPORTERS, "No Reporters in Region"),
    ])
    def test_round_trip_recognized_labels(self, status, label):
        assert PathStatus.from_display(label) == status

    @pytest.mark.parametrize("garbage", [
        "",                              # empty
        "Heard",                         # partial / substring
        "Reported",                      # partial
        "Reported in Re",                # truncated
        "heard by target",               # case-sensitive — lowercase shouldn't match
        "Heard by Target!",              # trailing junk
        "Some Future Status",            # unknown
        "Not Reported in Regionx",       # extra char
    ])
    def test_unrecognized_returns_unknown(self, garbage):
        assert PathStatus.from_display(garbage) == PathStatus.UNKNOWN

    def test_substring_safety_not_reported_vs_reported(self):
        # This is the bug class the enum was introduced to prevent:
        # "Not Reported in Region" contains "Reported in Region" as a substring.
        # from_display uses exact match, so both round-trip to their own status.
        assert (
            PathStatus.from_display("Not Reported in Region")
            == PathStatus.NOT_REPORTED_IN_REGION
        )
        assert (
            PathStatus.from_display("Reported in Region")
            == PathStatus.REPORTED_IN_REGION
        )


class TestHasPathEvidence:
    """has_path_evidence partitions the enum into 'real signal' vs 'no data'.

    Predictor / strategy code uses this to treat UNKNOWN /
    NOT_TRANSMITTING / NO_REPORTERS uniformly.
    """

    def test_evidence_states(self):
        for status in (
            PathStatus.HEARD_BY_TARGET,
            PathStatus.REPORTED_IN_REGION,
            PathStatus.NOT_REPORTED_IN_REGION,
        ):
            assert status.has_path_evidence is True, status

    def test_no_evidence_states(self):
        for status in (
            PathStatus.UNKNOWN,
            PathStatus.NOT_TRANSMITTING,
            PathStatus.NO_REPORTERS,
        ):
            assert status.has_path_evidence is False, status


class TestColorAndRowBackground:
    """color and row_background back the dashboard + table rendering."""

    def test_every_state_has_a_color(self):
        # Each state must return a hex-ish string — the dashboard reads .color
        # unconditionally.
        for status in PathStatus:
            color = status.color
            assert isinstance(color, str)
            assert color.startswith("#")
            assert len(color) == 7  # #RRGGBB

    def test_row_background_present_only_for_priority_states(self):
        # Only HEARD_BY_TARGET and REPORTED_IN_REGION should have a row
        # background highlight. Others fall through to default alternating rows.
        assert PathStatus.HEARD_BY_TARGET.row_background is not None
        assert PathStatus.REPORTED_IN_REGION.row_background is not None
        for status in (
            PathStatus.NOT_REPORTED_IN_REGION,
            PathStatus.NOT_TRANSMITTING,
            PathStatus.NO_REPORTERS,
            PathStatus.UNKNOWN,
        ):
            assert status.row_background is None, status

    def test_distinct_foreground_colors(self):
        # The five visible-evidence states should have distinct foreground
        # colors so users can distinguish them at a glance.
        visible = [
            PathStatus.HEARD_BY_TARGET,
            PathStatus.REPORTED_IN_REGION,
            PathStatus.NOT_REPORTED_IN_REGION,
            PathStatus.NOT_TRANSMITTING,
            PathStatus.NO_REPORTERS,
        ]
        colors = {s.color for s in visible}
        assert len(colors) == len(visible), (
            "Two visible PathStatus states share a color — users can't tell them apart"
        )


class TestShortLabels:
    """short_label is used in space-constrained UI like the dashboard."""

    def test_short_label_present_for_displayed_states(self):
        for status in PathStatus:
            assert status.short_label is not None
            # short_label should be shorter or equal to display_label for the
            # primary states where shortening is the whole point.
            if status in (PathStatus.HEARD_BY_TARGET, PathStatus.REPORTED_IN_REGION):
                assert len(status.short_label) <= len(status.display_label)
