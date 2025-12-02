# QSO Predictor
# Copyright (C) 2025 [Peter Hirst/WU2C]

import json
import time
import paho.mqtt.client as mqtt
from PyQt6.QtCore import QObject, pyqtSignal

class MQTTClient(QObject):
    spot_received = pyqtSignal(dict)
    status_message = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.broker = "mqtt.pskreporter.info"
        self.port = 1883
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        
        self.my_call = "N0CALL"
        self.current_band = "20m"
        self.running = False

    def start(self):
        if self.running: return
        self.running = True
        try:
            self.status_message.emit("Connecting to Live Feed...")
            self.client.connect_async(self.broker, self.port, 60)
            self.client.loop_start()
        except Exception as e:
            self.status_message.emit(f"MQTT Error: {e}")

    def stop(self):
        self.running = False
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except: pass

    def update_subscriptions(self, my_call, freq_hz):
        self.my_call = my_call
        self.current_band = self._freq_to_band(freq_hz)
        
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
            self.status_message.emit(f"Live: {self.current_band} + {self.my_call}")
        except: pass

    def on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.status_message.emit("Connected to PSK Reporter MQTT")
            self._subscribe()
        else:
            self.status_message.emit(f"MQTT Connection Failed: {rc}")

    def on_disconnect(self, client, userdata, flags, rc, properties=None):
        self.status_message.emit("Live Feed Disconnected")

    def on_message(self, client, userdata, msg):
        try:
            # Payload Example: {"sc":"W1AW","rc":"K1ABC","f":14074123,"rp":-12,"t":1735000000,"rl":"FN42"}
            data = json.loads(msg.payload.decode())
            
            spot = {
                'sender': data.get('sc', 'Unknown'),
                'receiver': data.get('rc', 'Unknown'),
                'freq': data.get('f', 0),
                'snr': data.get('rp', -99),
                'grid': data.get('rl', ''), 
                'time': data.get('t', time.time())
            }
            self.spot_received.emit(spot)
        except: pass

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