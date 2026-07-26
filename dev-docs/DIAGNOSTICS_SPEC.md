# Diagnostics framework ("Doctors") — design spec

Status: Migration steps 1–4 implemented 2026-07-26 (step 1:
`diagnostics/` package, re-exports, conventions tests; step 2: detection
layer lifted from `setup_wizard.py` with first unit coverage; step 3:
`StationSnapshot` + `registry.py` + `report.py` + Audio Doctor adapter in
`audio_doctor/doctor.py`; step 4: Clock Doctor + Diagnostics menu with
Full Checkup and `widgets/checkup_dialog.py`, on branch
`feat/diagnostics-menu` pending Windows verification). **Step 4's release
freezes the report format** — review Contract 3 wording before shipping.
Step 5 (one doctor per release, roster order) is the ongoing phase.
Companion reading: `DEVELOPMENT_NOTES.md` § Audio Doctor.

## What and why

A family of per-subsystem diagnostic "doctors" (Audio Doctor is the first,
shipped in v2.6.0) that share one probe pass, one findings model, and one
report format. Menu-wise they are siblings under a Diagnostics menu, with
**Run Full Checkup** above them running every applicable doctor and producing
a single merged report.

Design principles, in priority order:

1. **Probes measure, checks reason.** Platform access (COM, registry,
   netstat, IOKit…) lives in per-OS probe modules. Checks are pure functions
   over snapshot dataclasses, testable with fixtures on any OS. This is the
   `audio_doctor` split (`models/parsing/checks` vs `probe_windows.py`)
   promoted to a framework rule.
2. **One snapshot, many doctors.** The best diagnoses are cross-system
   (config says X, port table says Y, process list says Z). Probing runs
   once per checkup; every doctor interprets the same snapshot. Doctors
   never probe.
3. **Platform honesty.** A doctor that doesn't support the current platform
   appears in the report as "not checked on this platform" — never silently
   absent. Distinguishing "checked and fine" from "not examined" is itself
   diagnostic information.
4. **The report is the product.** It is written to be pasted — into a forum
   thread or an LLM chat — and read by someone who cannot see the machine.
   Passed checks are listed, not just failures. The report opens with a
   preamble addressed to whoever (or whatever) will interpret it.
5. **Passive by default.** v1 probes only observe. Anything that opens a
   serial port, toggles RTS, sends a CAT command, or transmits requires an
   explicit user action on a clearly labelled control (the Audio Doctor
   TX-path probe is the precedent: user-initiated, clearly scoped). The
   framework never writes another application's config file. Recommending a
   setting is fine; applying it is out of scope for this spec.

Non-goal for v1, but a standing constraint: a future standalone/headless
tester ("run this exe, paste the report") must be buildable from the core
package. Therefore **nothing in `diagnostics/` may import Qt** or anything
from the main app. Enforce with an architectural test, same pattern as the
existing `utils/`-stays-stdlib test.

---

## Contract 1 — StationSnapshot

One dataclass composed of per-domain snapshots. Gathered once per checkup by
the probe layer (in a worker thread — main thread never blocks on I/O).

```python
@dataclass
class StationSnapshot:
    schema_version: int                # bump on any non-additive change
    taken_at_utc: str                  # ISO 8601, Z suffix
    platform: str                      # "windows" / "macos" / "linux"
    os_detail: str = ""                # e.g. "Windows 11 23H2", "macOS 15.5"

    # Domains. None = not gathered (unsupported platform or probe failure —
    # see errors). Present-but-empty = gathered, nothing found.
    audio: Optional["AudioSnapshot"] = None        # exists today; string
                                                   #   annotation — see the
                                                   #   import-direction rule
    apps: Optional[List[DetectedApp]] = None       # diagnostics.models (step 2)
    udp_ports: Optional[List[PortInfo]] = None     # diagnostics.models (step 2)
    serial: Optional[SerialSnapshot] = None        # future (Serial/CAT Doctor)
    clock: Optional[ClockSnapshot] = None          # future (Clock Doctor)
    system: Optional[SystemSnapshot] = None        # future (System Doctor)

    errors: List[str] = field(default_factory=list)  # probe-time notes
```

Rules:

- **Import direction is one-way: app → diagnostics, never back.**
  `audio_doctor.models` imports `diagnostics.models` at module load (the
  step-1 re-export shim), so any runtime diagnostics → audio_doctor import
  is a hard circular-import crash regardless of load order. Enforced by
  the conventions test, which bans every app module inside `diagnostics/`.
  Consequences: domain snapshot types owned by app-side packages appear in
  `StationSnapshot` as **string annotations with no runtime import**
  (`audio: Optional["AudioSnapshot"]`); the Audio Doctor adapter lives in
  `audio_doctor/`, not `diagnostics/`; and the registry is generic — the
  doctor list is assembled by the consumer (the app, or the standalone
  tester), never by `diagnostics/` importing doctors app-side.
- **Two-level availability semantics.** Domain level: `None` means "not
  gathered". Field level within a domain: follow the `AudioSnapshot`
  convention — `None` means unreadable, checks report `UNKNOWN` rather than
  guessing.
- **Additive evolution only.** New domains and new fields get defaults;
  existing field meanings never change. Renames/removals require a
  `schema_version` bump and are expected to be rare-to-never.
- Domain snapshots are defined next to their doctor (e.g. `AudioSnapshot`
  stays in `audio_doctor/models.py`); `StationSnapshot` just aggregates.
- A per-doctor rerun (menu item) still builds a `StationSnapshot` — it just
  gathers only the domains that doctor declares (see Contract 4). Same type
  everywhere; no special cases.

Sketches for the future domains (to sanity-check the aggregate, not to
bind implementation):

- `SerialSnapshot`: list of ports (device path, friendly name, USB VID/PID,
  driver name/version, in-use-by process where determinable), plus USB
  device inventory with chip identification (FTDI / CP210x / CH340 /
  Prolific / known Digirig IDs).
- `ClockSnapshot`: NTP sync state and measured offset (platform service
  status and/or one SNTP query), timezone sanity.
- `SystemSnapshot`: power settings (USB selective suspend, Fast Startup —
  the latter currently lives in `AudioSnapshot.fast_startup` and stays
  there until a System Doctor exists; migrate additively then), macOS TCC
  microphone permission, Linux `dialout` membership, autostart entries for
  known ham apps.

## Contract 2 — Findings

**`CheckResult` and `Severity` are promoted from `audio_doctor` unchanged.**

```python
@dataclass
class CheckResult:
    check_id: str              # stable slug, e.g. "default-communication"
    title: str
    severity: Severity         # OK / INFO / UNKNOWN / WARNING / FAIL
    detail: str
    fix: str = ""
    panel: Optional[SettingsPanel] = None
```

Rules:

- **`check_id` slugs are forever.** They appear in circulated reports and
  (eventually) in helpers'/LLMs' learned vocabulary. Same discipline as
  `PathStatus.display_label`: never rename, never reuse.
- `check_id` is namespaced by doctor: `"clock/ntp-offset"`,
  `"network/chain-link-down"`, audio keeps its existing un-prefixed ids
  for report continuity (they're already in the wild in v2.6.0 logs).
- Every check **always returns a result**, including OK — the report's
  "passed" section depends on it. `run_checks()` in `audio_doctor/checks.py`
  already works this way; keep the convention.
- `Severity.UNKNOWN` is the platform-honesty severity at check granularity
  ("couldn't read X"); whole-doctor non-applicability is handled by the
  framework (Contract 4), not by emitting rows of UNKNOWNs.
- `SettingsPanel` moves to the shared core and may grow macOS/Linux
  members later (it is "a settings surface a fix lives in", not a Windows
  concept; `probe_*` modules own the launch commands, as today).
- The framework attaches doctor identity when merging (report grouping);
  checks don't carry it redundantly.

## Contract 3 — The report

A single markdown document, identical structure on every platform, built by
`diagnostics/report.py` from `(StationSnapshot, {doctor: [CheckResult]})`.
Offered as: save to file, copy to clipboard.

Section order (stable — helpers and LLMs learn this layout):

```
# <Tool name> diagnostic report
> Preamble: 2–3 sentences addressed to the reader ("You are helping an
> amateur radio operator troubleshoot their station. Below is a
> machine-collected snapshot… 'Not checked' sections were not examined —
> do not assume they are healthy.")

## Station
tool version, report schema version, platform + OS detail, timestamp (UTC),
callsign/grid if found in configs (see privacy note)

## Findings          ← FAIL and WARNING only, most severe first
Per finding: [symbol] title — detail. Fix: …  (check_id in parentheses)

## Passed checks     ← OK / INFO, grouped by doctor, one line each
## Not checked       ← doctors skipped on this platform, and UNKNOWN results
## Details           ← per-domain snapshot dumps (device tables, port table,
                        detected apps with config paths and mtimes)
## Machine appendix  ← fenced JSON: schema_version + findings array
                        (check_id, severity, title). Small and stable;
                        full snapshot serialization is NOT included in v1.
```

Rules:

- **Findings before evidence.** The reader triages from the top; raw tables
  are reference material at the bottom.
- **Privacy:** callsign and grid are included by default (public information
  on every spotting network; essential context for helpers) behind a
  visible "include station identity" checkbox for the exception cases. No
  other identity data (usernames in paths are scrubbed to `~`).
- The preamble makes the report self-carrying: "paste this into your
  favorite LLM" requires no separate prompt.
- Report filenames: `<tool>-report-YYYYMMDD-HHMMZ.md`.

## Contract 4 — Doctor interface

```python
class Doctor(Protocol):
    id: str                    # "audio", "clock", "network", …
    title: str                 # "Audio Doctor"
    platforms: FrozenSet[str]  # {"windows"} for audio today
    domains: FrozenSet[str]    # StationSnapshot fields it reads

    def run(self, snap: StationSnapshot) -> List[CheckResult]: ...
```

- A module-level registry (plain list in `diagnostics/registry.py`) holds
  registered doctors in display order.
- **Full Checkup:** gather the union of `domains` of all
  platform-applicable doctors (one probe pass, worker thread), then run
  each doctor over the snapshot. Doctors whose platform doesn't match are
  reported under "Not checked", not skipped silently.
- **Per-doctor menu item:** same flow, doctor list of one, gathering only
  its declared domains. Cheap re-run loop after a fix.
- **Context domains:** the consumer may pass `extra_domains` to
  `run_checkup()` for data the *report* needs but no current doctor
  declares — e.g. `apps` for the Station identity line and Details
  tables until the Config Doctor exists. QSOP's controller requests
  `{'apps', 'udp_ports'}` on every checkup.
- `run()` must be pure (no I/O, no Qt) — enforced by the no-Qt
  architectural test on the package, and by code review for I/O.
- Cross-system checks (e.g. UDP chain topology, which needs `apps` +
  `udp_ports`) belong to the doctor whose *user-facing subject* they
  address (Network Doctor), which simply declares both domains. If a
  finding truly has no single home, it goes in the doctor whose menu item
  a user would plausibly click — not in a new "misc" bucket.

## Doctor roster (informative — spec'd one at a time, in this order)

1. **Clock Doctor** *(pattern-prover: smallest possible doctor)* —
   `clock` domain. Checks: NTP service running/synced; measured offset vs
   FT8 tolerance (warn ≥ 1 s, fail ≥ 2 s); timezone/DST sanity.
2. **Config Doctor** — `apps`. Checks: config parseable; duplicate
   configs/instances for one app with divergent settings (mtime evidence:
   "you may be editing the copy you don't run"); config references audio
   devices/ports that don't exist right now (needs `audio`, `serial` as
   they become available — domains are additive over releases).
3. **Network Doctor** — `apps` + `udp_ports`. Checks: reconstruct intended
   UDP topology from configs (WSJT-X → forwarders → consumers), diff
   against live port table; report the broken link by name ("GridTracker
   is configured to forward 2237→2238 but isn't running, so nothing
   reaches QSO Predictor"). Port conflicts; firewall hints (Windows,
   best-effort). Must pass the daisy-chain fixture: an unusual-but-
   consistent chain (e.g. 4242→2238) is OK, not a warning.
4. **Serial/CAT Doctor** — `serial` (new probes; the largest new work).
   Checks: expected port (from configs) exists; driver present and not a
   known-bad version (counterfeit-Prolific trap); port exclusively held by
   another process; USB chip identification incl. Digirig detection.
   Active CAT probing (send a query via Hamlib) is a *later, opt-in*
   feature per the passive-by-default rule.
5. **System Doctor** — `system`. Checks: USB selective suspend / power
   plan; Fast Startup (migrates from Audio Doctor); macOS TCC mic
   permission; Linux `dialout` membership; autostart present for apps that
   the topology says are required (companion recommendation:
   "flrig is part of your chain but doesn't start automatically").
6. **Audio Doctor** — exists; becomes a registered doctor with
   `platforms={"windows"}`, unchanged behavior. macOS/Linux audio probes
   are a future `probe_macos.py` / `probe_linux.py` inside
   `audio_doctor/`, not a rewrite.

## Package layout & migration

```
diagnostics/                  # NEW — pure, no Qt, no main-app imports
    __init__.py
    models.py                 # StationSnapshot; Severity, CheckResult,
                              #   SettingsPanel move here (re-exported from
                              #   audio_doctor.models for compatibility)
    registry.py               # doctor registry, run_checkup()
    report.py                 # markdown renderer + preamble
    probe_apps.py             # ConfigFileReader, RunningAppDetector
                              #   (lifted from setup_wizard.py)
    probe_ports.py            # PortScanner (lifted from setup_wizard.py)
                              # (probe_* prefix — matches the conventions
                              #   test's platform-library exemption)
    setup_analysis.py         # SetupAnalyzer (lifted from setup_wizard.py;
                              #   NOT snapshot-pure — calls find_free_port.
                              #   Network Doctor supersedes it eventually.)
    doctors/
        clock.py              # first new doctor (+ its probe, if trivial)
        …                     # one file per small doctor
```

Migration steps (each independently shippable, no user-visible change
until a new doctor lands):

1. Create `diagnostics/models.py`; move `Severity`, `CheckResult`,
   `SettingsPanel` there; `audio_doctor/models.py` re-exports them so no
   call site churns. Add the no-Qt architectural test for `diagnostics/`.
2. Lift `ConfigFileReader` / `PortScanner` / `RunningAppDetector` /
   `SetupAnalyzer` / dataclasses out of `setup_wizard.py` into
   `diagnostics/`;
   `setup_wizard.py` keeps only the Qt dialog + worker and imports the
   rest. (Bonus: those classes become unit-testable under the existing
   pure-module test conventions.)
3. Add `StationSnapshot` + `registry.py` + `report.py`; wrap Audio Doctor
   as a registered doctor. The adapter (around today's
   `gather_snapshot()`/`run_checks()`) lives in `audio_doctor/` and is
   registered from the app side, per the import-direction rule; the
   dialog keeps working unchanged.
4. Ship Clock Doctor + the Diagnostics menu (Full Checkup, Audio Doctor,
   Clock Doctor). First release where the report format goes public —
   review Contract 3 wording carefully at this point; the schema is
   effectively frozen once helpers start reading it.
5. Subsequent releases: one doctor each, roster order above.

UI: one shared findings-list widget (severity symbol/color already defined
on `Severity`) fed by every doctor; the existing Audio Doctor dialog
migrates to it opportunistically, not urgently. Menu: `Diagnostics ▸ Run
Full Checkup / ─── / Audio Doctor / Clock Doctor / …`.

## Open questions (decide before step 4, not before step 1)

- **Tool/report branding** — the report header is the name that
  circulates ("Station Doctor" / "ShackCheck" / other). Blocks nothing
  until the report ships.
- **Standalone tester packaging** — headless entry point emitting the
  report; deferred until ≥3 doctors exist. The no-Qt constraint keeps it
  possible; PyInstaller via the existing Windows build workflow when the
  time comes.
- **Active probes consent UX** — one shared "this will open/key things"
  pattern for TX probe (exists), future CAT query, RTS toggle. Needed by
  Serial/CAT Doctor at the earliest.
- **Fast Startup ownership** — moves from Audio to System Doctor when the
  latter exists; keep the `check_id` stable across the move.
