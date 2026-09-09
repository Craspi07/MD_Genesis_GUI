"""Incremental parser for GENESIS atdyn/cgdyn run.log output.

# VERIFY: this session could not reach mdgenesis.org (network egress
blocked, see DECISIONS.md) to confirm GENESIS's exact log format against
real tutorial output. The format assumed here — a one-time header line of
column names followed by repeated same-width data rows, both prefixed
`INFO:` — matches the tabular energy-output style GENESIS is known to use
in general, but the exact column names/ordering are unconfirmed. Before
relying on this for a real run, capture a real `run.log` from
tutorial 11.1 and adjust `_HEADER_FIRST_TOKEN`/column handling to match.

Parsing is incremental and allocation-light per CLAUDE.md: `feed()` takes
only the newly-tailed text (see app/wsl.py's tail()) and appends parsed
records to a plain Python list; callers (runner.py) are responsible for
only rebuilding any DataFrame/redrawing plots on their own timer, not per
line.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

_HEADER_FIRST_TOKEN = "STEP"
_INFO_PREFIX = "INFO:"

# CG-specific energy terms called out in the original spec (F3) that
# should be surfaced in the Run tab's live plot when present.
CG_SPECIFIC_TERMS = ("NATIVE_CONTACT", "CG_EXV", "CG_DNA_BP", "CG_DNA_EXV")


@dataclass
class LogRecord:
    step: int
    time_ps: float
    values: Dict[str, float] = field(default_factory=dict)


class GenesisLogParser:
    """Stateful, incremental parser: call `feed(new_text)` repeatedly with
    only the bytes appended since the last tail (never the whole file)."""

    def __init__(self) -> None:
        self.columns: Optional[List[str]] = None
        self.records: List[LogRecord] = []
        self._partial_line: str = ""

    def feed(self, new_text: str) -> List[LogRecord]:
        if not new_text:
            return []
        text = self._partial_line + new_text
        lines = text.split("\n")
        # the last chunk may be an incomplete line if the tail landed
        # mid-write; hold it back for the next feed() call.
        if not new_text.endswith("\n"):
            self._partial_line = lines[-1]
            lines = lines[:-1]
        else:
            self._partial_line = ""

        new_records: List[LogRecord] = []
        for raw_line in lines:
            record = self._parse_line(raw_line)
            if record is not None:
                self.records.append(record)
                new_records.append(record)
        return new_records

    def _parse_line(self, raw_line: str) -> Optional[LogRecord]:
        line = raw_line.strip()
        if not line.startswith(_INFO_PREFIX):
            return None
        content = line[len(_INFO_PREFIX):].strip()
        if not content:
            return None
        tokens = content.split()

        if self.columns is None:
            if tokens[0] == _HEADER_FIRST_TOKEN:
                self.columns = tokens
            return None

        if len(tokens) != len(self.columns):
            return None
        try:
            values = [float(t) for t in tokens]
        except ValueError:
            return None

        mapping = dict(zip(self.columns, values))
        try:
            step = int(mapping.pop(_HEADER_FIRST_TOKEN))
        except (KeyError, ValueError):
            return None
        time_ps = mapping.pop("TIME", 0.0)
        return LogRecord(step=step, time_ps=time_ps, values=mapping)

    def latest(self) -> Optional[LogRecord]:
        return self.records[-1] if self.records else None


# -- run-completion / error detection ----------------------------------------
_ERROR_PATTERNS = [
    re.compile(r"error", re.IGNORECASE),
    re.compile(r"segmentation fault", re.IGNORECASE),
    re.compile(r"mpirun.*(fail|abort)", re.IGNORECASE),
]

# MPI "not enough slots" is common under WSL2 (no real network fabric) and
# is auto-retried with --oversubscribe rather than surfaced as fatal (F6).
_SLOT_ERROR_PATTERN = re.compile(r"not enough slots", re.IGNORECASE)


def detect_slot_error(text: str) -> bool:
    return bool(_SLOT_ERROR_PATTERN.search(text))


def detect_error_lines(text: str) -> List[str]:
    return [line for line in text.splitlines() if any(p.search(line) for p in _ERROR_PATTERNS)]
