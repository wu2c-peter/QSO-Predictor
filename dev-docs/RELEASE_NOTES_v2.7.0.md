# Release Notes — v2.7.0

**Date:** July 2026
**Theme:** The Doctors — a full station-diagnostics framework with five
new doctors and one shareable checkup report

---

## Summary

v2.6.0 shipped the Audio Doctor and it earned its keep immediately. The
obvious question was: why should only audio get a doctor? v2.7.0
answers with a family of them — one per station subsystem — under a new
**Diagnostics** menu:

**Diagnostics → Run Full Checkup** probes your whole station once —
configs, UDP ports, serial hardware, system clock, OS power state,
audio (Windows) — runs every doctor over that snapshot, and produces a
single markdown report designed to be **pasted**: into a forum thread,
an email, or an AI assistant. Findings first (worst first), then every
check that passed, then what was *not* examined, then the raw evidence.
The report carries its own context — the person (or model) reading it
needs nothing else to start helping.

The new doctors, each also runnable individually:

- **Clock Doctor** — measures your real clock offset against NTP (one
  48-byte query). FT8's silent killer: past ~1 s of drift, decodes
  quietly die while the waterfall looks alive.
- **Config Doctor** — duplicate config files ("you may be editing the
  copy the app doesn't read" — modification times tell the story), and
  stored audio-device bindings that no longer match any live device
  (the Windows USB-rename trap).
- **Network Doctor** — verifies the UDP decode chain link by link
  against what is actually listening, and names the broken link by app.
  Unusual-but-consistent chains (a 4242 daisy-chain hop) are recognized
  as healthy, never flagged for being unconventional.
- **Serial/CAT Doctor** — every serial port with its adapter chip
  identified (FTDI / CP210x / CH340 / Prolific); configured CAT/PTT
  ports that don't exist (the COM-renumber trap); the counterfeit
  Prolific "Code 10" trap and FTDI-gate-bricked cables; two apps
  configured to fight over one port. **Strictly passive** — it never
  opens a port, because opening one can toggle DTR/RTS and key your
  transmitter.
- **System Doctor** — Windows Fast Startup (moved here from the Audio
  Doctor, and now reports the *effective* state — hibernation disabled
  forces it off), USB selective suspend (the classic
  vanishing-mid-session USB device), automatic sleep vs unattended
  operation (with macOS power-assertion awareness — a Mac decoding
  audio normally never sleeps, and the report says so instead of crying
  wolf), macOS microphone permission, Linux dialout/uucp membership,
  and which ham apps do or don't start automatically (Task-Manager
  "disabled" state respected).

Everything is **passive**: no doctor changes a setting, writes another
app's config, opens a serial port, or transmits.

Privacy: reports scrub usernames from every path; callsign and grid
appear only while the "Include station identity" checkbox is ticked;
autostart and USB inventories list only ham-relevant entries — the
rest are counted, not named.

Also in this release: the checkup dialog gained an **Advisories**
section (informational findings that carry concrete advice are now
shown in full), a bare `%` in a WSJT-X/JTDX config value no longer
breaks config detection, and the automated test suite grew from 430 to
625 tests.

---

## What Changed

### New: Diagnostics menu

`Diagnostics ▸ Run Full Checkup… / Audio Doctor… (Windows) / Clock
Doctor… / Config Doctor… / Network Doctor… / Serial/CAT Doctor… /
System Doctor…`

The Audio Doctor moved from **Tools** to **Diagnostics** (unchanged
otherwise). Each doctor's menu item re-runs just that doctor — the
cheap loop for verifying a fix.

### The checkup report

One markdown document, identical structure on every platform:

1. A preamble addressed to whoever will read it ("You are helping an
   amateur radio operator troubleshoot their station…") — pasting the
   report into an LLM chat needs no extra prompt.
2. **Station** — tool version, platform, timestamp, callsign/grid (if
   included; explicitly marked "withheld by operator" if not).
3. **Findings** — failures and warnings only, worst first, each with
   its fix.
4. **Passed checks** — because "checked and fine" must be
   distinguishable from "not examined".
5. **Not checked** — doctors skipped on this platform and states that
   could not be read.
6. **Details** — the evidence: device tables, port tables, detected
   configs with modification times.
7. **Machine appendix** — a small stable JSON block for tooling.

### Doctor details worth knowing

- **Clock Doctor** queries `time.cloudflare.com` / `time.google.com`
  (never the NTP Pool — their vendor policy forbids application
  defaults), resolves DNS *before* stamping the timing window, and
  reports UNKNOWN when offline instead of guessing.
- **Network Doctor** scans config-referenced UDP ports even outside
  the conventional 2230–2260 range, so daisy-chains through ports like
  4242 are fully visible.
- **Serial/CAT Doctor** understands that WSJT-X keeps a placeholder
  `CATSerialPort` even with `Rig=None`, and that `PTTport` means
  nothing under VOX keying — a port is only "expected" when the
  matching feature is actually selected. On Windows it also surfaces
  present-but-broken devices (a Code 10 counterfeit adapter never
  reaches the normal port list) and a USB adapter inventory that sees
  driverless and PID-0000-bricked chips.
- **System Doctor** stores only ham-relevant autostart entries and TCC
  clients; a full software inventory would fingerprint your machine
  inside a shared report.

### Fixes

- A bare `%` in any WSJT-X/JTDX config value made QSOP's config
  detection silently drop that app everywhere (setup wizard included).
  Fixed — config parsing no longer performs `%`-interpolation.
- Anonymized reports say "Station: (withheld by operator)" so a
  deliberate omission can't be mistaken for a parse failure.

### For developers

- `diagnostics/` is a pure, Qt-free package (enforced by tests) — the
  doctors framework, probes, registry, and report renderer are
  buildable into a future standalone headless tester.
- Design spec: `dev-docs/DIAGNOSTICS_SPEC.md`. Every doctor shipped
  through the same pipeline: fixture tests → multi-agent adversarial
  review → all confirmed findings fixed with regression tests.
- Test suite: 430 → 625 tests, still cross-platform and display-free.

---

## Upgrade Notes

- No settings migration; existing configs are untouched.
- The Audio Doctor's Fast Startup check now lives in the System Doctor
  (same check id in reports). The standalone Audio Doctor dialog no
  longer shows that row; Full Checkup does.
- Windows/macOS/Linux all get the full Diagnostics menu; the Audio
  Doctor entry remains Windows-only.
