"""
Doctor registry and checkup orchestration — Contract 4 of
dev-docs/DIAGNOSTICS_SPEC.md.

A Doctor is a pure interpreter over a StationSnapshot; the registry
holds the doctor list (assembled by the consumer — the app or a future
standalone tester — never by this package importing app-side modules)
and runs checkups: one probe pass gathering the union of the applicable
doctors' domains, then every applicable doctor over the same snapshot.

`gather_snapshot()` / `run_checkup()` perform probe I/O — call them from
a worker thread, never the Qt main thread (same contract as the probes
themselves).

QSO Predictor
Copyright (C) 2026 Peter Hirst (WU2C)
"""

import dataclasses
import logging
import platform as platform_mod
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, FrozenSet, Iterable, List, Optional, Protocol

from diagnostics.models import (CheckResult, SNAPSHOT_META_FIELDS,
                                SNAPSHOT_SCHEMA_VERSION, StationSnapshot)

logger = logging.getLogger(__name__)


def current_platform() -> str:
    """The platform key doctors declare support for."""
    if sys.platform == 'win32':
        return 'windows'
    if sys.platform == 'darwin':
        return 'macos'
    return 'linux'


class Doctor(Protocol):
    """One per-subsystem diagnostic. `run()` must be pure — no I/O, no
    Qt; everything it needs comes from the snapshot (enforced by the
    conventions test for doctors living in diagnostics/, by review for
    app-side doctors like audio_doctor's)."""
    id: str                    # "audio", "clock", "network", ...
    title: str                 # "Audio Doctor"
    platforms: FrozenSet[str]  # e.g. frozenset({"windows"})
    domains: FrozenSet[str]    # StationSnapshot fields it reads

    def run(self, snap: StationSnapshot) -> List[CheckResult]: ...


# ---------------------------------------------------------------------------
# Registries: doctors (display order) and per-domain snapshot gatherers
# ---------------------------------------------------------------------------

_DOCTORS: List[Doctor] = []

# domain name -> zero-arg callable returning that domain's snapshot value.
# Domains whose probes live in this package are pre-registered below;
# app-side domains (e.g. 'audio') are registered by the consumer.
_GATHERERS: Dict[str, Callable[[], object]] = {}


def register(doctor: Doctor) -> Doctor:
    """Add a doctor (display order = registration order). Duplicate ids
    are a programming error."""
    if any(d.id == doctor.id for d in _DOCTORS):
        raise ValueError(f"doctor id {doctor.id!r} already registered")
    _DOCTORS.append(doctor)
    return doctor


def registered_doctors() -> List[Doctor]:
    return list(_DOCTORS)


def snapshot_domains() -> FrozenSet[str]:
    """The valid domain names: StationSnapshot's non-meta fields."""
    return frozenset(f.name for f in dataclasses.fields(StationSnapshot)
                     if f.name not in SNAPSHOT_META_FIELDS)


def register_gatherer(domain: str,
                      fn: Callable[[], object]) -> Callable[[], object]:
    """Register (or replace) the probe callable for a snapshot domain.
    Unknown domain names fail fast — setattr on a dataclass would
    otherwise silently create a phantom attribute no doctor or report
    ever reads."""
    if domain not in snapshot_domains():
        raise ValueError(
            f"{domain!r} is not a StationSnapshot domain "
            f"(valid: {sorted(snapshot_domains())})")
    _GATHERERS[domain] = fn
    return fn


def _reset_for_tests() -> None:
    """Test hook: clear doctors and restore the built-in gatherers."""
    _DOCTORS.clear()
    _GATHERERS.clear()
    _register_builtin_gatherers()


# ---------------------------------------------------------------------------
# Snapshot gathering
# ---------------------------------------------------------------------------

def _gather_apps():
    # Local imports keep registry importable without pulling the probe
    # modules until a checkup actually needs them.
    from diagnostics.probe_apps import ConfigFileReader, RunningAppDetector
    apps = ConfigFileReader().discover_configs()
    running = {name.casefold() for name in RunningAppDetector.detect()}
    for app in apps:
        app.is_running = app.name.casefold() in running
    return apps


def _gather_udp_ports():
    from diagnostics.probe_apps import ConfigFileReader
    from diagnostics.probe_ports import PortScanner
    # Config-referenced ports must be scanned even outside the
    # conventional range (the 4242 daisy-chain lesson). This re-reads the
    # configs because gatherers are independent by design — usually a
    # cheap known-paths pass, though on machines with NO configs it
    # repeats the broader fallback search; acceptable for a
    # user-initiated checkup.
    extra = {a.udp_port for a in ConfigFileReader().discover_configs()
             if a.udp_port}
    return PortScanner.scan_udp_ports(extra_ports=extra)


def _gather_clock():
    from diagnostics.probe_clock import gather_clock
    return gather_clock()


def _gather_system():
    from diagnostics.probe_system import gather_system
    return gather_system()


def _register_builtin_gatherers() -> None:
    _GATHERERS.setdefault('apps', _gather_apps)
    _GATHERERS.setdefault('udp_ports', _gather_udp_ports)
    _GATHERERS.setdefault('clock', _gather_clock)
    _GATHERERS.setdefault('system', _gather_system)


_register_builtin_gatherers()


def gather_snapshot(domains: Iterable[str]) -> StationSnapshot:
    """One probe pass over the requested domains. Failures never raise:
    the domain stays None and the failure is recorded in `errors`
    (Contract 1's "not gathered" semantics). Runs probe I/O — worker
    thread only."""
    snap = StationSnapshot(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        taken_at_utc=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        platform=current_platform(),
        os_detail=platform_mod.platform(),
    )
    for domain in sorted(set(domains)):
        if domain not in snapshot_domains():
            # A doctor declared a domain that isn't a snapshot field
            # (register_gatherer already rejects these at wiring time).
            snap.errors.append(f"{domain}: not a snapshot domain")
            continue
        fn = _GATHERERS.get(domain)
        if fn is None:
            snap.errors.append(f"{domain}: no gatherer registered")
            continue
        try:
            setattr(snap, domain, fn())
        except Exception as e:
            logger.exception(f"Diagnostics: gathering {domain!r} failed")
            snap.errors.append(f"{domain}: {e}")
    return snap


# ---------------------------------------------------------------------------
# Checkup
# ---------------------------------------------------------------------------

@dataclass
class DoctorRun:
    """One doctor's results within a checkup."""
    doctor_id: str
    title: str
    results: List[CheckResult] = field(default_factory=list)


@dataclass
class SkippedDoctor:
    """A doctor that did not run, and why — reported under "Not checked",
    never silently absent (spec principle 3)."""
    doctor_id: str
    title: str
    reason: str


@dataclass
class CheckupRun:
    """Everything one checkup produced; input to report rendering."""
    snapshot: StationSnapshot
    entries: List[DoctorRun] = field(default_factory=list)
    skipped: List[SkippedDoctor] = field(default_factory=list)


def run_checkup(doctors: Optional[Iterable[Doctor]] = None,
                snapshot: Optional[StationSnapshot] = None,
                extra_domains: Optional[Iterable[str]] = None) -> CheckupRun:
    """Run a checkup: gather once, then every applicable doctor over the
    same snapshot.

    doctors: explicit doctor list (display order); defaults to the
        registry. A single-doctor list is the per-menu-item re-run path.
    snapshot: pre-gathered snapshot to reuse (skips probing — used by
        tests and re-renders); default gathers the union of the
        applicable doctors' declared domains.
    extra_domains: context domains to gather beyond what doctors declare.
        The report's Station identity line and Details tables read
        domains no current doctor may declare (e.g. 'apps' for
        callsign/grid until the Config Doctor exists) — the consumer
        requests them here.
    """
    doctor_list = list(doctors) if doctors is not None else list(_DOCTORS)
    plat = current_platform()
    applicable = [d for d in doctor_list if plat in d.platforms]
    skipped = [SkippedDoctor(d.id, d.title, f"not supported on {plat}")
               for d in doctor_list if plat not in d.platforms]

    if snapshot is None:
        domains = set(extra_domains or ())
        for d in applicable:
            domains |= set(d.domains)
        snapshot = gather_snapshot(domains)

    entries = []
    for d in applicable:
        try:
            entries.append(DoctorRun(d.id, d.title, list(d.run(snapshot))))
        except Exception as e:
            logger.exception(f"Diagnostics: doctor {d.id!r} crashed")
            skipped.append(SkippedDoctor(d.id, d.title, f"crashed: {e}"))

    return CheckupRun(snapshot=snapshot, entries=entries, skipped=skipped)
