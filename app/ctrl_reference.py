"""Validates a generated GENESIS control file against the real installed
binary's own `-h ctrl_all` template dump, instead of trusting this app's
Jinja templates (built from reading tutorial pages) to stay correct
forever.

This exists because of the VVER_CG saga (see DECISIONS.md, 2026-09-10):
`_common_sections.j2` hardcoded `integrator = VVER_CG`, which is valid on
atdyn but not cgdyn -- a real installed cgdyn rejected it outright. Had
this module existed then, rendering the control file for a cgdyn project
and validating it against `cgdyn -h ctrl_all`'s own
`integrator = LEAP # [LEAP,VVER]` line would have flagged the mismatch
immediately, without needing a real failed benchmark run to discover it.

`-h ctrl_all` output looks like (real output, both engines, 2026-09-10):

    integrator    = LEAP      # [LEAP,VVER]
    nsteps        = 100       # number of MD steps
    # crdout_period = 0         # coordinates output period

Some keywords are commented out (optional, shown at their default) --
still real, valid keywords, just not required. A trailing comment
containing a bracketed comma list (`# [LEAP,VVER]`) documents the
keyword's allowed values; a plain comment (`# number of MD steps`) means
the keyword exists but has no fixed value set to check against.

This is advisory, not a gate: results are warnings a human reviews, not a
hard failure, since this module's own parsing of `-h ctrl_all`'s free-text
comments could itself be incomplete for a GENESIS version/build this
wasn't tested against.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from app.wsl import WslBridge

_SECTION_LINE = re.compile(r"^\[([A-Za-z_][A-Za-z0-9_]*)\]\s*$")
_KEYWORD_LINE = re.compile(r"^#?\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^#]*?)\s*(?:#\s*(.*))?$")
_BRACKET_LIST = re.compile(r"\[([^\]]*)\]")

# Reference type: {SECTION: {keyword: allowed_values_or_None}}
Reference = Dict[str, Dict[str, Optional[List[str]]]]


def parse_ctrl_all(text: str) -> Reference:
    """Parse a `<engine> -h ctrl_all` dump into {section: {keyword:
    allowed_values_or_None}}. Lines outside any `[SECTION]` are ignored
    (a leading banner/usage message, if any, isn't a control-file body)."""
    reference: Reference = {}
    section: Optional[str] = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        section_match = _SECTION_LINE.match(line)
        if section_match:
            section = section_match.group(1).upper()
            reference.setdefault(section, {})
            continue
        if section is None:
            continue
        keyword_match = _KEYWORD_LINE.match(line)
        if not keyword_match:
            continue
        keyword, _value, comment = keyword_match.groups()
        allowed: Optional[List[str]] = None
        if comment:
            bracket_match = _BRACKET_LIST.search(comment)
            if bracket_match:
                allowed = [v.strip() for v in bracket_match.group(1).split(",") if v.strip()]
        reference[section][keyword] = allowed
    return reference


def validate_control_text(control_text: str, reference: Reference) -> List[str]:
    """Compare a rendered control file's `[SECTION] keyword = value` lines
    against a parsed `-h ctrl_all` reference. Returns human-readable
    warning strings; an empty list means nothing looked wrong (not a
    guarantee -- see module docstring)."""
    if not reference:
        return ["reference is empty -- could not parse any [SECTION]s from -h ctrl_all output"]

    warnings: List[str] = []
    section: Optional[str] = None
    for raw_line in control_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        section_match = _SECTION_LINE.match(line)
        if section_match:
            section = section_match.group(1).upper()
            continue
        if section is None or line.startswith("#"):
            continue
        keyword_match = _KEYWORD_LINE.match(line)
        if not keyword_match:
            continue
        keyword, value, _comment = keyword_match.groups()
        value = value.strip()

        section_ref = reference.get(section)
        if section_ref is None:
            warnings.append(f"[{section}] not found in the installed GENESIS's own -h ctrl_all template")
            continue
        if keyword not in section_ref:
            warnings.append(f"[{section}] {keyword}: not a recognized keyword for this GENESIS build")
            continue
        allowed = section_ref[keyword]
        if allowed is not None and value not in allowed:
            warnings.append(
                f"[{section}] {keyword} = {value}: not in this build's allowed values {allowed}"
            )
    return warnings


def validate_against_installed_genesis(bridge: WslBridge, engine: str, control_text: str) -> List[str]:
    """Fetch `<engine> -h ctrl_all` from the real installed binary and
    validate `control_text` against it in one call. Returns a single
    warning describing the fetch failure if the binary couldn't be run,
    rather than raising -- this is meant to degrade to "couldn't check"
    rather than crash a caller."""
    result = bridge.fetch_ctrl_all(engine)
    if not result.ok:
        return [f"could not run '{engine} -h ctrl_all' to validate against: {result.stderr.strip() or 'unknown error'}"]
    reference = parse_ctrl_all(result.stdout)
    return validate_control_text(control_text, reference)
