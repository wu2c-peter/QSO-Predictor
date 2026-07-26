"""
Small in-package doctors, one module each (dev-docs/DIAGNOSTICS_SPEC.md).

Each doctor is a pure interpreter over a StationSnapshot — no I/O, no
Qt (enforced by tests/test_conventions.py). Their probes live in the
package's probe_* modules; registration is assembled by the consumer.

QSO Predictor
Copyright (C) 2026 Peter Hirst (WU2C)
"""
