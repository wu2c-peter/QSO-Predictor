# QSO Predictor — IONIS Propagation Prediction
# Copyright (C) 2025-2026 Peter Hirst (WU2C)
#
# Propagation model by Greg Beam (KI7MT)
# Original: github.com/IONIS-AI (GPLv3)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""
IONIS propagation prediction for QSO Predictor.

Pure numpy inference of the IonisGate V22-gamma model (205K parameters,
trained on 20M WSPR observations). Predicts HF path viability from
grid squares, band, time, SFI, and Kp.

Usage:
    from ionis import IonisEngine

    engine = IonisEngine()
    if engine.is_available():
        result = engine.predict('FN42', 'JN48', '20m', sfi=142, kp=2)
"""

from .engine import IonisEngine
from .features import freq_to_band, BAND_FREQ_HZ, MODE_THRESHOLDS_DB

__all__ = ['IonisEngine', 'freq_to_band', 'BAND_FREQ_HZ',
           'MODE_THRESHOLDS_DB']
