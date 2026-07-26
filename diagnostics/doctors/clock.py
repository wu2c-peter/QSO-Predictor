"""
Clock Doctor — is the system clock good enough for FT8?

FT8's 15-second windows require the clock within roughly a second of
UTC. A drifted clock is the mode's classic silent failure: the waterfall
looks alive, nothing decodes, and nothing reports an error. The probe
(probe_clock) measures the real offset against NTP; these checks are
pure functions over that snapshot.

QSO Predictor
Copyright (C) 2026 Peter Hirst (WU2C)
"""

from typing import List

from diagnostics.models import (CheckResult, ClockSnapshot, Severity,
                                StationSnapshot)

# FT8 tolerance thresholds (seconds of absolute offset). Decodes degrade
# past ~1 s and are effectively gone by ~2 s.
OFFSET_WARN_S = 1.0
OFFSET_FAIL_S = 2.0

_SYNC_FIX = (
    "Enable automatic time synchronization in your operating system's "
    "date & time settings, or run a dedicated NTP client (e.g. Meinberg "
    "NTP on Windows). Then re-run this check."
)


def _check_offset(clock: ClockSnapshot) -> CheckResult:
    if clock.offset_s is None:
        return CheckResult(
            check_id='clock/ntp-offset',
            title='Clock offset could not be measured',
            severity=Severity.UNKNOWN,
            detail='No NTP server was reachable — normal when operating '
                   'offline. Verify the clock another way (e.g. against '
                   'WWV or time.is) before blaming propagation for '
                   'missing decodes.',
        )
    ms = clock.offset_s * 1000
    direction = 'fast' if clock.offset_s >= 0 else 'slow'
    # One decimal place: rounding 999.6 ms up to "1000 ms" would make
    # the OK wording contradict the 1 s threshold it quotes.
    where = f'{abs(ms):.1f} ms {direction} vs {clock.ntp_server}'
    if abs(clock.offset_s) < OFFSET_WARN_S:
        return CheckResult(
            check_id='clock/ntp-offset',
            title='System clock is within FT8 tolerance',
            severity=Severity.OK,
            detail=f'Measured {where} — inside the ~1 s tolerance '
                   f'FT8 needs.',
        )
    if abs(clock.offset_s) < OFFSET_FAIL_S:
        return CheckResult(
            check_id='clock/ntp-offset',
            title='System clock is drifting out of FT8 tolerance',
            severity=Severity.WARNING,
            detail=f'Measured {where}. Decode rates degrade beyond '
                   f'about 1 s of offset.',
            fix=_SYNC_FIX,
        )
    return CheckResult(
        check_id='clock/ntp-offset',
        title='System clock is too far off for FT8',
        severity=Severity.FAIL,
        detail=f'Measured {where}. Beyond about 2 s, FT8 decodes '
               f'effectively stop — this alone explains an empty band.',
        fix=_SYNC_FIX,
    )


def _check_timezone(clock: ClockSnapshot) -> CheckResult:
    if clock.utc_offset_min is None:
        tz = clock.timezone_name or 'unknown'
    else:
        sign = '+' if clock.utc_offset_min >= 0 else '-'
        mins = abs(clock.utc_offset_min)
        tz = (f'{clock.timezone_name} '
              f'(UTC{sign}{mins // 60:02d}:{mins % 60:02d})')
    return CheckResult(
        check_id='clock/timezone',
        title='Timezone (informational)',
        severity=Severity.INFO,
        detail=f'Local timezone is {tz}. Timezone only affects display — '
               f'FT8 needs the underlying UTC to be right, which the '
               f'offset check verifies.',
    )


class ClockDoctor:
    """Doctor-protocol implementation for the clock subsystem."""

    id = 'clock'
    title = 'Clock Doctor'
    platforms = frozenset({'windows', 'macos', 'linux'})
    domains = frozenset({'clock'})

    def run(self, snap: StationSnapshot) -> List[CheckResult]:
        if snap.clock is None:
            return [CheckResult(
                check_id='clock/snapshot-missing',
                title='Clock state could not be gathered',
                severity=Severity.UNKNOWN,
                detail='The clock probe did not produce a snapshot — '
                       'see the probe errors in this report.',
            )]
        return [_check_offset(snap.clock), _check_timezone(snap.clock)]
