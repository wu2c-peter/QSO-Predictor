# Release Notes — v2.8.0

**Date:** August 2026
**Theme:** Click-to-call, bulletproof UDP, and the integration guides

---

## Summary

v2.8.0 closes the loop the product opens: QSO Predictor tells you who
to call — now double-clicking that station sets the call up in WSJT-X.
Underneath it, a week of live dogfooding (a real four-app multicast
migration on the author's station) hardened the entire UDP layer:
multicast reception that survives VPN adapters, a Network Doctor check
for silently-shared ports, cross-machine forwarding, and a string of
corrected in-app guidance. New `/integrations/` guides on
qsop.wu2c.net document the whole WSJT-X UDP ecosystem.

## Click-to-call

Double-click a callsign — in the decode table or on the target
dashboard — and it's set up in WSJT-X. No window switching, no helper
scripts, all platforms:

- **Fresh CQ (within ~45 s)** → QSOP sends a UDP *Reply*: WSJT-X
  behaves exactly as if you double-clicked that decode in its own Band
  Activity window, including enabling TX if your WSJT-X "double-click
  on call sets Tx enable" option is on.
- **Anyone else** → QSOP sends a UDP *Configure*: DX Call and grid
  fill, standard messages generate, and **you** press Enable TX. This
  works for any callsign — not just CQers — which is more than the
  Reply-based click-to-call in other companion apps can do.
- **Single-click keeps its old meaning everywhere** (row click sets
  the QSOP target; dashboard callsign click copies to clipboard).
- **JTDX**: replying to CQs works; JTDX predates the Configure message
  and ignores it, so for non-CQ stations QSOP copies the callsign to
  the clipboard and says so — one paste finishes the job (and the
  auto-paste scripts in the User Guide complete it automatically).
- QSO Predictor **never transmits on its own** — TX only ever starts
  from your double-click, governed by your own WSJT-X settings.
- Requires hearing WSJT-X directly (multicast or direct unicast).
  Behind a forwarder, QSOP explains rather than failing silently.
- The TX offset stays manual by design (no UDP message exists for
  it) — click the recommended frequency to copy it, paste into the
  spinner. The User Guide's auto-paste scripts are updated: WSJT-X
  callsign pasting is retired (UDP does it better), frequency pasting
  and JTDX callsign completion remain.

## UDP robustness (found the hard way)

- **Multicast reception joins every interface.** A single default join
  can land on an idle VPN adapter (observed live: NordVPN's NordLynx
  at a lower route metric than Ethernet) leaving QSOP deaf while other
  apps on the same group receive. QSOP now joins the group on
  loopback, the default route, and every local address — and logs
  which.
- **Requests reply to WSJT-X's real socket.** WSJT-X accepts commands
  only on the ephemeral socket it transmits from — never its
  configured server port. Click-to-call routes accordingly.
- **New Network Doctor check: "Shared unicast ports."** Windows lets
  several apps bind one unicast port without error, but delivers each
  packet to only the most-specific binding — one app silently starves
  (observed live: JTAlert's 127.0.0.1 bind captured the stream from
  GridTracker, and everything downstream). The Full Checkup now names
  the winner and the starved apps. Multicast stations, where sharing
  is legitimate, are never flagged.
- **Cross-machine forwarding.** The UDP forward list now accepts
  `host:port` entries (`192.168.1.50:2237`) alongside bare ports
  (which keep meaning this PC — existing configs unchanged). Multicast
  doesn't traverse Wi-Fi/routers reliably; unicast chains do. The
  FT8web rebroadcast also gained the self-forward loop filter.
- **Live callsign/grid changes.** Changing your station identity in
  Settings now applies immediately — analyzer caches cleared, MQTT
  who-hears-me topic resubscribed, outcome recording switched — no
  restart (Local Intelligence still binds at startup; the status bar
  says so).
- **Settings-save fix**: saving Settings no longer stacks duplicate
  signal connections (spots were processed once extra per save).

## Corrected guidance (in-app and docs)

- The multicast example address everywhere (Settings help, the
  Multicast preset, User Guide, wiki) was `239.0.0.2` — an address
  WSJT-X rejects as "MAC-ambiguous". Now `239.255.0.0`, with the
  rejection explained so the error message is searchable.
- Auto-Detect's port-conflict advice recommended the WSJT-X/JTDX
  "secondary UDP server" as a decode feed — that server broadcasts
  logged QSOs only, never decodes. The advice (and the same error in
  the User Guide's and wiki's multi-app instructions) now offers the
  real options: forwarding, or one multicast group.
- Settings → Network help text no longer renders clipped.

## Silent-TX warning: two strikes before it shows

The automatic silent-TX monitor (Windows) now requires **two
consecutive** silent probes before the status-bar warning appears — a
single quiet cycle (Halt TX, mid-cycle band change) is logged and
confirmed against the next transmission instead of flashing a warning
that self-clears. If you see the banner at all, it now means two
transmissions in a row measured silent.

## New: integration guides on qsop.wu2c.net

- [Run WSJT-X with GridTracker, JTAlert, and your logger at the same
  time](https://qsop.wu2c.net/integrations/wsjtx-udp-multicast/) —
  why only one app gets decodes, multicast vs daisy-chain, exact
  settings, multi-machine patterns, and a troubleshooting table built
  from failures that actually happened.
- [QSO Predictor + GridTracker](https://qsop.wu2c.net/integrations/gridtracker/)
  — both topologies with verified settings labels.

All third-party settings names verified against live GridTracker and
JTAlert 2.81.10.
