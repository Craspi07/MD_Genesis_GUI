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

Two known false-positive sources, found 2026-09-18 by reading the real
GENESIS 2.1.6.1 source (github.com/genesis-release-r-ccs/genesis):

1. A keyword's own comment can itself contain a bracketed list that
   documents *another* keyword's allowed values, not its own -- e.g.
   `src/atdyn/at_ensemble.fpp`'s `show_ctrl_ensemble` prints
   `# gamma_t = 1.0  # thermostat friction (ps-1) in [LANGEVIN]`: that
   `[LANGEVIN]` says "this parameter only matters when tpcontrol=
   LANGEVIN", not "gamma_t may only equal LANGEVIN". The old, unanchored
   bracket search treated any `[...]` found anywhere in a comment as an
   enum, so `gamma_t = 0.01` against that comment produced the
   nonsensical "not in this build's allowed values ['LANGEVIN']". Fixed
   by requiring the *entire* trailing comment to be nothing but the
   bracket list -- true allowed-value comments in the real source really
   are bare, e.g. `tpcontrol = NO # [NO,BERENDSEN,BUSSI,LANGEVIN]`. The
   tradeoff: a genuine enum whose comment has a few words before the
   bracket (e.g. `dispersion_corr`'s real
   `# dispersion correction [NONE,Energy,EPress]`) now goes unchecked
   instead of checked -- accepted deliberately, since a missed check is
   far better than an actively wrong one.

2. `atdyn`'s own `-h ctrl_all` [ENERGY] output is stale for RESIDCG:
   `show_ctrl_energy` (`src/atdyn/at_energy.fpp`) prints
   `forcefield = CHARMM # [CHARMM,AAGO,CAGO,KBGO,AMBER,GROAMBER,
   GROMARTINI]` and never mentions any `cg_*` keyword at all -- but the
   actual reader, `read_ctrl_energy`, validates `forcefield` against the
   full `ForceFieldTypes` array in `at_enefunc_str.fpp` (10 entries,
   ending in `'RESIDCG   '` with a trailing `!shinobu-edited` comment --
   added after `show_ctrl_energy`'s help text was written, and evidently
   never backported there) and does read every `cg_cutoffdist_ele`/
   `cg_cutoffdist_126`/`cg_pairlistdist_ele`/`cg_pairlistdist_126`/
   `cg_sol_ionic_strength`/`cg_IDR_HPS_epsilon` keyword this app's CG
   templates generate (`call read_ctrlfile_real(handle, Section,
   'cg_cutoffdist_ele', ...)` etc., each with its own real default).
   `forcefield = RESIDCG` and these keywords are genuinely valid GENESIS
   2.1.6 input -- confirmed both by that source and by the real,
   GENESIS-team-maintained tutorial 11.1's own `pro.inp` (see
   genesis_tutorial_materials), which uses exactly this combination.
   `_KNOWN_CTRL_ALL_DOC_GAPS` below annotates (not suppresses) warnings
   for exactly these cases with this explanation, rather than baking a
   silent allowlist into the comparison -- a human still sees the
   warning and the reason it's very likely a false positive, per this
   module's own "advisory, human reviews" design.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from app.wsl import WslBridge

_SECTION_LINE = re.compile(r"^\[([A-Za-z_][A-Za-z0-9_]*)\]\s*$")
_KEYWORD_LINE = re.compile(r"^#?\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^#]*?)\s*(?:#\s*(.*))?$")
# Anchored, whole-comment match -- see module docstring point 1: a
# bracketed list appearing only *somewhere* inside a longer descriptive
# comment documents a different keyword, not this one's own allowed values.
_BRACKET_LIST = re.compile(r"^\[([^\]]*)\]$")

# Reference type: {SECTION: {keyword: allowed_values_or_None}}
Reference = Dict[str, Dict[str, Optional[List[str]]]]

# {(SECTION, keyword, value-or-None-for-any-value): explanation}. Checked
# by validate_control_text() before it emits a warning for that exact
# (section, keyword[, value]) -- see module docstring point 2.
_KNOWN_CTRL_ALL_DOC_GAPS = {
    ("ENERGY", "forcefield", "RESIDCG"): (
        "GENESIS 2.1.6's atdyn -h ctrl_all forcefield comment predates RESIDCG being "
        "added to ForceFieldTypes (at_enefunc_str.fpp) -- read_ctrl_energy validates "
        "against that full list, not the shorter -h ctrl_all comment. Very likely a "
        "false positive; see DECISIONS.md."
    ),
    **{
        ("ENERGY", keyword, None): (
            f"GENESIS 2.1.6's atdyn -h ctrl_all doesn't document '{keyword}' at all, but "
            "read_ctrl_energy (at_energy.fpp) does read it with a real default -- this app's "
            "RESIDCG/HPS/AICG2+ templates need it. Very likely a false positive; see DECISIONS.md."
        )
        for keyword in (
            "cg_cutoffdist_ele",
            "cg_cutoffdist_126",
            "cg_pairlistdist_ele",
            "cg_pairlistdist_126",
            "cg_sol_ionic_strength",
            "cg_IDR_HPS_epsilon",
        )
    },
}


def _known_doc_gap(section: str, keyword: str, value: str) -> Optional[str]:
    return _KNOWN_CTRL_ALL_DOC_GAPS.get((section, keyword, value)) or _KNOWN_CTRL_ALL_DOC_GAPS.get(
        (section, keyword, None)
    )


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
            bracket_match = _BRACKET_LIST.match(comment.strip())
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
            note = _known_doc_gap(section, keyword, value)
            suffix = f" ({note})" if note else ""
            warnings.append(f"[{section}] {keyword}: not a recognized keyword for this GENESIS build{suffix}")
            continue
        allowed = section_ref[keyword]
        if allowed is not None and value not in allowed:
            note = _known_doc_gap(section, keyword, value)
            suffix = f" ({note})" if note else ""
            warnings.append(
                f"[{section}] {keyword} = {value}: not in this build's allowed values {allowed}{suffix}"
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
