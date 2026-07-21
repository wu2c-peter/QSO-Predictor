"""
Audio Doctor — Windows audio-path diagnostics for digital-mode operators.

Diagnoses the classic "WSJT-X went silent to the rig's USB codec" family of
failures: persisted per-app mixer mutes, communications ducking, default
device roles hijacked by monitor audio, stale re-enumerated endpoints, and
wrong endpoint formats.

Package layout mirrors the utils/ convention: `models`, `parsing` and
`checks` are pure stdlib (unit-testable on any platform); all COM / winreg
access is confined to `probe_windows`, which soft-imports its Windows-only
deps and is import-safe on every platform — gate at runtime with
`probe_windows.available()`.

QSO Predictor
Copyright (C) 2026 Peter Hirst (WU2C)
"""
