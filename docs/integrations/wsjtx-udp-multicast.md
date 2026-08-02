---
layout: page
title: "Run WSJT-X with GridTracker, JTAlert, and Your Logger at the Same Time"
permalink: /integrations/wsjtx-udp-multicast/
description: >-
  Only one app receives WSJT-X decodes? How to share the WSJT-X / JTDX UDP
  stream with GridTracker, JTAlert, QSO Predictor, and your logger — using
  UDP multicast (recommended) or a forwarding daisy-chain. Exact settings,
  verification steps, and troubleshooting.
---

*Last updated 2026-08-01 · Tested with WSJT-X 2.7.x, GridTracker,
JTAlert, QSO Predictor 2.7.1 on Windows 11 and macOS.*

You install a second FT8 companion app and suddenly the first one goes
quiet: GridTracker's map stops updating, JTAlert shows no decodes, or the
new app complains it can't bind its port. Nothing is broken — you've hit a
design property of WSJT-X's UDP interface, and there are two clean ways
around it.

This guide applies to WSJT-X and JTDX equally (JTDX inherited the same UDP
interface). It is useful whether or not you run
[QSO Predictor](https://qsop.wu2c.net/) — QSOP is simply one more listener,
configured the same way as the rest.

## Why only one app gets the decodes

By default WSJT-X sends its UDP stream to a single address and port
(`127.0.0.1:2237`), and **only one application can own a plain unicast
port at a time**. Whichever app binds 2237 first wins; everything else
either receives nothing or fails to start listening. Symptoms:

- Decodes appear in one companion app but not the other.
- An app works until you launch a second one, then goes silent.
- "Address already in use" / bind errors in an app's log.
- Apps behave differently depending on launch order.

Two topologies fix this properly: **multicast** (every app subscribes
independently) or a **daisy-chain** (each app forwards to the next).

## Option 1: Multicast (recommended)

One setting change in WSJT-X, one in each listener. Any app can start,
stop, or crash without affecting the others.

```
                   ┌────────────► GridTracker   (join 239.255.0.0:2237)
WSJT-X ────────────┼────────────► JTAlert       (join 239.255.0.0:2237)
  UDP Server:      ├────────────► QSO Predictor (join 239.255.0.0:2237)
  239.255.0.0:2237 └────────────► Logger        (join 239.255.0.0:2237)
```

### WSJT-X settings

**File → Settings → Reporting**, "UDP Server" section:

| Setting | Value |
|---|---|
| UDP Server | `239.255.0.0` |
| UDP Server port number | `2237` |
| Outgoing interfaces | select the **loopback** entry (`loopback_0` on Windows, `lo0` on macOS, `lo` on Linux) |
| Multicast TTL | `1` |
| Accept UDP requests | ✅ checked |

Notes:

- Most addresses in `239.0.0.0`–`239.255.255.255` work, **but not all**:
  WSJT-X rejects groups of the form `x.0.0.y` or `x.128.0.y` (e.g.
  `239.0.0.2`) with the error *"MAC-ambiguous multicast groups addresses
  not supported"* — those groups share an Ethernet MAC mapping with the
  reserved `224.0.0.0/24` control block. `239.255.0.0` is a safe,
  commonly used choice. You will also see `224.0.0.1` in older guides —
  the special "all hosts" group — but the administratively-scoped
  `239.x` range is the better-behaved choice.
- **Outgoing interfaces matters.** If no interface (or the wrong one) is
  selected, WSJT-X transmits the multicast packets somewhere nothing is
  listening and every app goes quiet. For same-machine setups, loopback is
  the cleanest choice *when every listener supports it* — but some apps
  join the multicast group only on one interface chosen by the OS (the
  lowest-metric multicast route, which can even be an idle VPN adapter)
  and will sit silent while traffic flows on a different one. If any
  listener stays deaf while others receive, the blanket fix is to **tick
  every listed interface** — loopback, your network adapter, and any VPN
  adapters (NordLynx, TAP, WireGuard) — so a copy of the stream reaches
  every place an app could have joined. With TTL 1 the traffic still
  stops at your own machine and subnet, and the extra copies cost a few
  kilobytes per cycle. If your companion apps run on *another* computer,
  see "Apps on different machines" below.
- Older WSJT-X versions (before the multi-interface UI) have just the
  address and port fields — set those and skip the rest.

**JTDX:** same fields under **File → Settings → Reporting**. JTDX supports
the same multicast configuration.

### Each listener

| App | Where | Values |
|---|---|---|
| GridTracker | Settings (gear) → General → Receiving <!-- VERIFY: exact section label on current GridTracker --> | enable **Multicast**, IP `239.255.0.0`, port `2237` |
| JTAlert | Recent versions auto-detect multicast from the WSJT-X config when started <!-- VERIFY: behavior on current JTAlert version --> | — |
| QSO Predictor | Settings → Network | Listen IP `239.255.0.0`, Listen Port `2237` |
| N3FJP / other loggers | Their WSJT-X / UDP settings page | same group and port, multicast enabled |

macOS note: multiple apps sharing one multicast group on the same Mac
requires `SO_REUSEPORT` co-binding. QSO Predictor sets this automatically
(since v2.5.5.1); most other companion apps do too.

## Option 2: Daisy-chain (forwarding)

Each app listens on its own port and re-emits the stream to the next port.
No multicast involved; every hop is plain unicast.

```
WSJT-X ──► 2237 GridTracker ──► 2238 QSO Predictor ──► 2239 Logger
           (listen 2237,        (listen 2238,
            forward to 2238)     forward to 2239)
```

- **GridTracker:** enable UDP forwarding ("Forward UDP Messages") and set
  the destination to `127.0.0.1:<next port>`. <!-- VERIFY: exact toggle label on current GridTracker -->
- **JTAlert:** enable "Resend WSJT-X UDP Packets" to the next port
  (Settings → Applications → WSJT-X). <!-- VERIFY: exact path/label on current JTAlert -->
- **QSO Predictor:** Settings → Network → **UDP Forwarding** → "Forward to
  ports" (comma-separated; default `2238`). QSOP can sit anywhere in the
  chain, including the middle.

The port numbers themselves don't matter as long as each hop's "forward
to" matches the next hop's "listen on" — chains like WSJT-X → `4242` →
GridTracker → `2238` → QSOP work fine.

**Trade-offs vs multicast:** the chain is order-dependent and fragile —
close or crash a middle app and everything downstream goes silent, and any
app that can't forward must sit at the end.

The subtler cost: **forwarders are one-way, so downstream apps become
read-only.** The WSJT-X UDP protocol is bidirectional — click-to-call,
halt TX, and callsign highlighting are request packets sent back to
WSJT-X, and WSJT-X only hears them from apps talking to its socket
directly. An app behind a forwarder receives decodes but its clicks go
nowhere (HamApps documents this for JTAlert's resend: downstream apps
"only receive"). In any chain, only the first app keeps its interactive
features — if two apps both want them (say GridTracker *and* JTAlert),
no chain ordering can satisfy both. Multicast can: every member
exchanges packets with WSJT-X directly, so every app keeps full control.
(Purely advisory listeners like QSO Predictor never send requests, so
they're the one kind of app that can sit anywhere in a chain without
losing anything.)

One trap to avoid when splitting the stream: WSJT-X's **"Secondary UDP
Server"** in the Reporting tab is *not* a second copy of the decode
stream — it's the N1MM Logger+ logged-contact (ADIF) broadcast. JTDX's
equivalent (**"2nd UDP server"**, filed under "Send logged QSO ADIF
data") is the same thing. An app pointed at either sees completed QSOs
only: no decodes, no status. Neither can feed a second chain.

The daisy-chain remains useful when one app doesn't do multicast, or
when you want one app to filter/inspect the stream before the others
see it.

## Apps on different machines

The multicast recommendation above is strictly a *same-machine* pattern:
with "Outgoing interfaces" set to loopback, those packets never touch a
network card, so there is nothing to traverse and nothing to go wrong.

Between machines, be more conservative — multicast is genuinely
unreliable off-box in typical home networks: consumer routers don't
forward `239.x` traffic between subnets, VPNs usually drop it, and Wi-Fi
access points transmit multicast at low legacy rates with no
acknowledgments (decodes arrive late, partially, or not at all).
IGMP-snooping switches can eat it too.

Patterns that work, in order of preference:

1. **Hybrid (recommended):** loopback multicast for all the apps on the
   main PC, plus one app forwarding a plain unicast copy to the remote
   machine's `IP:port`. GridTracker's forwarder accepts a full IP:port
   destination and can be that bridge. Unicast point-to-point is
   deterministic, firewall-friendly, and Wi-Fi-safe.
2. **Direct unicast:** if the remote machine hosts the *primary*
   consumer, point WSJT-X's UDP Server straight at that machine's IP and
   fan out locally there.
3. **LAN multicast:** on a fully wired single subnet (every host on the
   same switch, no Wi-Fi hop, no VLANs), multicast across machines does
   work — select the LAN interface in "Outgoing interfaces" instead of
   loopback. Test it before trusting it, and prefer option 1 the moment
   Wi-Fi is involved.

## How to know it's working

Work down the chain:

1. **WSJT-X** shows decodes in Band Activity (if not, the problem is radio
   audio, not UDP).
2. **GridTracker** map/call roster populates within one 15-second cycle.
3. **JTAlert** shows callsigns.
4. **QSO Predictor** status bar reports "Tracking N stations" shortly
   after startup, and the local decode table fills.

QSO Predictor's built-in **Network Doctor** (Diagnostics → Run Full
Checkup)
verifies the whole decode chain link by link — who is configured to send
where, and whether anything is actually listening there — and names the
broken hop in plain language ("GridTracker isn't running, so nothing
reaches QSO Predictor"). It recognizes unusual-but-consistent setups as
healthy rather than flagging them. The report is markdown, made to be
pasted into a forum thread or an AI chat if you want help.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Only the first-launched app gets decodes | Everything is unicast on one port | Switch to multicast (Option 1) or a daisy-chain (Option 2) |
| *All* apps silent after switching to multicast | WSJT-X "Outgoing interfaces" not set to loopback | Select the loopback interface in WSJT-X Reporting settings |
| Apps on another PC receive nothing | TTL 1 / loopback-only interface | Select the LAN interface in Outgoing interfaces; check firewall |
| One app silent, group and port look right | Group mismatch typo (`224` vs `239`, or port) | Every app must use the *identical* group and port |
| One app receives the multicast group, another stays silent — settings identical | The silent app joined the group on a different interface than WSJT-X transmits on (e.g. default adapter vs loopback) | In WSJT-X "Outgoing interfaces", select your network adapter as well as (or instead of) loopback; TTL 1 keeps traffic on your subnet |
| Multicast breaks when a VPN connects — or one app is deaf even with the VPN **disconnected** | A VPN adapter (NordLynx, TAP, WireGuard…) can hold the *lowest* interface metric, so apps that join the group on "any interface" silently join the idle tunnel instead of your LAN or loopback (`netsh interface ip show joins` reveals which interface each membership landed on) | Raise the VPN adapter's interface metric (`Set-NetIPInterface`), disable the adapter when unused, or use apps that join the group on every interface |
| Windows firewall prompt appeared once, app silent since | Blocked on first run | Allow the app for private networks in Windows Defender Firewall |
| "Address already in use" on startup | Two apps unicast-bound to one port | That's the original problem — use one of the two topologies above |
| WSJT-X: "MAC-ambiguous multicast groups addresses not supported" | Group address collides with the reserved `224.0.0.0/24` MAC mapping (any `x.0.0.y` / `x.128.0.y` form, e.g. `239.0.0.2`) | Pick a different group, e.g. `239.255.0.0` |
| New app works, but an *existing* app (or everything downstream of it) silently went stale | Windows lets several apps bind one unicast port (`SO_REUSEADDR`), but each packet is delivered to only **one** of them — a `127.0.0.1`-specific binding beats a `0.0.0.0` binding, so the newcomer can capture the whole stream without any error appearing anywhere | Don't share a unicast port; move to multicast (Option 1) or give each app its own port in a chain (Option 2) |

## Where QSO Predictor fits

Everything above stands on its own. If you're curious what QSOP adds once
it's on the multicast group: it cross-references your local decodes with
live PSK Reporter data to reconstruct what the **DX station** is hearing —
the pileup at their end (including callers you can't hear), whether your
signal is reaching their region, and which frequencies are clear *there*
rather than here. [Overview and download](https://qsop.wu2c.net/), or the
[GridTracker-specific guide](/integrations/gridtracker/) for that pairing.
