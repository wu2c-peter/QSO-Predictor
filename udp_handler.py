# QSO Predictor
# Copyright (C) 2025 [Peter Hirst/WU2C]

import socket
import threading
import struct
from PyQt6.QtCore import QObject, pyqtSignal

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
            print(f"UDP Bound to {self.port}")
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
        except Exception as e:
            print(f"Header Error: {e}")

    def _read_utf8(self, data, idx):
        if idx + 4 > len(data): return "", idx
        length = struct.unpack('>I', data[idx:idx+4])[0]
        idx += 4
        if length == 0xFFFFFFFF: return None, idx
        if length == 0: return "", idx
        
        if idx + length > len(data): return "", idx
        val = data[idx:idx+length].decode('utf-8', errors='replace')
        return val, idx + length

    def _process_status(self, data):
        idx = 12 
        try:
            # 1. ID
            _, idx = self._read_utf8(data, idx) 
            # 2. Dial Freq
            dial_freq = struct.unpack('>Q', data[idx:idx+8])[0]
            idx += 8
            # 3. Mode
            _, idx = self._read_utf8(data, idx)
            # 4. DX Call
            dx_call, idx = self._read_utf8(data, idx)
            # 5. Report
            _, idx = self._read_utf8(data, idx)
            # 6. Tx Mode
            _, idx = self._read_utf8(data, idx)
            # 7. Tx Enabled
            idx += 1 
            # 8. Transmitting
            idx += 1
            # 9. Decoding
            idx += 1
            # 10. Rx DF
            idx += 4
            
            # 11. Tx DF
            if idx + 4 <= len(data):
                tx_df = struct.unpack('>I', data[idx:idx+4])[0]
                self.status_update.emit({
                    'dial_freq': dial_freq,
                    'dx_call': dx_call,
                    'tx_df': tx_df
                })
        except: pass

    def _process_decode(self, data):
        idx = 12 
        try:
            # 1. ID
            _, idx = self._read_utf8(data, idx)
            # 2. New
            idx += 1 
            # 3. Time
            ms_midnight = struct.unpack('>I', data[idx:idx+4])[0]
            idx += 4
            hours = ms_midnight // 3600000
            mins = (ms_midnight % 3600000) // 60000
            time_str = f"{hours:02d}{mins:02d}"
            # 4. SNR
            snr = struct.unpack('>i', data[idx:idx+4])[0]
            idx += 4
            # 5. DT
            dt = struct.unpack('>d', data[idx:idx+8])[0]
            idx += 8
            # 6. Freq
            freq = struct.unpack('>I', data[idx:idx+4])[0]
            idx += 4
            # 7. Mode
            mode, idx = self._read_utf8(data, idx)
            # 8. Message
            message, idx = self._read_utf8(data, idx)
            
            # --- IMPROVED PARSING LOGIC ---
            parts = message.strip().split()
            grid = ""
            call = ""

            # Helper to identify common suffixes that are NOT callsigns
            def is_suffix(s):
                s = s.upper()
                # Standard endings
                if s in ['73', 'RR73', 'RRR']: return True
                # Signal reports (e.g., -10, +05, R-15)
                if s.startswith(('+', '-', 'R+', 'R-')) and len(s) > 1: return True
                return False

            # Helper to identify a Grid (4 chars, Alpha-Alpha-Digit-Digit, e.g., FN42)
            def is_grid(s):
                if len(s) != 4: return False
                return s[0].isalpha() and s[1].isalpha() and s[2].isdigit() and s[3].isdigit()

            if len(parts) >= 3:
                # Pattern: [TARGET] [SENDER] [GRID/SUFFIX]
                last = parts[-1]
                
                if is_grid(last):
                    grid = last
                    call = parts[-2]
                elif is_suffix(last):
                    call = parts[-2]
                else:
                    # Fallback: ambiguous, assume last part is call (e.g. CQ DX CALL)
                    # unless it looks like a country prefix, but simple fallback is usually safest
                    call = last 
                    
            elif len(parts) == 2:
                # Pattern: [TARGET] [SENDER] or [CQ] [SENDER]
                # Usually the second item is the sender
                call = parts[1]

            # Cleanup callsign (strip <> if present, e.g. <W1ABC>)
            call = call.strip('<>')
            
            # ------------------------------
            
            self.new_decode.emit({
                'time': time_str, 'snr': snr, 'dt': round(dt, 1),
                'freq': freq, 'mode': mode, 'message': message,
                'call': call, 'grid': grid
            })
        except Exception as e:
            # It's good to at least print errors during debugging so you know if packets are failing
            print(f"Decode Error: {e}")