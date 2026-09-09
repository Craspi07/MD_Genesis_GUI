"""Wrappers for GENESIS's own `*_analysis` tools (F5).

Per CLAUDE.md, trajectories are never read across the `\\wsl$` boundary:
every analysis tool here runs entirely inside WSL (via WslBridge) with its
result redirected to a small text file in the project directory, and only
that text file is read back from the GUI process. numpy is used solely to
post-process/plot those already-computed text results, not to recompute
RMSD/Rg/Q-value ourselves.

The `qval_residcg_analysis` binary name comes directly from the project's
stated environment facts (given as ground truth, not fetched this
session). Every other analysis tool name/control-file keyword below could
not be confirmed against mdgenesis.org (blocked this session — see
DECISIONS.md) and is marked `# VERIFY`.
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from app.project import Project
from app.wsl import WslBridge

# analysis_type -> (binary name, output filename, human label)
ANALYSIS_TOOLS = {
    "rmsd": ("rmsd_analysis", "rmsd.txt", "RMSD (vs. initial frame)"),  # VERIFY binary name
    "rg": ("rg_analysis", "rg.txt", "Radius of gyration"),  # VERIFY binary name
    "qvalue": ("qval_residcg_analysis", "qvalue.txt", "Q-value"),  # given in environment facts
    "contact_map": ("distmat_analysis", "contact_map.txt", "Contact map"),  # VERIFY binary name
    "density": ("density_analysis", "density.txt", "Density profile (z)"),  # VERIFY binary name
}


@dataclass
class AnalysisRunResult:
    success: bool
    output_path: Optional[Path]
    log: str


def write_analysis_control_file(
    analysis_type: str, project: Project, local_directory: str, mode: Optional[str] = None
) -> str:
    """Write a minimal control file for one analysis tool and return its
    filename (relative to the project directory). `mode` distinguishes
    variants of the same tool (e.g. contact_map "final" vs
    "time_averaged") via an extra [OPTION] line.

    # VERIFY: GENESIS's real analysis-tool control files likely have
    additional required keywords (atom selections, frame ranges, etc.)
    not represented here; this is a minimal skeleton pending confirmation
    against mdgenesis.org.
    """
    binary, output_name, _label = ANALYSIS_TOOLS[analysis_type]
    directory = Path(local_directory)
    top_files = list(directory.glob(f"{project.name}*.top"))
    gro_files = list(directory.glob(f"{project.name}*.gro"))
    top_name = top_files[0].name if top_files else f"{project.name}.top"
    gro_name = gro_files[0].name if gro_files else f"{project.name}.gro"
    dcd_name = f"{project.name}.dcd"
    output_name = _output_name_for_mode(output_name, mode)

    text = (
        "[INPUT]\n"
        f"grotopfile = {top_name}   # VERIFY\n"
        f"grocrdfile = {gro_name}   # VERIFY\n\n"
        "[TRAJECTORY]\n"
        f"trjfile1 = {dcd_name}     # VERIFY\n\n"
        "[OUTPUT]\n"
        f"outfile = {output_name}   # VERIFY\n"
    )
    if mode == "time_averaged":
        text += "\n[OPTION]\naverage = YES   # VERIFY\n"
    filename = f"{analysis_type}_{mode}.inp" if mode else f"{analysis_type}.inp"
    (directory / filename).write_text(text)
    return filename


def _output_name_for_mode(output_name: str, mode: Optional[str]) -> str:
    if not mode:
        return output_name
    stem, _, ext = output_name.rpartition(".")
    return f"{stem}_{mode}.{ext}" if stem else f"{output_name}_{mode}"


def run_analysis(
    bridge: WslBridge, analysis_type: str, project: Project, local_directory: str, mode: Optional[str] = None
) -> AnalysisRunResult:
    binary, output_name, _label = ANALYSIS_TOOLS[analysis_type]
    output_name = _output_name_for_mode(output_name, mode)
    control_filename = write_analysis_control_file(analysis_type, project, local_directory, mode=mode)
    command = f"cd {project.directory} && {binary} {shlex.quote(control_filename)}"
    result = bridge.run(command, timeout=300)
    log = (result.stdout or "") + (result.stderr or "")
    output_path = Path(local_directory) / output_name
    if not result.ok:
        return AnalysisRunResult(success=False, output_path=None, log=log)
    if not output_path.exists():
        return AnalysisRunResult(success=False, output_path=None, log=log + "\n(no output file was produced)")
    return AnalysisRunResult(success=True, output_path=output_path, log=log)


# -- parsing (numpy post-processing only, per CLAUDE.md) ---------------------
def parse_two_column_series(text: str) -> Tuple[np.ndarray, np.ndarray]:
    """Parse a whitespace-separated "frame value" text output into two
    numpy arrays. Blank lines and comment lines (starting with # or ;) are
    skipped."""
    xs: List[float] = []
    ys: List[float] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            xs.append(float(parts[0]))
            ys.append(float(parts[1]))
        except ValueError:
            continue
    return np.array(xs), np.array(ys)


def parse_contact_map(text: str) -> np.ndarray:
    """Parse a whitespace-separated matrix (one row per line) into a 2D
    numpy array."""
    rows: List[List[float]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        try:
            rows.append([float(v) for v in line.split()])
        except ValueError:
            continue
    if not rows:
        return np.zeros((0, 0))
    width = max(len(r) for r in rows)
    padded = [r + [0.0] * (width - len(r)) for r in rows]
    return np.array(padded)
