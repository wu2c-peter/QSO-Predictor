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

# We listen on Port 2238 (The one GridTracker should be sending to)
UDP_IP = "127.0.0.1"
UDP_PORT = 2238

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    sock.bind((UDP_IP, UDP_PORT))
    print(f"--- DEBUG LISTENER RUNNING ---")
    print(f"Listening on {UDP_IP}:{UDP_PORT}")
    print(f"Waiting for GridTracker to send data...")
    print(f"(Press Ctrl+C to stop)")
    
    while True:
        data, addr = sock.recvfrom(4096)
        print(f"SUCCESS! Received {len(data)} bytes from {addr}")
        
except Exception as e:
    print(f"CRITICAL ERROR: Could not bind to port {UDP_PORT}")
    print(f"Reason: {e}")
    print("Is the main app still running? Close it first!")
    input("Press Enter to exit...")

