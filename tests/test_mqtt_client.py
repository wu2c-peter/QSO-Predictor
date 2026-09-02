# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""PSK Reporter MQTT subscription bookkeeping and health reporting.

2026-09 audit: `unsubscribe("#")` matches nothing under MQTT's literal
filter semantics, so every band the operator visited stayed subscribed
for the whole session; an unknown dial frequency silently subscribed
to 20 m; FT4 always fetched FT8 spots; and a broker that was never
reachable looked healthy forever.
"""

import time

import pytest

from mqtt_client import MQTTClient


class FakePaho:
    """Just enough of paho.mqtt.client.Client to record subscriptions."""

    def __init__(self):
        self.connected = True
        self.subscribed = []
        self.unsubscribed = []

    def is_connected(self):
        return self.connected

    def subscribe(self, topics):
        self.subscribed.extend(t for t, _qos in topics)

    def unsubscribe(self, topics):
        self.unsubscribed.extend(topics)


@pytest.fixture
def client():
    c = MQTTClient()
    c.client = FakePaho()
    return c


def test_band_change_drops_the_previous_band(client):
    client.update_subscriptions('WU2C', 14074000)
    client.update_subscriptions('WU2C', 7074000)
    assert 'pskr/filter/v2/20m/FT8/#' in client.client.unsubscribed
    assert client.client.subscribed[-1:] == ['pskr/filter/v2/40m/FT8/#'] or \
        'pskr/filter/v2/40m/FT8/#' in client.client.subscribed
    assert client.desired_topics() == ['pskr/filter/v2/40m/FT8/#',
                                       'pskr/filter/v2/+/FT8/WU2C/#']
    # ledger reflects exactly what the broker now holds
    assert client._subscribed == client.desired_topics()


def test_callsign_change_drops_old_who_hears_me_topic(client):
    client.update_subscriptions('N0CALL', 14074000)
    client.update_subscriptions('WU2C', 14074000)
    assert 'pskr/filter/v2/+/FT8/N0CALL/#' in client.client.unsubscribed
    assert 'pskr/filter/v2/20m/FT8/#' not in client.client.unsubscribed  # unchanged


def test_ft4_uses_ft4_topics(client):
    client.update_subscriptions('WU2C', 14080000, mode='FT4')
    assert client.desired_topics() == ['pskr/filter/v2/20m/FT4/#',
                                       'pskr/filter/v2/+/FT4/WU2C/#']


def test_unknown_dial_subscribes_to_no_band(client):
    client.update_subscriptions('WU2C', 144174000)   # 2 m
    assert client.current_band is None
    assert client.desired_topics() == ['pskr/filter/v2/+/FT8/WU2C/#']


def test_never_connected_warns_after_grace(client):
    client.running = True
    client._start_time = time.time() - client._startup_grace - 1
    client.client.connected = False
    ok, msg = client.check_data_health()
    assert not ok and 'PSK Reporter' in msg


def test_never_connected_is_quiet_during_grace(client):
    client.running = True
    client._start_time = time.time()
    client.client.connected = False
    assert client.check_data_health() == (True, "")
