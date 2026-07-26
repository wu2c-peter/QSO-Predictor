"""
Diagnostics framework core — shared types for the per-subsystem "Doctors"
(Audio Doctor today; Clock/Config/Network/Serial/System Doctors planned).

Design: dev-docs/DIAGNOSTICS_SPEC.md. Standing constraints, enforced by
tests/test_conventions.py:

- Nothing in this package imports Qt or main-app modules. A future
  standalone/headless tester must be buildable from this package alone,
  and doctors' check logic must stay unit-testable on any platform.
- Platform access (COM, registry, netstat, ...) is confined to
  `probe_*` modules, mirroring the audio_doctor convention.

QSO Predictor
Copyright (C) 2026 Peter Hirst (WU2C)
"""
