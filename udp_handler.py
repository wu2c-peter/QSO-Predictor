# QSO Predictor
# Copyright (C) 2025 [Peter Hirst/WU2C]
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.


import socket
import threading
import struct
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox

class UDPHandler(QObject):
    new_decode = pyqtSignal(dict)
    status_update = pyqtSignal(dict)

    def __init__(self, config):
        super().__init__()
        self.ip = "0.0.0.0" 
        self.port = int(config.get('NETWORK', 'udp_port'))
        self.forward_ports = config.get_forward_ports()
        self.running = False
        
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.bind((self.ip, self.port))
        except Exception as e:
            print(f"Bind Error: {e}")

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        try: self.sock.close()
        except: pass

    def _listen_loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                self._forward_packet(data)
                self._parse_packet(data)
            except OSError: break
            except Exception: pass

    def _forward_packet(self, data):
        for port in self.forward_ports:
            try: self.sock.sendto(data, ('127.0.0.1', port))
            except: pass

    def _parse_packet(self, data):
        if len(data) < 12: return
        magic = struct.unpack('>I', data[0:4])[0]
        if magic != 2914763738 and magic != 2914831322: return

        try:
            msg_type = struct.unpack('>I', data[8:12])[0]
            if msg_type == 1: # Status
                self._process_status(data)
            elif msg_type == 2: # Decode
                self._process_decode(data)
        except: pass

    def _process_status(self, data):
        idx = 12
        def read_utf8(d, i):
            l = struct.unpack('>I', d[i:i+4])[0]
            i += 4
            if l == 0xFFFFFFFF: return None, i
            if l == 0: return "", i
            return d[i:i+l].decode('utf-8', errors='replace'), i+l

        try:
            # 1. ID
            _, idx = read_utf8(data, idx) 
            # 2. Dial Freq (8 bytes)
            dial_freq = struct.unpack('>Q', data[idx:idx+8])[0]
            idx += 8
            # 3. Mode (utf8)
            _, idx = read_utf8(data, idx)
            # 4. DX Call (utf8) <--- THIS IS WHAT WE WANT
            dx_call, idx = read_utf8(data, idx)
            
            self.status_update.emit({
                'dial_freq': dial_freq,
                'dx_call': dx_call
            })
        except: pass

    def _process_decode(self, data):
        idx = 12
        def read_utf8(d, i):
            l = struct.unpack('>I', d[i:i+4])[0]
            i += 4
            if l == 0xFFFFFFFF: return None, i
            if l == 0: return "", i
            return d[i:i+l].decode('utf-8', errors='replace'), i+l

        try:
            _, idx = read_utf8(data, idx) # ID
            idx += 1 # New
            ms_midnight = struct.unpack('>I', data[idx:idx+4])[0]
            idx += 4
            hours = ms_midnight // 3600000
            mins = (ms_midnight % 3600000) // 60000
            time_str = f"{hours:02d}{mins:02d}"
            
            snr = struct.unpack('>i', data[idx:idx+4])[0]
            idx += 4
            dt = struct.unpack('>d', data[idx:idx+8])[0]
            idx += 8
            freq = struct.unpack('>I', data[idx:idx+4])[0]
            idx += 4
            mode, idx = read_utf8(data, idx)
            message, idx = read_utf8(data, idx)
            
            parts = message.strip().split()
            grid = ""
            call = ""
            if len(parts) >= 3:
                if len(parts[-1]) == 4 and parts[-1][0].isalpha() and parts[-1][2].isdigit():
                    grid = parts[-1]
                    call = parts[-2]
                else:
                    call = parts[-1]
            
            self.new_decode.emit({
                'time': time_str, 'snr': snr, 'dt': round(dt, 1),
                'freq': freq, 'mode': mode, 'message': message,
                'call': call, 'grid': grid
            })
        except: pass


