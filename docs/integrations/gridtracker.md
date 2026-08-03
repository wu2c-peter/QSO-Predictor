---
layout: page
title: "Using QSO Predictor with GridTracker"
permalink: /integrations/gridtracker/
description: >-
  Run GridTracker and QSO Predictor side by side on one WSJT-X or JTDX
  stream: multicast and daisy-chain configurations with exact settings,
  verification steps, and troubleshooting. Keep your map — add the DX
  station's perspective.
---

*Last updated 2026-08-01 · Tested with WSJT-X 2.7.x, GridTracker,
QSO Predictor 2.7.1 on Windows 11 (this is the author's own daily-driver
station configuration).*

GridTracker and [QSO Predictor](https://qsop.wu2c.net/) don't compete —
they look in opposite directions. GridTracker shows **your** side of the
band: who you've decoded, where they are on the map, what you've logged.
QSO Predictor reconstructs the **DX station's** side from live PSK
Reporter data: the pileup they're hearing (including callers you can't
hear), whether your signal reaches their region, and which frequencies are
clear at *their* location. Run together, you see both ends of the QSO.

Both apps consume the same WSJT-X/JTDX UDP stream, so the only real
question is how to share it. Two working setups follow — if you're new to
WSJT-X UDP routing or things currently only work for one app at a time,
read [the multicast guide](/integrations/wsjtx-udp-multicast/) first for
the full background.

## Setup A: Multicast (recommended)

Both apps subscribe to the same multicast group independently. Either can
start, stop, or crash without affecting the other.

```
WSJT-X (UDP Server 239.255.0.0:2237)
   ├────────────► GridTracker   (multicast 239.255.0.0:2237)
   └────────────► QSO Predictor (multicast 239.255.0.0:2237)
```

**WSJT-X — File → Settings → Reporting:**

| Setting | Value |
|---|---|
| UDP Server | `239.255.0.0` |
| UDP Server port number | `2237` |
| Outgoing interfaces | your **network adapter** (see note) |
| Multicast TTL | `1` |
| Accept UDP requests | ✅ |

> **Interface note:** QSO Predictor 2.7.1 and earlier join the multicast
> group on the default network adapter, so loopback-only transmission
> won't reach it — select your real adapter (Ethernet/Wi-Fi) in
> "Outgoing interfaces", optionally alongside loopback. TTL 1 keeps the
> traffic from leaving your own subnet.

**GridTracker — Settings (gear) → General tab, "Receive UDP Messages"
panel:**

| Setting | Value |
|---|---|
| Multicast? | ✅ ticked |
| IP | `239.255.0.0` |
| Port | `2237` |

**QSO Predictor — Settings → Network:**

| Setting | Value |
|---|---|
| Listen IP | `239.255.0.0` |
| Listen Port | `2237` |

On macOS, sharing one multicast group between apps needs `SO_REUSEPORT`;
QSO Predictor handles this automatically (v2.5.5.1+).

## Setup B: Daisy-chain through GridTracker

If you'd rather not touch multicast, let GridTracker receive the unicast
stream and forward a copy onward. This is the configuration the author
runs daily.

```
WSJT-X ──► 2237 GridTracker ──► 2238 QSO Predictor
                (listen 2237, forward to 2238)
```

**WSJT-X — Settings → Reporting:** UDP Server `127.0.0.1`, port `2237`,
"Accept UDP requests" checked.

**GridTracker:** receive on `127.0.0.1:2237` (its default), then in the
"Forward UDP Messages" panel (Settings → General tab) tick **Enabled?**
and set IP `127.0.0.1`, Port `2238`.

**QSO Predictor — Settings → Network:** Listen IP `127.0.0.1`, Listen
Port `2238`.

The specific ports are arbitrary — only the pattern matters: WSJT-X sends
to GridTracker's listen port, GridTracker forwards to QSO Predictor's
listen port. (Chains like WSJT-X → `4242` → GridTracker → `2238` → QSOP
work identically.)

The reverse order also works — QSO Predictor can be the first hop and
forward to GridTracker instead: QSOP listens on `2237` and forwards via
Settings → Network → **UDP Forwarding** → "Forward to ports: `2238`"
(its default), with GridTracker listening on `2238`.

**Two drawbacks vs Setup A:** the middle app is a single point of
failure — close GridTracker in Setup B and QSO Predictor goes silent
(not broken, just unfed), and vice versa in the reverse order. And the
downstream app loses its interactive features: forwarded streams are
one-way, so QSO Predictor's click-to-call (v2.8+) can't reach WSJT-X
from behind GridTracker's forwarder. If either bites, switch to
Setup A.

## Verify it's working

1. WSJT-X decoding normally (Band Activity fills each 15 s cycle).
2. GridTracker's map/call roster updates within one cycle.
3. QSO Predictor's status bar shows "Tracking N stations" and its decode
   table fills. On a healthy station this appears within ~30 seconds of
   the first decode cycle.
4. Double-click a station in WSJT-X: GridTracker highlights it, and QSO
   Predictor sets it as the target and begins the target-side analysis.

If any link is dead, run QSO Predictor's **Network Doctor**
(Diagnostics → Run Full Checkup). It walks the actual decode chain — who is configured to
send where, whether anything is listening there — and names the broken
hop in plain language, e.g. "GridTracker isn't running, so nothing
reaches QSO Predictor." Unusual-but-consistent port choices are treated
as healthy, not flagged.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| QSOP silent, GridTracker fine (Setup B) | GridTracker forwarding disabled, or forward port ≠ QSOP listen port | Enable forwarding; make the two numbers match |
| QSOP silent since GridTracker closed | Daisy-chain single point of failure | Restart GridTracker, or move to multicast (Setup A) |
| Both silent after multicast switch | WSJT-X "Outgoing interfaces" not on loopback | Select loopback in WSJT-X Reporting settings |
| GridTracker fine, QSOP shows "No data from WSJT-X/JTDX" warning | QSOP listening on the wrong port/IP for your topology | Match QSOP's Listen IP/Port to the stream (2237 group in Setup A, forward port in Setup B) |
| Everything dies when a VPN connects | VPN routing/multicast interference | Keep the chain on `127.0.0.1` (Setup B), or exclude 239.x from the VPN |
| First-run Windows firewall prompt was dismissed | App blocked for private networks | Re-allow in Windows Defender Firewall |

Logged-QSO housekeeping: when a QSO is logged, both apps hear the same
UDP logging message — GridTracker records it, and QSO Predictor can
auto-clear the current target if you've enabled "Auto-clear on QSO" in
its settings. No double-entry, no conflict.

## See also

- [Run WSJT-X with GridTracker, JTAlert, and your logger at the same
  time](/integrations/wsjtx-udp-multicast/) — the full UDP routing guide.
- [QSO Predictor User Guide](/user-guide/) — what the target-side display
  is telling you once data flows.
