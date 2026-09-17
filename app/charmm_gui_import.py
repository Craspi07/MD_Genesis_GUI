"""Extract a CHARMM-GUI download (.tgz) so its files can be picked from a
normal folder instead of an archive Windows Explorer can't open.

CHARMM-GUI's download is a gzipped tarball. Windows Explorer has no
built-in way to open .tar.gz/.tgz (only .zip) -- but that's a Windows
Explorer limitation, not a limitation of this app. Python's stdlib
`tarfile` module decompresses gzip tarballs via its own zlib binding, no
external `tar` binary and no WSL round-trip required, so this runs
entirely on the Windows side exactly like app/project_creation.py's own
source_pdb_path handling (a plain file copy, no WslBridge involved) --
extraction here is that same kind of "local, no-WSL-needed" operation,
just for an archive instead of a single file.

Solution Builder (the CHARMM-GUI module this app's users actually use,
per direct confirmation -- there is no "select GENESIS as the target
program" step in that workflow, unlike the Membrane Builder tutorials
this module originally assumed) does not ship a ready-made control file
naming exactly which of its bundled toppar/ files a system needs. So
this module does NOT try to guess that: it only auto-detects what's safe
to auto-detect --

- the final prepared system, by finding the highest-numbered
  stepN_input.psf/.pdb pair Solution/Membrane Builder writes (the
  lower-numbered stepN_* files along the way -- step1_pdbreader,
  step2_orient, etc. -- are intermediate stages, not the final system);
- the box size, by reading the CRYST1 record from that PDB -- a public,
  stable field of the PDB file format itself (columns 7-15/16-24/25-33
  for a/b/c in Angstroms; see the PDB format spec v3.3, "CRYST1" record).
  This app's own app/validators.py already relies on the same
  fixed-column PDB convention for ATOM records, so this isn't a new
  parsing convention for the codebase.

Topology/parameter/stream file selection (the .rtf/.prm/.str files) is
deliberately left to the user via the existing file pickers, just
pointed at the extracted toppar/ folder instead of a blank dialog --
CHARMM-GUI bundles its *entire* CHARMM36 toppar/ library (40+ files) in
every archive regardless of what a given system actually uses (confirmed
by inspecting genesis_tutorial_materials/tutorial-6.2/1_setup/toppar/),
and which handful of those files a specific system needs (e.g. protein
vs. protein+lipid vs. a ligand's own .str) isn't recoverable from the
archive alone without guessing.
"""
from __future__ import annotations

import re
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

_FINAL_STEP_PATTERN = re.compile(r"^step(\d+)_input\.(psf|pdb)$", re.IGNORECASE)


@dataclass
class CharmmGuiExtractResult:
    success: bool
    message: str
    extracted_dir: str = ""
    toppar_dir: str = ""
    psf_path: str = ""
    pdb_path: str = ""
    box_x: Optional[float] = None
    box_y: Optional[float] = None
    box_z: Optional[float] = None


def _find_final_structure_files(root: Path) -> Optional[Tuple[Path, Path]]:
    """Find the highest-numbered stepN_input.psf/.pdb pair -- CHARMM-GUI's
    own naming for the final, fully solvated/ionized system."""
    numbered: Dict[int, Dict[str, Path]] = {}
    for path in root.glob("**/step*_input.*"):
        match = _FINAL_STEP_PATTERN.match(path.name)
        if not match:
            continue
        step = int(match.group(1))
        ext = match.group(2).lower()
        numbered.setdefault(step, {})[ext] = path
    for step in sorted(numbered, reverse=True):
        files = numbered[step]
        if "psf" in files and "pdb" in files:
            return files["psf"], files["pdb"]
    return None


def _parse_cryst1(pdb_path: Path) -> Optional[Tuple[float, float, float]]:
    """Read box a/b/c out of a PDB CRYST1 record, if present."""
    try:
        with pdb_path.open("r", errors="replace") as handle:
            for line in handle:
                if line.startswith("CRYST1"):
                    try:
                        return float(line[6:15]), float(line[15:24]), float(line[24:33])
                    except ValueError:
                        return None
    except OSError:
        return None
    return None


def _find_toppar_dir(root: Path) -> Optional[Path]:
    candidates = [p for p in root.glob("**/toppar") if p.is_dir()]
    return candidates[0] if candidates else None


def extract_charmm_gui_archive(archive_path: str) -> CharmmGuiExtractResult:
    """Extract `archive_path` (a CHARMM-GUI .tgz) into a fresh temp
    directory. The temp directory is deliberately left for the OS to
    reclaim rather than cleaned up here, the same way a user's own
    manually-browsed source files (e.g. from their Downloads folder)
    already aren't tracked or deleted by this app.
    """
    staging = Path(tempfile.mkdtemp(prefix="charmm_gui_import_"))

    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            # filter="data" (Python 3.11.4+/3.12+) rejects absolute
            # paths, ".." traversal, device files, etc. -- CHARMM-GUI's
            # own archives are trusted, but there's no reason to extract
            # one without this guard against a malformed or tampered file.
            archive.extractall(staging, filter="data")
    except (tarfile.TarError, OSError) as exc:
        return CharmmGuiExtractResult(False, f"Could not extract '{archive_path}': {exc}")

    result = CharmmGuiExtractResult(True, "", extracted_dir=str(staging))

    toppar_dir = _find_toppar_dir(staging)
    if toppar_dir is not None:
        result.toppar_dir = str(toppar_dir)

    final_pair = _find_final_structure_files(staging)
    if final_pair is not None:
        psf_path, pdb_path = final_pair
        result.psf_path = str(psf_path)
        result.pdb_path = str(pdb_path)
        box = _parse_cryst1(pdb_path)
        if box is not None:
            result.box_x, result.box_y, result.box_z = box

    message_parts = [f"Extracted to {staging}."]
    if result.psf_path:
        message_parts.append(f"Found {Path(result.psf_path).name} / {Path(result.pdb_path).name}.")
    else:
        message_parts.append("No stepN_input.psf/.pdb pair found automatically.")
    if result.box_x is not None:
        message_parts.append(f"Box from CRYST1: {result.box_x:.3f} x {result.box_y:.3f} x {result.box_z:.3f} A.")
    message_parts.append(
        "Use the Add.../Browse... buttons below to pick your topology/parameter/stream files"
        + (f" from {toppar_dir}." if toppar_dir is not None else " from the extracted folder.")
    )
    result.message = " ".join(message_parts)
    return result
