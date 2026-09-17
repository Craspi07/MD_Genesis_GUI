"""Import a CHARMM-GUI "Input Generator > GENESIS" output archive (.tgz)
into the all-atom wizard page, without the user ever having to open the
archive by hand.

CHARMM-GUI's download is a gzipped tarball. Windows Explorer has no
built-in way to open .tar.gz/.tgz (only .zip) -- but that's a Windows
Explorer limitation, not a limitation of this app. Python's stdlib
`tarfile` module decompresses gzip tarballs via its own zlib binding, no
external `tar` binary and no WSL round-trip required, so this runs
entirely on the Windows side exactly like app/project_creation.py's own
source_pdb_path handling (a plain file copy, no WslBridge involved) --
extraction here is that same kind of "local, no-WSL-needed" operation,
just for an archive instead of a single file.

When the user selects GENESIS as the target program in CHARMM-GUI's Input
Generator, the archive includes a self-contained genesis/ subdirectory
with GENESIS-ready control files (step6.0_minimization.inp, step6.1-6.6_
equilibration.inp, step7_production.inp) -- confirmed against the real
GENESIS tutorials 6.1/6.2 (mdgenesis.org/tutorials/genesis_tutorial_6.1_
2022/, .../6.2_2022/) and their own materials (genesis_tutorial_materials/
tutorial-6.1/2_min_equil/step6.0_minimization.inp, which
tests/fixtures/charmm_gui_step6.0_minimization.inp is a trimmed copy of).
That first-stage .inp already states, in its own [INPUT]/[BOUNDARY]
sections, exactly which topfile/parfile/strfile/psffile/pdbfile the
system needs and the box_size_x/y/z GENESIS should use. CHARMM-GUI ships
its *entire* CHARMM36 toppar/ library (40+ files) in every archive
regardless of what a given system actually uses (confirmed by inspecting
genesis_tutorial_materials/tutorial-6.2/1_setup/toppar/), so this module
reads CHARMM-GUI's own answer out of that one file rather than guessing
by scanning toppar/ itself.
"""
from __future__ import annotations

import re
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

_REQUIRED_INPUT_KEYS = ("topfile", "parfile", "psffile", "pdbfile")


@dataclass
class CharmmGuiImportResult:
    success: bool
    message: str
    top_paths: List[str] = field(default_factory=list)
    par_paths: List[str] = field(default_factory=list)
    str_paths: List[str] = field(default_factory=list)
    psf_path: str = ""
    pdb_path: str = ""
    box_x: Optional[float] = None
    box_y: Optional[float] = None
    box_z: Optional[float] = None


def _parse_inp_sections(text: str) -> Dict[str, Dict[str, str]]:
    """Pull [SECTION] key = value pairs out of a GENESIS .inp file.

    Only used to read a handful of known keys out of a CHARMM-GUI-
    generated file -- not a general round-trip parser (see
    app/control_file.py for this app's own writer side).
    """
    sections: Dict[str, Dict[str, str]] = {}
    current: Optional[str] = None
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.match(r"^\[(\w+)\]$", line)
        if match:
            current = match.group(1).lower()
            sections[current] = {}
            continue
        if current is None or "=" not in line:
            continue
        key, _, value = line.partition("=")
        sections[current][key.strip().lower()] = value.strip()
    return sections


def _split_values(raw: str) -> List[str]:
    return [v.strip() for v in raw.split(",") if v.strip()]


def _to_float(raw: Optional[str]) -> Optional[float]:
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def import_charmm_gui_archive(archive_path: str) -> CharmmGuiImportResult:
    """Extract `archive_path` (a CHARMM-GUI .tgz) into a fresh temp
    directory and read its genesis/step*.inp for the files/box size this
    system actually needs. Returns plain local filesystem paths, usable
    exactly like a manual file-picker selection would populate
    Project.aa_*_source_paths -- app/project_creation.py's existing
    copy_all_atom_files() picks up from there unchanged. The temp
    directory is deliberately left for the OS to reclaim rather than
    cleaned up here, the same way a user's own manually-browsed source
    files (e.g. from their Downloads folder) already aren't tracked or
    deleted by this app.
    """
    staging = Path(tempfile.mkdtemp(prefix="charmm_gui_import_"))

    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            # filter="data" (Python 3.12+) rejects absolute paths, `..`
            # traversal, device files, etc. -- CHARMM-GUI's own archives
            # are trusted, but there's no reason to extract one without
            # this guard against a malformed or tampered file.
            archive.extractall(staging, filter="data")
    except (tarfile.TarError, OSError) as exc:
        return CharmmGuiImportResult(False, f"Could not extract '{archive_path}': {exc}")

    candidates = sorted(staging.glob("**/genesis/step*.inp"))
    if not candidates:
        return CharmmGuiImportResult(
            False,
            "No genesis/step*.inp found in this archive. In CHARMM-GUI's Input Generator, "
            "make sure GENESIS is selected as the target MD program so the download "
            "includes a genesis/ folder with ready-made control files.",
        )
    inp_path = candidates[0]

    try:
        text = inp_path.read_text(errors="replace")
    except OSError as exc:
        return CharmmGuiImportResult(False, f"Could not read '{inp_path.name}': {exc}")

    sections = _parse_inp_sections(text)
    input_section = sections.get("input", {})
    boundary_section = sections.get("boundary", {})

    missing = [key for key in _REQUIRED_INPUT_KEYS if key not in input_section]
    if missing:
        return CharmmGuiImportResult(
            False, f"'{inp_path.name}' is missing expected [INPUT] keys: {', '.join(missing)}."
        )

    def _resolve(names: List[str]) -> Optional[List[str]]:
        resolved = []
        for name in names:
            candidate = (inp_path.parent / name).resolve()
            if not candidate.exists():
                return None
            resolved.append(str(candidate))
        return resolved

    top_paths = _resolve(_split_values(input_section["topfile"]))
    par_paths = _resolve(_split_values(input_section["parfile"]))
    str_names = _split_values(input_section.get("strfile", ""))
    str_paths = _resolve(str_names) if str_names else []
    psf_paths = _resolve(_split_values(input_section["psffile"]))
    pdb_paths = _resolve(_split_values(input_section["pdbfile"]))

    if top_paths is None or par_paths is None or str_paths is None or psf_paths is None or pdb_paths is None:
        return CharmmGuiImportResult(False, f"'{inp_path.name}' references a file that doesn't exist in the archive.")

    return CharmmGuiImportResult(
        True,
        f"Imported from '{inp_path.name}'.",
        top_paths=top_paths,
        par_paths=par_paths,
        str_paths=str_paths,
        psf_path=psf_paths[0],
        pdb_path=pdb_paths[0],
        box_x=_to_float(boundary_section.get("box_size_x")),
        box_y=_to_float(boundary_section.get("box_size_y")),
        box_z=_to_float(boundary_section.get("box_size_z")),
    )
