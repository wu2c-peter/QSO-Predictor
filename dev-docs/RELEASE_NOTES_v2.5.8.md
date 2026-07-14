# Release Notes — v2.5.8

**Date:** July 2026
**Theme:** FT8web browser-client support + a richer outcome record — the
next step toward v2.6's personalized recommendations

---

## Summary

Two headline changes this release:

1. **QSO Predictor now works with FT8web.**
   [FT8web](https://ft8web.ok1cdj.com/) is a browser-based FT8/FT4 client
   by Ondra, OK1CDJ — decode and transmit from a web page, no WSJT-X
   install. Browsers can't send UDP, so FT8web users have been locked out
   of the whole UDP ecosystem — QSO Predictor, GridTracker, JTAlert,
   loggers. We contributed an **External Data Stream** feature to FT8web
   itself (merged upstream July 2026, live on ft8web.ok1cdj.com), and this
   release adds QSOP's native listener for it. Tick one checkbox on each
   side and FT8web becomes a full alternative to WSJT-X/JTDX — decodes,
   status, and logged QSOs all flow through. As a bonus, QSOP re-broadcasts
   everything it receives as standard WSJT-X UDP packets, so your
   downstream apps keep working unchanged too.

2. **The outcome recorder captures the full tactical picture (schema v2).**
   v2.5.7 fixed *whether* outcome data was recorded correctly; v2.5.8
   expands *what* is recorded: a snapshot of the situation at the moment
   you selected the target — competition, your pileup rank, SNR margins,
   what the behavior model believed, the success probability and strategy
   the app showed you — plus a compact per-TX-cycle trace of how the
   pileup evolved while you called. This is the raw material v2.6 is
   planned to learn from. As before: machine-local, never uploaded.

Also in this release: two fixes to the learning stack (a behavior-prior
pooling bug that had Cook Islands stations inheriting a Bosnian behavior
profile, and corrupt `session_end` records after idle gaps), and the
automated test suite grew from 285 to 355 tests.

---

## What Changed

### FT8web as a decode source

**QSOP side:** Settings → Network tab → **"FT8web Browser Client
(Optional)"** → check *Listen for FT8web data stream*. The WebSocket port
defaults to 2442; leave it unless something else on your machine already
uses it. Off by default.

**FT8web side:** Settings → **External Data Stream** → *Enabled*, URL
`ws://localhost:2442`. FT8web (in your browser) and QSOP must run on the
same computer — the listener accepts localhost connections only.

What flows through: decodes, rig status (dial frequency, TX state,
target), and logged QSOs — the same three streams QSOP consumes from
WSJT-X, driving the same analysis, target selection, and outcome
recording. Both sources go through the same message parser, so a decode
is classified identically whichever client produced it.

**Forward ports keep working.** Everything received from FT8web is
re-broadcast to your configured forward ports as genuine WSJT-X-format
UDP datagrams (heartbeats included). GridTracker, JTAlert, and loggers
listening on those ports neither know nor care that the decodes
originated in a browser tab.

**Health warnings understand the new source.** While an FT8web client is
connected, the "No data from WSJT-X/JTDX" warning is suppressed — UDP silence
is expected then. Conversely, if WSJT-X/JTDX *and* FT8web are both
feeding data at once, a new status-bar warning ("Two data sources
active") asks you to close one: two clients' dial frequencies and targets
interleave and confuse the analyzer. Intended usage is one active source
at a time.

Implementation notes: the listener is a pure-stdlib WebSocket server
(RFC 6455) — no new dependencies, no bridge process. The wire format is
schema v1 of FT8web's External Data Stream
([FT8web PR #10](https://github.com/ok1cdj/FT8web/pull/10)).

### Outcome recorder: schema v2 — the at-select snapshot

Every outcome event now opens with a snapshot of the conditions under
which you made the call decision: pileup competition (count *and* where
it was measured), how many rivals are local to you, your rank in the
pileup, your SNR at the target, the strongest rival's SNR, the behavior
model's state and persona for the target, and the success probability and
strategy the app displayed. While you call, a compact per-TX-cycle trace
records how the pileup evolved — competition, your rank, path status,
your own TX frequency — capped so long slogs stay small (~1.2 KB per
event with a typical trace).

Why this matters: v2.6 is planned to tune recommendations from your own
outcome history. "Did following the recommendation pay off?" can only be
answered against the situation *at the moment of the decision*, not the
terminal result alone. Same argument as v2.5.7 — this data only
accumulates while you operate, so the sooner v2 records start being
written, the more v2.6 has to learn from on day one.

As always: `~/.qso-predictor/outcome_history.jsonl`, machine-local, never
uploaded. v1 records remain valid; mixed v1/v2 files are expected and
fine. Full field reference in `dev-docs/OUTCOME_SCHEMA.md`.

### Behavior prior: E5 is not E7

When the behavior model has never seen a specific callsign, it falls back
to a prior pooled from same-prefix stations. That pooling collapsed every
single-letter+digit country prefix to its first letter — so E51WL (South
Cook Islands) inherited a behavior profile built from E7 (Bosnia)
stations, confidently presented as "Based on 15 E stations" for a Pacific
target. The digit is now kept where it selects the country (E5/E7, S5/S7,
T7, H4) and dropped only in single-entity series where it's just a call
area (B, F, G, I, K, L, M, N, R, U, W).

Also: a prefix prior now requires 5 stations instead of 2, and thin
estimates are labeled "Weak prior: …" instead of "Based on …" — a
2-station aggregate is an anecdote, and the old wording projected more
authority than the inference deserved.

### Outcome log: no more corrupt `session_end` records

Field data showed one corrupt `session_end` per target click after an
idle gap: stamped with the *old* session's last-activity time, zero
outcomes, negative `elapsed_s`. Root cause: target selection didn't count
as session activity, so every re-select kept re-seeing the stale idle gap
and ending the freshly started session with a pre-idle timestamp.
Selection now counts as activity, and elapsed time is clamped so it can
never go negative. If you analyze the JSONL yourself: `session_end`
records with negative `elapsed_s` are pre-2.5.8 artifacts — discard them.

### Internal

* Test suite: 285 → 355 tests. The FT8web listener has end-to-end
  coverage with a real WebSocket client (masked frames, ping/pong,
  junk-frame tolerance, reconnects, and a forward-port round-trip back
  through the WSJT-X parser), and the schema v2 field set is frozen by
  contract tests.
* The MSIX packaging script now derives the package filename from the
  AppxManifest version instead of a hardcoded string.

---

## Compatibility

* `outcome_history.jsonl`: new events are schema v2 (`"v": 2`); v1
  records remain valid, and mixed v1/v2 files are expected. External
  tooling should dispatch on the `v` field.
* Two new settings (FT8web enable + WebSocket port), off by default. No
  migration; existing configs are untouched.
* No changes to WSJT-X/JTDX UDP handling, MQTT ingestion, scoring, or any
  behavior when the FT8web listener is disabled.
