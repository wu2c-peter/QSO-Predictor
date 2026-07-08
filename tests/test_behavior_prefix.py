"""Prefix extraction for behavior-prior aggregation.

Regression context: `_extract_prefix` stopped before any digit, so every
single-letter-plus-digit country prefix collapsed to its first letter —
E51WL (Cook Islands) was pooled with E7 (Bosnia) stations, producing a
"based on 15 E stations" prior built from the wrong side of the planet.
For most ITU series a single letter + digit selects the *country*
(E5 vs E7, S5 Slovenia vs S7 Seychelles); only for a few series
(W/K/N USA, G/M UK, ...) is the digit a mere call area.
"""

import pytest

from local_intel.behavior_predictor import BehaviorPredictor


@pytest.fixture
def predictor(tmp_path):
    return BehaviorPredictor(history_path=tmp_path / 'behavior_history.json')


# --- Single letter + digit: digit is part of the country prefix ---

@pytest.mark.parametrize('callsign,expected', [
    ('E51WL', 'E5'),    # Cook Islands — the reported bug
    ('E73ABC', 'E7'),   # Bosnia
    ('E20XYZ', 'E2'),   # Thailand
    ('E44WE', 'E4'),    # Palestine
    ('E6AB', 'E6'),     # Niue
    ('S51AB', 'S5'),    # Slovenia
    ('S79KW', 'S7'),    # Seychelles
    ('T77XX', 'T7'),    # San Marino
    ('H44MS', 'H4'),    # Solomon Islands
])
def test_digit_kept_when_it_selects_country(predictor, callsign, expected):
    assert predictor._extract_prefix(callsign) == expected


def test_cook_islands_not_pooled_with_bosnia(predictor):
    assert predictor._extract_prefix('E51WL') != predictor._extract_prefix('E73ABC')


# --- Exempt series: digit is only a call area within one entity ---

@pytest.mark.parametrize('callsign,expected', [
    ('W1ABC', 'W'),     # USA
    ('K5ABC', 'K'),     # USA
    ('N2XYZ', 'N'),     # USA
    ('G3ABC', 'G'),     # UK
    ('M0ABC', 'M'),     # UK
    ('F5ABC', 'F'),     # France
    ('I2ABC', 'I'),     # Italy
    ('R1ABC', 'R'),     # Russia
])
def test_call_area_digit_dropped_for_single_entity_series(predictor, callsign, expected):
    assert predictor._extract_prefix(callsign) == expected


# --- Pre-existing behavior that must not change ---

@pytest.mark.parametrize('callsign,expected', [
    ('JA1ABC', 'JA'),
    ('DL5ABC', 'DL'),
    ('VK2ABC', 'VK'),
    ('EA1AB', 'EA'),    # two-letter E prefixes stay distinct from E-digit
    ('ES5TV', 'ES'),
    ('EI9AB', 'EI'),
    ('9A1AA', '9A'),
    ('5B4AB', '5B'),
    ('3DA0RS', '3DA'),
])
def test_existing_prefix_extraction_unchanged(predictor, callsign, expected):
    assert predictor._extract_prefix(callsign) == expected


def test_lowercase_and_whitespace_normalized(predictor):
    assert predictor._extract_prefix(' e51wl ') == 'E5'


# --- Prefix-prior sample-size gate ---

def _seed_history(predictor, calls):
    from local_intel.behavior_predictor import HistoricalRecord
    for call in calls:
        predictor._history[call] = HistoricalRecord(
            callsign=call, observations=3, loudest_first_count=3)
    predictor._prefix_stats_dirty = True


def test_prior_withheld_below_min_stations(predictor):
    n_below = BehaviorPredictor.PREFIX_PRIOR_MIN_STATIONS - 1
    _seed_history(predictor, [f'E7{i}AB' for i in range(n_below)])
    assert predictor._get_prefix_prior('E74XX') is None


def test_prior_offered_at_min_stations(predictor):
    n = BehaviorPredictor.PREFIX_PRIOR_MIN_STATIONS
    _seed_history(predictor, [f'E7{i}AB' for i in range(n)])
    prior = predictor._get_prefix_prior('E74XX')
    assert prior is not None
    assert prior.metadata['prefix'] == 'E7'
    assert prior.metadata['sample_stations'] == n


def test_prior_not_borrowed_across_e_countries(predictor):
    """E51WL (Cook Is) must not get a prior built from E7 (Bosnia) stations."""
    n = BehaviorPredictor.PREFIX_PRIOR_MIN_STATIONS
    _seed_history(predictor, [f'E7{i}AB' for i in range(n)])
    assert predictor._get_prefix_prior('E51WL') is None
