"""
Audio Doctor as a registered doctor (DIAGNOSTICS_SPEC.md migration step 3).

Adapter around the existing `probe_windows.gather_snapshot()` /
`checks.run_checks()` pair, so Audio Doctor participates in Full Checkup
alongside future doctors. Lives app-side (in audio_doctor/, not
diagnostics/) per the spec's import-direction rule: app -> diagnostics,
never back. The standalone Audio Doctor dialog is untouched and keeps
calling the probe/checks directly.

The consumer wires it up with one call:

    from audio_doctor.doctor import register
    register(rig_hint=config_value_or_None)

QSO Predictor
Copyright (C) 2026 Peter Hirst (WU2C)
"""

import logging
import sys
from typing import Callable, List, Optional, Sequence, Union

from diagnostics import registry
from diagnostics.models import CheckResult, Severity, StationSnapshot
from audio_doctor import probe_windows
from audio_doctor.checks import run_checks

logger = logging.getLogger(__name__)

# A rig hint may be the string itself, or a zero-arg callable returning
# it — the callable is evaluated per checkup, so a hint the user edits
# in the Audio Doctor dialog (persisted to config at runtime) is always
# read fresh instead of frozen at registration.
RigHint = Union[str, Callable[[], Optional[str]]]


def gather_audio():
    """Domain gatherer for 'audio' — worker thread only (COM).

    Off-Windows this returns None (domain "not gathered", no error
    noise): other doctors legitimately declare 'audio' cross-platform —
    the Config Doctor's binding check reads it — so a macOS checkup
    requesting it is normal, not a failure. On WINDOWS with the probe
    unavailable it raises: that's a real dependency problem the report's
    probe errors should surface, and it keeps AudioDoctor.run() on its
    UNKNOWN path rather than running checks against a half-gathered
    snapshot."""
    if not probe_windows.available():
        if sys.platform == 'win32':
            raise RuntimeError(
                'audio probe unavailable (pycaw/comtypes not installed)')
        return None
    with probe_windows.com_initialized():
        return probe_windows.gather_snapshot()


class AudioDoctor:
    """Doctor-protocol wrapper over the audio checks."""

    id = 'audio'
    title = 'Audio Doctor'
    platforms = frozenset({'windows'})
    domains = frozenset({'audio'})

    def __init__(self, rig_hint: Optional[RigHint] = None,
                 app_names: Optional[Sequence[str]] = None,
                 browser_tx=False):
        self._rig_hint = rig_hint
        self._app_names = app_names
        # bool or zero-arg callable, resolved per run like rig_hint:
        # FT8web-as-source makes browser codec streams expected.
        self._browser_tx = browser_tx

    def _resolve_rig_hint(self) -> Optional[str]:
        hint = self._rig_hint() if callable(self._rig_hint) else self._rig_hint
        hint = (hint or '').strip()
        return hint or None     # falsy/whitespace -> checks' default

    def run(self, snap: StationSnapshot) -> List[CheckResult]:
        if snap.audio is None:
            # Applicable platform but the domain wasn't gathered — the
            # probe failed (see snapshot.errors). Framework-era check,
            # so the id carries the doctor namespace.
            return [CheckResult(
                check_id='audio/snapshot-missing',
                title='Audio state could not be gathered',
                severity=Severity.UNKNOWN,
                detail='The Windows audio probe did not produce a '
                       'snapshot — see the probe errors in this report.',
            )]
        kwargs = {}
        hint = self._resolve_rig_hint()
        if hint:
            kwargs['rig_hint'] = hint
        if self._app_names:
            kwargs['app_names'] = self._app_names
        kwargs['browser_tx'] = bool(
            self._browser_tx() if callable(self._browser_tx)
            else self._browser_tx)
        return run_checks(snap.audio, **kwargs)


def register(rig_hint: Optional[RigHint] = None,
             app_names: Optional[Sequence[str]] = None,
             browser_tx=False) -> AudioDoctor:
    """Register the Audio Doctor and its domain gatherer. Call once at
    app startup (or from the standalone tester's assembly). Pass
    zero-arg callables reading live state for rig_hint / browser_tx —
    not frozen values — so checkups always use current settings."""
    registry.register_gatherer('audio', gather_audio)
    return registry.register(AudioDoctor(rig_hint=rig_hint,
                                         app_names=app_names,
                                         browser_tx=browser_tx))
