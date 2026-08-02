---
layout: page
title: Integrations
permalink: /integrations/
description: >-
  How to run QSO Predictor alongside the apps you already use — WSJT-X, JTDX,
  GridTracker, JTAlert, FT8web, and your logger — with step-by-step UDP
  configuration guides.
---

QSO Predictor is designed to **join** your station, not replace anything in
it. Keep your logger, your map, and your alerts — QSOP listens to the same
WSJT-X/JTDX UDP stream they do and adds the one thing none of them show:
the DX station's side of the band.

These guides cover the exact settings for each combination, plus a
foundational guide to WSJT-X UDP routing that applies even if you never
install QSO Predictor.

## Guides

- **[Run WSJT-X with GridTracker, JTAlert, and your logger at the same
  time](/integrations/wsjtx-udp-multicast/)** — why only one app gets
  decodes, and the two topologies (multicast and daisy-chain) that fix it.
  Start here if apps are fighting over UDP port 2237.
- **[QSO Predictor + GridTracker](/integrations/gridtracker/)** — both
  recommended setups, verification steps, and troubleshooting.

More guides (JTAlert, JTDX, FT8web, loggers) are planned. If you want one
sooner, [say so on GitHub](https://github.com/wu2c-peter/qso-predictor/issues).

## The short version

Every app in this ecosystem consumes the same WSJT-X/JTDX "UDP Server"
stream. You have two good options:

1. **Multicast (recommended):** point WSJT-X at a multicast group
   (e.g. `239.255.0.0:2237`) and let every app subscribe independently.
   No app depends on any other.
2. **Daisy-chain:** each app listens on one port and forwards to the next
   (e.g. WSJT-X → 2237 GridTracker → 2238 QSO Predictor). Works well, but
   closing a middle app breaks the chain downstream.

QSO Predictor supports both — it can listen on unicast or multicast, and can
itself forward UDP onward (Settings → **UDP Forwarding**). Its built-in
**Network Doctor** (Diagnostics → Run Full Checkup) verifies the whole
chain link by link and names the broken hop when something stops flowing.
