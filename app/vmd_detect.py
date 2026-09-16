"""Best-effort search for a real vmd.exe install path on Windows.

Settings.vmd_path defaults to a single hardcoded guess
(`C:\\Program Files\\University of Illinois\\VMD\\vmd.exe`), which only
matches one specific VMD installer layout. Real VMD downloads (including
the 2.x alpha builds) commonly install under a version-suffixed folder
name instead (e.g. "VMD 2.0 alpha", "VMD 1.9.4a55"), which that single
guess can't anticipate -- a real, reported gap ("vmd is not found in the
path although it is installed by default"). This module searches a
handful of common install roots, including versioned sibling folders,
rather than assuming there's one true path.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

VMD_EXE_NAME = "vmd.exe"

# Every root VMD's installer has been observed to use, across versions.
# Order matters only in that the first match wins.
VMD_SEARCH_ROOTS = [
    r"C:\Program Files\University of Illinois\VMD",
    r"C:\Program Files (x86)\University of Illinois\VMD",
    r"C:\Program Files\VMD",
    r"C:\Program Files (x86)\VMD",
]


def detect_vmd_path(roots: Optional[List[str]] = None) -> Optional[str]:
    """Return the first real vmd.exe found under `roots` (or
    VMD_SEARCH_ROOTS), checking both the root itself and any
    version-suffixed sibling folder (e.g. "<root> 2.0 alpha"). Returns
    None if nothing is found -- the caller must not guess further."""
    search_roots = roots if roots is not None else VMD_SEARCH_ROOTS
    for root in search_roots:
        root_path = Path(root)

        direct = root_path / VMD_EXE_NAME
        if direct.exists():
            return str(direct)

        parent = root_path.parent
        if not parent.is_dir():
            continue
        for sibling in sorted(parent.glob(f"{root_path.name}*")):
            candidate = sibling / VMD_EXE_NAME
            if candidate.exists():
                return str(candidate)

    return None
