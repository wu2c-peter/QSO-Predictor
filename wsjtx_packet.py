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


import struct

class WsjtxPacketReader:
    """Parses WSJT-X/JTDX UDP packets serialized with Qt's QDataStream."""
    def __init__(self, data):
        self.data = data
        self.offset = 0

    def _unpack(self, fmt, size):
        if self.offset + size > len(self.data):
            raise ValueError("Packet too short")
        val = struct.unpack(fmt, self.data[self.offset:self.offset + size])[0]
        self.offset += size
        return val

    def read_bool(self):
        return self._unpack('?', 1)

    def read_qint32(self):
        return self._unpack('>i', 4)

    def read_quint32(self):
        return self._unpack('>I', 4)

    def read_double(self):
        return self._unpack('>d', 8)

    def read_utf8(self):
        length = self.read_quint32()
        if length == 0xFFFFFFFF: return None
        if length == 0: return ""
        str_bytes = self.data[self.offset:self.offset + length]
        self.offset += length
        return str_bytes.decode('utf-8', errors='replace')

    def read_qtime(self):
        ms_midnight = self.read_quint32()
        hours = ms_midnight // 3600000
        mins = (ms_midnight % 3600000) // 60000
        return f"{hours:02d}{mins:02d}"

    def check_magic(self):
        magic = self.read_quint32()
        return magic == 2914763738

