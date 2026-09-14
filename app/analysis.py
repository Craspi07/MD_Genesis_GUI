"""Wrappers for GENESIS's own `*_analysis` tools (F5).

Per CLAUDE.md, trajectories are never read across the `\\wsl$` boundary:
every analysis tool here runs entirely inside WSL (via WslBridge) with its
result redirected to a small text file in the project directory, and only
that text file is read back from the GUI process. numpy is used solely to
post-process/plot those already-computed text results, not to recompute
RMSD/Rg/Q-value ourselves.

Per-tool binary/keyword citations are kept short in the generated files
and in ANALYSIS_TOOLS below; see DECISIONS.md for the full source list
(mdgenesis.org/docs/examples/ per-tool pages, tutorial 11.1 Section 3 for
qval_residcg_analysis) and for what's still `# VERIFY` (mainly whether
grotopfile/grocrdfile is valid [INPUT] for the non-CG-specific tools --
only directly witnessed for qval_residcg_analysis).
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from app.project import Project
from app.text_io import write_generated_text
from app.wsl import WslBridge

# analysis_type -> (binary name, output keyword, output filename, human label)
# The output keyword differs per tool (confirmed from each tool's own
# example page -- see module docstring); there is no single generic
# "outfile" keyword shared by all of them.
ANALYSIS_TOOLS = {
    "rmsd": ("rmsd_analysis", "rmsfile", "rmsd.txt", "RMSD (vs. initial frame)"),
    "rg": ("rg_analysis", "rgfile", "rg.txt", "Radius of gyration"),
    "qvalue": ("qval_residcg_analysis", "qntfile", "qvalue.txt", "Q-value"),
    "contact_map": ("distmat_analysis", "outfile", "contact_map.txt", "Contact map"),
    "density": ("density_analysis", "mapfile", "density.ccp4", "Density profile (z)"),
}

# GENESIS binary names, [OUTPUT] keyword names, and (for rmsd/rg/distmat)
# the [SELECTION]/[OPTION] pattern are all confirmed per-tool from the
# example pages cited in the module docstring. qval_residcg_analysis is
# additionally confirmed end-to-end (full [INPUT]/[OUTPUT]/[TRAJECTORY]/
# [SELECTION]/[OPTION]) from tutorial 11.1 Section 3.


@dataclass
class AnalysisRunResult:
    success: bool
    output_path: Optional[Path]
    log: str


def write_analysis_control_file(
    analysis_type: str, project: Project, local_directory: str, mode: Optional[str] = None
) -> str:
    """Write a control file for one analysis tool and return its filename
    (relative to the project directory). `mode` distinguishes variants of
    the same tool (contact_map "final" vs "time_averaged") via distinct
    output filenames only -- no GENESIS analysis tool's [OPTION] section
    has an averaging keyword (see DECISIONS.md), so an actual
    time-averaged contact map would need Python-side (numpy)
    post-processing over multiple frames, not implemented here.
    """
    binary, output_keyword, output_name, _label = ANALYSIS_TOOLS[analysis_type]
    directory = Path(local_directory)
    top_files = list(directory.glob(f"{project.name}*.top"))
    gro_files = list(directory.glob(f"{project.name}*.gro"))
    top_name = top_files[0].name if top_files else f"{project.name}.top"
    gro_name = gro_files[0].name if gro_files else f"{project.name}.gro"
    dcd_name = f"{project.name}.dcd"
    output_name = _output_name_for_mode(output_name, mode)

    text = (
        "[INPUT]\n"
        f"grotopfile = {top_name}\n"
        f"grocrdfile = {gro_name}\n\n"
        "[TRAJECTORY]\n"
        f"trjfile1      = {dcd_name}\n"
        f"md_step1      = {project.parameters.n_steps}\n"
        f"mdout_period1 = {project.parameters.output_frequency}\n"
        "trj_format    = DCD\n"
        "trj_type      = COOR+BOX\n\n"
        "[SELECTION]\n"
        "group1 = all\n\n"
        "[OUTPUT]\n"
        f"{output_keyword} = {output_name}\n"
    )
    if analysis_type == "density":
        text += (
            "# density_analysis also needs BOUNDARY/ENSEMBLE/FITTING/\n"
            "# SPANA_OPTION/DENSITY_OPTION sections not generated here -- see DECISIONS.md\n"
        )
    filename = f"{analysis_type}_{mode}.inp" if mode else f"{analysis_type}.inp"
    write_generated_text(directory / filename, text)
    return filename


def _output_name_for_mode(output_name: str, mode: Optional[str]) -> str:
    if not mode:
        return output_name
    stem, _, ext = output_name.rpartition(".")
    return f"{stem}_{mode}.{ext}" if stem else f"{output_name}_{mode}"


def run_analysis(
    bridge: WslBridge, analysis_type: str, project: Project, local_directory: str, mode: Optional[str] = None
) -> AnalysisRunResult:
    binary, _output_keyword, output_name, _label = ANALYSIS_TOOLS[analysis_type]
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
