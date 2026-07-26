"""
Report rendering — Contract 3 of dev-docs/DIAGNOSTICS_SPEC.md.

One markdown document, identical structure on every platform, written to
be pasted into a forum thread or an LLM chat and read by someone who
cannot see the machine. Section order is stable (helpers and LLMs learn
the layout); the preamble makes the report self-carrying — no separate
prompt needed. Passed checks and not-checked doctors are listed
explicitly: "checked and fine" must be distinguishable from "not
examined".

Privacy: usernames are scrubbed from every rendered string — the exact
home directory (case-insensitive, both slash directions) plus the
generic `\\Users\\<name>` / `/home/<name>` path forms, which also catch
NT device paths (`\\Device\\HarddiskVolumeN\\Users\\<name>\\...`) that
carry no drive letter. Callsign/grid render only when the caller passes
include_identity=True — the toggle covers the Station line AND the
Details dumps.

This wording ships with the first Diagnostics-menu release (spec
migration step 4) and is effectively frozen from then on — helpers and
LLMs learn the layout from circulated reports.

QSO Predictor
Copyright (C) 2026 Peter Hirst (WU2C)
"""

import dataclasses
import json
import re
from enum import Enum
from pathlib import Path
from typing import FrozenSet, List, Optional, Tuple

from diagnostics.models import (CheckResult, SNAPSHOT_META_FIELDS, Severity)
from diagnostics.registry import CheckupRun

# Snapshot fields whose values are station identity, redacted everywhere
# when include_identity=False.
_IDENTITY_FIELDS = frozenset({'callsign', 'grid'})

_USER_DIR_RE = re.compile(r'(?i)([\\/](?:Users|home)[\\/])([^\\/|\s"\']+)')

# Deliberately domain-agnostic: this text is frozen once reports
# circulate, and the set of gathered domains grows with every doctor.
_PREAMBLE = (
    "You are helping an amateur radio operator troubleshoot their "
    "station. Below is a machine-collected snapshot of the PC side of "
    "their setup, plus findings from automated checks. Sections listed "
    "under \"Not checked\" were NOT examined; do not assume they are "
    "healthy. Machine-read facts in this report are more reliable than "
    "anyone's recollection of their settings."
)


def _scrub(text: str) -> str:
    """Strip usernames from path-bearing strings (privacy: they don't
    belong in circulated reports). Covers the exact home dir in either
    slash direction and any case, plus generic Users/home path segments
    (NT device paths included)."""
    home = str(Path.home())
    if home and home != '/':
        text = re.sub(re.escape(home), '~', text, flags=re.IGNORECASE)
        alt = home.replace('\\', '/')
        if alt != home:
            text = re.sub(re.escape(alt), '~', text, flags=re.IGNORECASE)
    return _USER_DIR_RE.sub(r'\g<1>~', text)


def _fmt_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, Enum):
        return value.name
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        # Compact: 0.6000000238418579 (a float32 volume round-tripped
        # through a double) must not render at full precision.
        return f"{value:.6g}"
    if dataclasses.is_dataclass(value):
        # Compact nested-dataclass rendering (e.g. AudioFormat ->
        # "channels=2, sample_rate_hz=48000, bits_per_sample=16")
        return ", ".join(
            f"{f.name}={_fmt_value(getattr(value, f.name))}"
            for f in dataclasses.fields(value))
    return _scrub(str(value))


def _cell(value) -> str:
    """Table-cell rendering: markdown-safe (no pipes/newlines)."""
    return _fmt_value(value).replace("\n", " ").replace("|", "\\|")


def _table(rows: List, redact: FrozenSet[str] = frozenset()) -> List[str]:
    """Markdown table of a homogeneous list of dataclasses. Columns are
    chosen from the field list (not row 0's values), so the schema is
    identical regardless of row order: only fields holding collections
    are excluded; nested dataclasses render compactly."""
    if not rows:
        return ["(none)", ""]
    cols = []
    for f in dataclasses.fields(rows[0]):
        values = [getattr(r, f.name) for r in rows]
        if any(isinstance(v, (list, tuple, dict)) for v in values):
            continue
        cols.append(f.name)
    out = ["| " + " | ".join(cols) + " |",
           "|" + "|".join("---" for _ in cols) + "|"]
    for row in rows:
        out.append("| " + " | ".join(
            "" if c in redact else _cell(getattr(row, c))
            for c in cols) + " |")
    out.append("")
    return out


def _dump_domain(name: str, value,
                 redact: FrozenSet[str] = frozenset()) -> List[str]:
    """Generic per-domain dump: works on any dataclass or list of
    dataclasses without importing its (possibly app-side) type."""
    lines = [f"### {name}", ""]
    if isinstance(value, (list, tuple)):
        lines += _table(list(value), redact)
    elif dataclasses.is_dataclass(value):
        sublists = []
        for f in dataclasses.fields(value):
            v = getattr(value, f.name)
            if isinstance(v, (list, tuple)):
                sublists.append((f.name, list(v)))
            elif f.name not in redact:
                lines.append(f"- {f.name}: {_fmt_value(v) or '(unreadable)'}")
        lines.append("")
        for sub_name, sub in sublists:
            lines.append(f"#### {name}.{sub_name} ({len(sub)})")
            lines.append("")
            if sub and dataclasses.is_dataclass(sub[0]):
                lines += _table(sub, redact)
            else:
                lines += [f"- {_fmt_value(x)}" for x in sub] + [""]
    else:
        lines += [_fmt_value(value), ""]
    return lines


def _identity(checkup: CheckupRun) -> Optional[Tuple[str, str]]:
    for app in (checkup.snapshot.apps or []):
        if app.callsign:
            return app.callsign, app.grid
    return None


def _finding_line(doctor_title: str, r: CheckResult) -> str:
    line = f"- {r.severity.symbol} **{_scrub(r.title)}** — {_scrub(r.detail)}"
    if r.fix:
        line += f" Fix: {_scrub(r.fix)}"
    line += f" _({doctor_title} — {r.check_id})_"
    return line


def render_report(checkup: CheckupRun, tool_name: str, tool_version: str,
                  include_identity: bool = True) -> str:
    """Render one checkup as the standard markdown report."""
    snap = checkup.snapshot
    flat = [(e.title, r) for e in checkup.entries for r in e.results]
    redact = frozenset() if include_identity else _IDENTITY_FIELDS

    lines = [f"# {tool_name} diagnostic report", ""]
    lines += [f"> {_PREAMBLE}", ""]

    # --- Station ---
    lines += ["## Station", ""]
    lines.append(f"- Tool: {tool_name} {tool_version}")
    lines.append(f"- Report schema: {snap.schema_version}")
    lines.append(f"- Platform: {snap.platform} ({snap.os_detail})")
    lines.append(f"- Generated: {snap.taken_at_utc}")
    if include_identity:
        ident = _identity(checkup)
        if ident:
            call, grid = ident
            lines.append(f"- Station: {call}" + (f" ({grid})" if grid else ""))
    else:
        # An anonymized report must be distinguishable from a failed
        # config parse — readers should know the omission is deliberate.
        lines.append("- Station: (withheld by operator)")
    lines.append("")

    # --- Findings (FAIL / WARNING only, worst first) ---
    lines += ["## Findings", ""]
    problems = sorted(
        [(t, r) for t, r in flat if r.severity >= Severity.WARNING],
        key=lambda tr: tr[1].severity, reverse=True)
    if problems:
        lines += [_finding_line(t, r) for t, r in problems]
    else:
        lines.append("No problems found by the checks that ran.")
    lines.append("")

    # --- Passed checks (OK / INFO, grouped by doctor) ---
    lines += ["## Passed checks", ""]
    any_passed = False
    for entry in checkup.entries:
        passed = [r for r in entry.results
                  if r.severity in (Severity.OK, Severity.INFO)]
        if not passed:
            continue
        any_passed = True
        lines.append(f"### {entry.title}")
        lines.append("")
        lines += [f"- {r.severity.symbol} {_scrub(r.title)}" for r in passed]
        lines.append("")
    if not any_passed:
        lines += ["(none)", ""]

    # --- Not checked (skipped doctors + UNKNOWN results) ---
    lines += ["## Not checked", ""]
    unknowns = [(t, r) for t, r in flat if r.severity == Severity.UNKNOWN]
    if checkup.skipped or unknowns:
        lines += [f"- {s.title}: {_scrub(s.reason)}" for s in checkup.skipped]
        lines += [f"- ? {_scrub(r.title)} — {_scrub(r.detail)} "
                  f"_({t} — {r.check_id})_" for t, r in unknowns]
    else:
        lines.append("(everything applicable was checked)")
    lines.append("")

    # --- Details (per-domain snapshot dumps) ---
    lines += ["## Details", ""]
    any_domain = False
    for f in dataclasses.fields(type(snap)):
        if f.name in SNAPSHOT_META_FIELDS:
            continue
        value = getattr(snap, f.name)
        if value is None:
            continue
        any_domain = True
        lines += _dump_domain(f.name, value, redact)
    if not any_domain:
        lines += ["(no domains gathered)", ""]
    if snap.errors:
        lines += ["### Probe errors", ""]
        lines += [f"- {_scrub(e)}" for e in snap.errors] + [""]

    # --- Machine appendix (values scrubbed BEFORE serialization: the
    # markdown-level scrub can't safely reach inside JSON escaping) ---
    appendix = {
        "schema_version": snap.schema_version,
        "findings": [
            {"doctor": e.doctor_id, "check_id": r.check_id,
             "severity": r.severity.name, "title": _scrub(r.title)}
            for e in checkup.entries for r in e.results
            if r.severity >= Severity.WARNING
        ],
    }
    lines += ["## Machine appendix", "", "```json",
              json.dumps(appendix, indent=2, ensure_ascii=False), "```", ""]

    return "\n".join(lines)


def report_filename(tool_name: str, taken_at_utc: str) -> str:
    """`<tool>-report-YYYYMMDD-HHMMZ.md` per the spec."""
    slug = tool_name.lower().replace(" ", "-")
    stamp = (taken_at_utc.replace("-", "").replace(":", "")
             .replace("T", "-")[:13] + "Z")
    return f"{slug}-report-{stamp}.md"
