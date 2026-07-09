# FT8web External Data Stream — proposal + working implementation

Status: submitted upstream 2026-07-03 — https://github.com/ok1cdj/FT8web/pull/10
(branch `feat/external-data-stream` on fork https://github.com/wu2c-peter/FT8web)

Contents of this folder:

- `PROPOSAL.md` — this file; the body doubles as draft text for the GitHub issue/PR.
- `0001-feat-optional-External-Data-Stream-JSON-over-local-W.patch` — complete,
  type-checked (`tsc --noEmit`) and build-verified patch against FT8web `main`
  (July 2026). Apply with `git am`.
- `ft8web_udp_bridge.py` — reference bridge, FT8web JSON → WSJT-X UDP protocol.
  Verified end-to-end against QSO Predictor's `udp_handler.py` parser
  (status, decode, and QSO-logged signals all fire with correct payloads).

---

## Draft issue / PR text (for Ondra, OK1CDJ)

### Proposal: optional "External Data Stream" so desktop tools can consume FT8web

FT8web is currently a closed loop — decodes, rig status and logged QSOs live
only inside the browser tab. The desktop FT8 ecosystem (GridTracker, JTAlert,
logging programs, propagation/pileup analyzers like QSO Predictor) is built
around the WSJT-X UDP message protocol, which a browser cannot speak directly
because browsers cannot send UDP datagrams.

This PR adds a small, **off-by-default** feature that closes that gap:

- A new `ExternalStreamService` (`src/services/`, ~175 lines, zero
  dependencies) that pushes JSON to a configurable `ws://localhost:<port>`
  WebSocket endpoint. Browsers are allowed to open `ws://` connections to
  localhost even from an https page (localhost is exempt from mixed-content
  blocking), so it works from the hosted app at ft8web.ok1cdj.com.
- Three hook points in `App.tsx`: the decode `worker.onmessage` handler
  (decode batches), a status effect (dial freq / mode / myCall / myGrid /
  TX offset / TX-enabled / transmitting / DX call — the WSJT-X Status
  equivalent), and `fsm.onLogQSO` (logged QSOs).
- A settings section (modeled on the Cloudlog/Wavelog block): enable toggle,
  endpoint URL, live connected/disconnected indicator.
- A reference bridge (`examples/udp-bridge/ft8web_udp_bridge.py`, stdlib +
  `websockets`) that re-emits the stream as WSJT-X-protocol UDP datagrams
  (Heartbeat, Status, Decode, QSO Logged). With the bridge running,
  GridTracker / JTAlert / QSO Predictor / loggers work with FT8web
  **unmodified** — verified against QSO Predictor's WSJT-X parser end-to-end.

Design constraints chosen deliberately:

- **One-way.** Nothing received on the socket is read or acted on — no remote
  control surface, no security exposure beyond publishing decodes to a
  localhost endpoint the user explicitly configured.
- **Fire-and-forget.** Never blocks or throws into decode/TX paths; drops
  messages while disconnected; reconnects with exponential backoff; replays
  the latest status snapshot on reconnect so late-starting consumers get
  current rig state.
- **Off by default.** Zero behavior change unless enabled in Settings.

#### Wire format (schema v1)

Every message is a JSON text frame:

```json
{ "src": "FT8web", "ver": 1, "type": "...", "utc": "2026-07-03T18:30:00.000Z", ... }
```

`type: "decode"` — one per decode cycle:

```json
{
  "type": "decode", "dialFreqHz": 14074000, "mode": "FT8",
  "decodes": [
    { "time": "183000", "snr": -12, "freq": 1687, "message": "CQ JA1XYZ PM95" }
  ]
}
```

(`time` is HHMMSS UTC; `freq` is the audio offset in Hz, like WSJT-X delta
frequency.)

`type: "status"` — sent on any change of the underlying fields, and replayed
on reconnect:

```json
{
  "type": "status", "dialFreqHz": 14074000, "mode": "FT8",
  "myCall": "OK1CDJ", "myGrid": "JO70", "txFreqHz": 1512,
  "txEnabled": true, "transmitting": false, "dxCall": "JA1XYZ"
}
```

`type: "qso_logged"` — sent when the FSM logs a QSO:

```json
{
  "type": "qso_logged", "call": "JA1XYZ", "grid": "PM95",
  "rstSent": "-12", "rstRcvd": "-07",
  "dialFreqHz": 14074000, "mode": "FT8", "band": "20m"
}
```

Additive changes keep `ver: 1`; breaking changes bump it. An obvious future
addition is decode `dt` (delta time) — the ft8ts result would need to carry it
through the worker's formatting step.

#### Verification done

- `npm run lint` (tsc --noEmit) clean; `npm run build` clean.
- End-to-end: simulated FT8web client → WebSocket → bridge → UDP →
  QSO Predictor's production WSJT-X parser. All three message types parsed
  correctly (dial frequency, DX/DE call and grid, TX DF, decode SNR/offset/
  message with callsign extraction, QSO-logged call+grid).
- Not yet exercised against GridTracker/JTAlert — their WSJT-X parsers are
  stricter about Heartbeat/Status handshakes in some versions; testers
  welcome.

---

## QSOP-side follow-up (move 2, separate work)

Planned but not implemented: a native WebSocket listener in QSOP
(a `controllers/` QObject following the HealthMonitor pattern, or a thread
alongside `udp_handler.py`) that accepts this schema directly — no bridge
process — and optionally re-emits WSJT-X UDP via the existing
`_forward_packet` machinery so downstream apps (GridTracker etc.) work while
QSOP runs. Port suggestion: 2442 (matches the FT8web default URL).
