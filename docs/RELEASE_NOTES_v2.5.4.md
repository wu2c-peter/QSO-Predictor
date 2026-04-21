# Release Notes — v2.5.4

**Release date:** April 2026
**Type:** Polish release (privacy policy infrastructure and Microsoft Store preparation)

## Overview

Small polish release focused on privacy transparency and preparing the project for Microsoft Store distribution. No behavioral changes to scoring, decoding, or propagation analysis.

## Changes

### New

- **Privacy Policy document** (`PRIVACY.md`) at repository root. Comprehensive statement of what QSO Predictor does and does not do with your data. Explicit summary: QSOP does not collect, store, or transmit personal information. All data stays on your local device.
- **Privacy Policy link in About dialog.** Help → About now includes a direct link to the privacy policy, alongside a "no telemetry, no tracking" tagline.
- **Privacy references throughout documentation:** README.md Privacy section, User Guide data-upload FAQ with privacy link, User Guide Getting Help section, Wiki Home page Links.

### Unchanged

- All scoring, path analysis, IONIS propagation, Hunt Mode, Fox/Hound/SuperHound, OutcomeRecorder behavior — identical to v2.5.3.
- All UDP, MQTT, and log parsing code paths — identical to v2.5.3.
- Configuration and data file formats — identical to v2.5.3.

## Upgrade notes

Drop-in replacement for v2.5.3. No configuration changes required. Existing `qso_predictor.ini`, `behavior_history.json`, and `outcome_history.jsonl` are fully compatible.

## Microsoft Store preparation

This release prepares the groundwork for QSO Predictor distribution via the Microsoft Store. Identity values reserved in Partner Center, privacy policy URL suitable for Store submission, in-app privacy link demonstrating Microsoft Store policy compliance.

GitHub direct-download distribution continues unchanged — the Microsoft Store is an additional channel, not a replacement.

---

73 de WU2C
