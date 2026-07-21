# Release Notes — v2.6.0

**Date:** July 2026
**Theme:** Audio Doctor — Windows TX-audio-path diagnostics — plus a
packaging fix that puts IONIS propagation back in downloadable builds

---

## Summary

Two headline changes this release:

1. **Audio Doctor: find out why your TX audio went silent — in seconds.**
   This tool exists because it happened to us. In July 2026, after a
   browser FT8 session (ft8web) that used the rig's codec, WSJT-X TX
   audio went dead: RX worked perfectly, the problem survived a cold
   boot, and re-selecting the audio device inside WSJT-X changed
   nothing. The investigation identified a family of Windows-side
   culprits — registry-persisted per-app mixer state, communications
   ducking, reassigned default-device roles — all invisible inside
   WSJT-X and all able to survive reboots. Tracking that down by hand
   took hours. The new **Tools → "Audio
   Doctor..."** (Windows) automates that investigation: 11 read-only
   checks over the audio path between WSJT-X/JTDX and the rig, a live
   TX-path probe that watches the Windows peak meters layer by layer,
   and clickable links that open the exact Windows settings panel where
   each fix lives. A passive monitor also warns in the status bar when
   WSJT-X claims to be transmitting but no audio is reaching the codec.

2. **Fix, with a disclosure: downloadable GitHub builds v2.4.0–v2.5.8
   shipped without IONIS propagation.** A build-workflow bug meant the
   Windows `.zip` and macOS `.dmg` downloads on the GitHub Releases
   page never actually contained the IONIS engine, even though the
   docs advertise it as bundled. Microsoft Store installs were **not**
   affected. Fixed and now CI-guarded; upgrading to v2.6.0 restores
   IONIS. Details below — we'd rather tell you plainly than quietly.

Also in this release: `psutil` restored to packaged builds (analyzer
memory diagnostics), a deliberate pruning of never-shipped sklearn
hiddenimports, and the automated test suite grew from 355 to 430 tests.

---

## What Changed

### Audio Doctor (Windows)

**Tools → "Audio Doctor..."** — Windows only; the menu item does not
appear on macOS/Linux. It is strictly read-only: it diagnoses, changes
nothing, and every finding tells you where the fix lives.

**Configuration audit.** Eleven checks over the Windows audio
configuration, listed worst-first with severity chips (✓ OK / ℹ Info /
? Unknown / ⚠ Warning / ✗ Problem). The classic failure modes it
catches:

* **The persisted per-app mute** — Windows stores per-app volume and
  mute *per device* in the registry. A silenced WSJT-X entry on the
  codec survives reboots, mutes TX only (RX is a different device
  role), and shows nowhere inside WSJT-X. This is the classic
  "RX works, TX dead" — and the one that started this whole tool.
* **The codec holding a Windows default role** — the rig codec should
  be neither the *default playback device* (system sounds go out over
  the air) nor the *default communication device* (browser/VoIP audio
  counts as a call and could TX over the air — and it arms
  communications ducking against WSJT-X).
* **Communications ducking** — should be "Do nothing". When any app
  opens a "communications" stream (a browser using the mic counts),
  Windows lowers other apps' sliders by 80% by default — and the
  lowered slider can stick.
* **Endpoint formats** — TX playback and RX recording should both be
  16-bit 48000 Hz; other rates force lossy resampling.
* **Duplicate / stale codec entries** — the USB codec has no serial
  number, so moving it to a different USB port makes Windows treat it
  as a brand-new device ("2- USB Audio CODEC") while WSJT-X may still
  be bound to the old one.
* **Windows Fast Startup** — with Fast Startup on, "Shut down" resumes
  a saved kernel image and does *not* reinitialize audio drivers; only
  "Restart" does. A power cycle proves nothing when troubleshooting
  audio.

Plus: rig codec present and active, live WSJT-X/JTDX audio session
location and mute/volume, and the system sounds scheme.

**Live TX path check.** Press Tune in WSJT-X, click **"Check TX
path"**: Audio Doctor watches the Windows peak meters — the per-app
session and the codec endpoint — for 4 seconds and reports which layer
of the path is silent. The verdicts pinpoint the failure: "No WSJT-X
audio session on the codec" (stale device binding — fixed *inside*
WSJT-X: Settings → Audio, switch the output away, OK, restart, switch
back), "WSJT-X is muted in the Windows mixer", "WSJT-X mixer volume is
near zero", "WSJT-X is not producing audio" (Pwr slider, or nothing is
actually transmitting), "Audio is not reaching the codec" (routed to a
different device), or the healthy "TX audio is reaching the codec".

**Fixes are a click away.** Most findings carry an "Open ..." link
that deep-links into the exact Windows settings surface — the
Communications tab, Playback/Recording devices, the Volume mixer,
Power Options — no hunting through Settings. (Fixes that live inside
WSJT-X itself deliberately carry no Windows link.)

**Rig device matching.** The "Rig audio device name contains:" box
(default "USB Audio CODEC" — matches SignaLink, Digirig, and most
rig-integrated codecs) tells Audio Doctor which endpoints are yours;
it's a simple substring match. Edits persist when you close the dialog
with Close (Esc discards). Stored as `rig_device_hint` under `[AUDIO]`
in `qso_predictor.ini`.

### The silent-TX monitor

You don't have to remember to open the dialog. Whenever WSJT-X reports
over UDP that it started transmitting, QSOP probes the TX path for
about 4 seconds on a background thread (at most once per minute). If
WSJT-X claims to be transmitting but no audio session or samples reach
the codec, a sticky status-bar warning appears:

> ⚠ TX audio: *headline* — see Tools → Audio Doctor

It clears automatically on the next healthy transmission (or after 10
minutes). While an FT8web browser client is connected the monitor
stands down — the browser plays TX audio there, not wsjtx.exe, so a
missing WSJT-X session is expected. To turn the monitor off entirely:
`silent_tx_monitor = false` under `[AUDIO]` in `qso_predictor.ini`.

### Found along the way: the Volume Mixer page lies

Discovered during live testing and worth knowing on its own: Windows
11's Settings → Sound → Volume mixer page can show an app's slider
greyed-out or at a wrong value *even while the app is actively
playing*. We confirmed it directly — WSJT-X tuning through the codec
at healthy volume while the mixer page showed it greyed out at "1".
Audio Doctor reads the live audio session, not the settings page, so
when the two disagree, trust the Doctor. The practical recipe is
order-dependent: **press Tune in WSJT-X first, then open the Volume
mixer** — only then does the WSJT-X row show its real value and become
adjustable (a mixer opened before TX starts stays stale and greyed
until you close and reopen it). The dialog carries a prominent hint
about this.

### Downloadable builds v2.4.0–v2.5.8 shipped without IONIS

The disclosure, plainly: the Windows `.zip` and macOS `.dmg` builds
published on the GitHub Releases page from v2.4.0 through v2.5.8 did
not contain a working IONIS propagation engine. The release workflow
never installed `safetensors`, so PyInstaller silently dropped it —
the Windows exes bundled the IONIS model checkpoint but not the
library needed to read it, and the macOS job bypassed the spec file
entirely, so DMGs lacked even the model data. The app degrades
gracefully when IONIS is unavailable, which is exactly why nobody
noticed: no error, just silently reduced propagation analysis while
the docs and Store listing advertised IONIS as bundled.

**Microsoft Store installs were not affected** — the MSIX build
environment installed the dependencies correctly all along.

Fixed in v2.6.0: the workflow installs `safetensors` (and `psutil`) in
both build jobs, and the macOS build now bundles the IONIS model data.
Guarded so it can't silently regress: a CI test now cross-checks every
hiddenimport in the PyInstaller spec against the workflow's
pip-install lines, and the release checklist gained build-log and
artifact smoke checks. If you installed from a GitHub release,
**upgrading to v2.6.0 restores IONIS** — no other action needed.

While in there: the sklearn/joblib hiddenimports were pruned from the
spec *deliberately* — they were never installed in the CI environment,
so no shipped build ever contained them (they only produced a dozen
"hidden import not found" errors per build). Trained-model loading is
documented as a source-install feature; frozen builds fall back
cleanly to the heuristic predictor, and can't run training anyway.
And `psutil` is back in packaged builds, restoring the analyzer's
memory diagnostics.

### Internal

* Test suite: 355 → 430 tests. The Audio Doctor core (models, parsing,
  checks, verdict logic) is pure stdlib by design, so all of its
  diagnostic logic is unit-tested on every platform — no Windows, no
  Qt required. A conventions test enforces the layering: only the
  Windows probe module may touch pycaw/COM/registry APIs.
* New CI guard (see the IONIS entry above): spec hiddenimports are
  parsed and compared against the workflow's install steps, so a
  missing frozen-build dependency fails the build instead of shipping
  silently.

---

## Compatibility

* Audio Doctor requires Windows 10/11. On macOS/Linux the Tools menu
  entry does not appear and nothing else changes — zero behavior
  difference on those platforms.
* Audio Doctor is read-only. It never modifies a Windows setting,
  device, or mixer value.
* Two new settings under `[AUDIO]` in `qso_predictor.ini`:
  `rig_device_hint` (default "USB Audio CODEC") and
  `silent_tx_monitor` (default on). No migration; existing configs are
  untouched.
* **Source installs on Windows:** re-run
  `pip install -r requirements.txt` to pick up `pycaw>=20251023`
  (Windows-only marker — nothing new installs on macOS/Linux).
  Packaged installs include everything.
* No changes to WSJT-X/JTDX UDP handling, the FT8web listener, MQTT
  ingestion, scoring, or outcome recording.
