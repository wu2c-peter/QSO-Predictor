# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""SolarClient must never launder a failed NOAA fetch into data.

2026-09 audit: any non-200 / schema-drift / network failure came back
as {'sfi': 0, 'k': 0, 'condx': 'Poor'}, which the header displayed as
real and IONIS consumed as physically impossible inputs (its 100/2
fallbacks never fired because the keys were always present).
"""

import pytest

import solar_client
from solar_client import SolarClient


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def _fake_get(responses):
    """responses: {url: _Resp or Exception}"""
    def get(url, timeout=5):
        r = responses[url]
        if isinstance(r, Exception):
            raise r
        return r
    return get


def test_new_format_parses(monkeypatch):
    monkeypatch.setattr(solar_client.requests, 'get', _fake_get({
        SolarClient.URL_FLUX: _Resp(200, [{"flux": 142, "time_tag": "x"}]),
        SolarClient.URL_PLANETARY_K: _Resp(200, [{"Kp": 1.0}, {"Kp": 3.33}]),
    }))
    data = SolarClient().get_solar_data()
    assert data == {'sfi': 142, 'k': 3, 'condx': 'Good', 'valid': True}


def test_old_format_parses(monkeypatch):
    monkeypatch.setattr(solar_client.requests, 'get', _fake_get({
        SolarClient.URL_FLUX: _Resp(200, {"Flux": "130", "TimeStamp": "x"}),
        SolarClient.URL_PLANETARY_K: _Resp(200, [["hdr"], ["2026-02-19", "3.33"]]),
    }))
    data = SolarClient().get_solar_data()
    assert (data['sfi'], data['k'], data['valid']) == (130, 3, True)


@pytest.mark.parametrize("flux_resp, kp_resp", [
    (_Resp(503, None), _Resp(200, [{"Kp": 1}, {"Kp": 2}])),            # HTTP error
    (_Resp(200, []), _Resp(200, [{"Kp": 1}, {"Kp": 2}])),               # empty feed
    (_Resp(200, [{"newkey": 1}]), _Resp(200, [{"Kp": 1}, {"Kp": 2}])),  # schema drift
    (ConnectionError("offline"), ConnectionError("offline")),          # no network
    (_Resp(200, [{"flux": 142}]), _Resp(200, [{"Kp": 1}, {"Kp": 42}])),  # impossible Kp
])
def test_failure_is_flagged_invalid_not_zero(monkeypatch, flux_resp, kp_resp):
    monkeypatch.setattr(solar_client.requests, 'get', _fake_get({
        SolarClient.URL_FLUX: flux_resp,
        SolarClient.URL_PLANETARY_K: kp_resp,
    }))
    data = SolarClient().get_solar_data()
    assert data['valid'] is False
    assert data['condx'] == 'Unavailable'
    assert 0 not in (data['sfi'], data['k'])   # never a fake zero
