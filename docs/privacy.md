---
layout: page
title: Privacy Policy
permalink: /privacy/
---


# Privacy Policy

**Last updated:** April 20, 2026

## Summary

QSO Predictor does not collect, store, or transmit any personal information. The application runs entirely on your local device and reads data only from sources you already use (your own WSJT-X/JTDX log files) and public amateur radio data services (PSK Reporter, NOAA).

## Data we access

**Local log files.** QSO Predictor reads `ALL.TXT` files produced by WSJT-X and JTDX to analyze historical station behavior and provide tactical recommendations. These files remain on your device; QSO Predictor does not upload their contents anywhere.

**PSK Reporter MQTT stream.** QSO Predictor subscribes to the public PSK Reporter live spot stream to display real-time amateur radio reception data. This is a read-only connection — QSO Predictor does not upload anything to PSK Reporter.

**NOAA Space Weather API.** QSO Predictor fetches public solar flux (SFI) and geomagnetic index (Kp) data from the NOAA Space Weather Prediction Center to display band condition context. No identifying information is sent in these requests.

## Data we store locally

QSO Predictor stores the following files on your device only:

- **Configuration settings** (`qso_predictor.ini`) — your callsign, grid, UI preferences, connection settings
- **Behavior history** (`behavior_history.json`) — patterns learned from your own log files about stations you have observed on the air
- **Outcome data** (`outcome_history.jsonl`) — records of your own QSO attempts, used for local self-evaluation features

None of this data is transmitted anywhere. You can inspect or delete any of these files at any time. They are stored in:

- Windows: `%USERPROFILE%\.qso-predictor\` and `%APPDATA%\QSO Predictor\`
- macOS: `~/.qso-predictor/` and `~/Library/Application Support/QSO Predictor/`
- Linux: `~/.qso-predictor/` and `~/.config/QSO Predictor/`

## Data we do not collect

QSO Predictor does not:

- Transmit telemetry or analytics
- Use crash reporting services
- Track usage patterns
- Register with any remote service
- Send or store your callsign beyond your local configuration
- Interact with advertising networks
- Create user accounts

## Third-party services

QSO Predictor connects to these external services at runtime:

- **PSK Reporter** — [pskreporter.info](https://pskreporter.info) (read-only MQTT subscription to public spot data)
- **NOAA Space Weather Prediction Center** — read-only public API for solar and geomagnetic data (US government public-domain data)

Please review those services' own privacy policies if you have concerns about their handling of public amateur radio data.

## Contact

Questions about this privacy policy? Please open an issue on the project's [GitHub Issues page](https://github.com/wu2c-peter/qso-predictor/issues).

## Changes to this policy

If this privacy policy changes materially, this document will be updated with a new "Last updated" date. Existing users will not be notified directly; you are encouraged to review this page when you update QSO Predictor.

## Verification

QSO Predictor is open-source software licensed under GPLv3. The complete source code is available at [github.com/wu2c-peter/qso-predictor](https://github.com/wu2c-peter/qso-predictor) for independent verification of every claim in this policy.

---

73 de WU2C
