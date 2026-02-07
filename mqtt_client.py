# QSO Predictor
# Copyright (C) 2025 Peter Hirst (WU2C)
#
# v2.1.1 Changes:
# - Added: check_data_health() method for resilient data source monitoring
# - Added: Timeout detection (60s threshold) with automatic warning/recovery
#
# v2.0.9 Changes:
# - Added: Proper logging throughout
# - Added: Periodic spot rate logging (every 60s) instead of per-spot

import json
import logging
import time
import paho.mqtt.client as mqtt
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)


class MQTTClient(QObject):
    spot_received = pyqtSignal(dict)
    status_message = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.broker = "mqtt.pskreporter.info"
        self.port = 1883
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        
        # FIX v2.0.4: Configure auto-reconnect with exponential backoff
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        
        self.my_call = "N0CALL"
        self.current_band = "20m"
        self.running = False
        
        # Track statistics for diagnostics and periodic logging
        self._spots_received = 0
        self._spots_since_last_log = 0
        self._last_spot_time = None
        self._last_stats_log_time = None
        self._stats_log_interval = 60  # Log spot rate every 60 seconds
        
        # v2.1.1: Timeout detection
        self._timeout_warned = False
        self._timeout_threshold = 60  # MQTT can be bursty, allow 60s before warning
        
        logger.debug(f"MQTT: Client initialized, broker={self.broker}:{self.port}")

    def start(self):
        if self.running: 
            logger.debug("MQTT: Already running, ignoring start()")
            return
        self.running = True
        try:
            logger.info(f"MQTT: Connecting to {self.broker}:{self.port}")
            self.status_message.emit("Connecting to Live Feed...")
            self.client.connect_async(self.broker, self.port, 60)
            self.client.loop_start()
        except Exception as e:
            logger.error(f"MQTT: Connection error - {e}")
            self.status_message.emit(f"MQTT Error: {e}")

    def stop(self):
        logger.info(f"MQTT: Stopping client (total spots received: {self._spots_received})")
        self.running = False
        try:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("MQTT: Client stopped")
        except Exception as e:
            logger.debug(f"MQTT: Error during stop: {e}")

    def update_subscriptions(self, my_call, freq_hz):
        old_call = self.my_call
        old_band = self.current_band
        
        self.my_call = my_call.upper()  # Normalize stored callsign
        self.current_band = self._freq_to_band(freq_hz)
        
        if old_call != self.my_call or old_band != self.current_band:
            logger.info(f"MQTT: Subscription update - call={self.my_call}, band={self.current_band}")
        
        if self.client.is_connected():
            self._subscribe()

    def _subscribe(self):
        # 1. Band Activity (Who is transmitting on my band?)
        topic_band = f"pskr/filter/v2/{self.current_band}/FT8/#"
        
        # 2. Who Hears Me? (Reverse Beacon - GLOBAL)
        topic_me = f"pskr/filter/v2/+/FT8/{self.my_call}/#"
        
        try:
            self.client.unsubscribe("#") 
            self.client.subscribe([(topic_band, 0), (topic_me, 0)])
            logger.info(f"MQTT: Subscribed to {topic_band} and {topic_me}")
            self.status_message.emit(f"Live: {self.current_band} + {self.my_call}")
        except Exception as e:
            logger.error(f"MQTT: Subscribe error - {e}")

    def on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info("MQTT: Connected to PSK Reporter")
            self.status_message.emit("Connected to PSK Reporter MQTT")
            self._subscribe()
        else:
            logger.warning(f"MQTT: Connection failed with code {rc}")
            self.status_message.emit(f"MQTT Connection Failed: {rc}")

    def on_disconnect(self, client, userdata, flags, rc, properties=None):
        logger.warning(f"MQTT: Disconnected (rc={rc}, total spots received: {self._spots_received})")
        self.status_message.emit("Live Feed Disconnected")
        # FIX v2.0.4: Auto-reconnect on unexpected disconnect
        if self.running and rc != 0:  # rc=0 means clean disconnect
            logger.info("MQTT: Unexpected disconnect, attempting reconnect...")
            self.status_message.emit("Attempting reconnect...")
            try:
                self.client.reconnect()
            except Exception as e:
                logger.warning(f"MQTT: Reconnect failed - {e} - will retry")
                self.status_message.emit(f"Reconnect failed: {e} - will retry")

    def on_message(self, client, userdata, msg):
        try:
            # Payload Example: {"sc":"W1AW","rc":"K1ABC","f":14074123,"rp":-12,"t":1735000000,"rl":"FN42"}
            data = json.loads(msg.payload.decode())
            
            # FIX v2.0.4: Sanitize timestamp - must be valid number
            # PSK Reporter sometimes sends null or invalid timestamps
            spot_time = data.get('t')
            if not isinstance(spot_time, (int, float)) or spot_time <= 0:
                spot_time = time.time()
            
            # FIX: Normalize callsigns and grid to uppercase at ingestion
            # This ensures all downstream comparisons work regardless of PSK Reporter's case
            spot = {
                'sender': data.get('sc', 'Unknown').upper(),
                'receiver': data.get('rc', 'Unknown').upper(),
                'freq': data.get('f', 0),
                'snr': data.get('rp', -99),
                'grid': data.get('rl', '').upper(),  # Receiver grid
                'sender_grid': data.get('sl', '').upper(),  # Sender grid (v2.1.0: for near-me detection)
                'time': time.time(),          # Receipt time for freshness filtering
                'pskr_time': spot_time,       # Original PSK Reporter timestamp
            }
            
            
        

            self._spots_received += 1
            self._spots_since_last_log += 1
            self._last_spot_time = time.time()
            
            # Log first spot to confirm data is flowing
            if self._spots_received == 1:
                logger.info(f"MQTT: First spot received - {spot['sender']} -> {spot['receiver']} {spot['snr']}dB")
                logger.info("MQTT: Spots are flowing (individual spots not logged to reduce verbosity)")
            
            # Periodic stats logging (every 60 seconds when debug enabled)
            now = time.time()
            if self._last_stats_log_time is None:
                self._last_stats_log_time = now
            elif now - self._last_stats_log_time >= self._stats_log_interval:
                rate = self._spots_since_last_log / (now - self._last_stats_log_time) * 60
                logger.debug(f"MQTT: Spot rate: {rate:.1f}/min (total: {self._spots_received})")
                self._spots_since_last_log = 0
                self._last_stats_log_time = now
            
            self.spot_received.emit(spot)
        except json.JSONDecodeError as e:
            logger.debug(f"MQTT: JSON decode error - {e}")
        except Exception as e:
            logger.debug(f"MQTT: Message processing error - {e}")

    def _freq_to_band(self, freq):
        f = freq / 1_000_000
        if 1.8 <= f <= 2.0: return "160m"
        if 3.5 <= f <= 4.0: return "80m"
        if 5.3 <= f <= 5.4: return "60m"
        if 7.0 <= f <= 7.3: return "40m"
        if 10.1 <= f <= 10.15: return "30m"
        if 14.0 <= f <= 14.35: return "20m"
        if 18.068 <= f <= 18.168: return "17m"
        if 21.0 <= f <= 21.45: return "15m"
        if 24.89 <= f <= 24.99: return "12m"
        if 28.0 <= f <= 29.7: return "10m"
        if 50.0 <= f <= 54.0: return "6m"
        return "20m"
    
    def get_diagnostics(self) -> dict:
        """Return diagnostic information about MQTT status."""
        return {
            'broker': self.broker,
            'port': self.port,
            'running': self.running,
            'connected': self.client.is_connected() if self.client else False,
            'my_call': self.my_call,
            'current_band': self.current_band,
            'spots_received': self._spots_received,
            'last_spot_age': (time.time() - self._last_spot_time) if self._last_spot_time else None,
        }
    
    def check_data_health(self) -> tuple:
        """v2.1.1: Check if MQTT spot data is flowing. Returns (is_healthy, message).
        
        Called periodically by main window to detect data source failures.
        Returns:
            (True, "") if data is flowing or not yet connected
            (False, "warning message") if data has stopped
        """
        if not self.running:
            return (True, "")
        
        # If never connected or no spots yet, don't warn
        # (MQTT can take a moment to connect and receive first spot)
        if self._last_spot_time is None:
            return (True, "")
        
        age = time.time() - self._last_spot_time
        if age > self._timeout_threshold:
            if not self._timeout_warned:
                self._timeout_warned = True
                connected = self.client.is_connected() if self.client else False
                logger.warning(f"MQTT: No spots received for {age:.0f}s (connected={connected})")
            connected = self.client.is_connected() if self.client else False
            if not connected:
                return (False, "⚠ PSK Reporter disconnected — check internet")
            else:
                return (False, f"⚠ No MQTT spots for {int(age)}s — feed may be stalled")
        else:
            if self._timeout_warned:
                self._timeout_warned = False
                logger.info("MQTT: Spot flow resumed")
            return (True, "")
