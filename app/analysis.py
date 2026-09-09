"""Wrappers for GENESIS's own `*_analysis` tools (F5).

Per CLAUDE.md, trajectories are never read across the `\\wsl$` boundary:
every analysis tool here runs entirely inside WSL (via WslBridge) with its
result redirected to a small text file in the project directory, and only
that text file is read back from the GUI process. numpy is used solely to
post-process/plot those already-computed text results, not to recompute
RMSD/Rg/Q-value ourselves.

Confirmed 2026-09-09 against live fetches of mdgenesis.org/docs/examples/
and each tool's own example page (linked from there), plus tutorial 11.1
Section 3 for the CG-specific qval_residcg_analysis case:
- rmsd_analysis: https://mdgenesis.org/examples/rmsd_root-mean-square_deviation_rmsd_analysis/
- rg_analysis: https://mdgenesis.org/examples/radius_of_gyration_rg_analysis/
- distmat_analysis: https://mdgenesis.org/examples/distance-distance_matrix_distmat_analysis/
- density_analysis: https://mdgenesis.org/examples/density_density_analysis/
- qval_residcg_analysis: mdgenesis.org tutorial 11.1 (genesis_tutorial_11.1_2022) Section 3

Every one of those example control files uses [INPUT] psffile/reffile
(atomistic, CHARMM-style) rather than grotopfile/grocrdfile -- except the
CG-specific qval_residcg_analysis example, which uses grotopfile/grocrdfile
exactly like atdyn/cgdyn's own [INPUT] section. Since this app only ever
produces GROMACS-style CG topologies (.top/.gro, RESIDCG forcefield, see
control_file.py), grotopfile/grocrdfile is kept for every tool here on the
strength of that one directly-confirmed CG example plus
mdgenesis.org/docs/usage/'s statement that "basic usage of these tools is
similar to that in the MD simulators" (which do accept grotopfile/
grocrdfile). This is a reasoned inference, not a directly-witnessed
example for rmsd_analysis/rg_analysis/density_analysis/distmat_analysis
specifically -- still marked # VERIFY below. See DECISIONS.md.

Also newly confirmed: no fetched example (rmsd, rg, density, distmat, or
qval) has anything resembling an `average` [OPTION] keyword. The previous
`average = YES` line for "time_averaged" contact-map runs was fabricated
and has been removed -- see write_analysis_control_file's docstring.
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from app.project import Project
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
    output filenames only.

    No GENESIS analysis tool's [OPTION] section (rmsd_analysis,
    rg_analysis, distmat_analysis, density_analysis, or
    qval_residcg_analysis) has an averaging keyword in any fetched
    example -- distmat_analysis's real [OPTION] section only has
    check_only/analysis_atom/matrix_shape (mdgenesis.org/examples/
    distance-distance_matrix_distmat_analysis/). "time_averaged" mode is
    therefore not something GENESIS's control file can express here; this
    function only varies the output filename by mode, and any actual
    time-averaging of a contact map must be done in Python (numpy) over
    multiple analyzed frames -- not implemented, and the UI feature that
    exposes this mode should be reconsidered. # VERIFY / see DECISIONS.md.
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
        f"grotopfile = {top_name}   # VERIFY: confirmed for CG mode only via qval_residcg_analysis "
        "(mdgenesis.org tutorial 11.1 Section 3); inferred (not directly witnessed) for the other tools here -- see module docstring\n"
        f"grocrdfile = {gro_name}   # VERIFY: see grotopfile note above\n\n"
        "[TRAJECTORY]\n"
        f"trjfile1      = {dcd_name}\n"
        f"md_step1      = {project.parameters.n_steps}   # confirmed keyword; present in every fetched analysis-tool example\n"
        f"mdout_period1 = {project.parameters.output_frequency}   # confirmed keyword; present in every fetched analysis-tool example\n"
        "trj_format    = DCD    # confirmed keyword+value in every fetched analysis-tool example\n"
        "trj_type      = COOR+BOX   # confirmed keyword+value in every fetched analysis-tool example\n\n"
        "[SELECTION]\n"
        "group1 = all   # VERIFY: every fetched example defines an atom-name/segid selection (e.g. \"an: CA\", \"segid:BPTI\") "
        "rather than a bare \"all\"; kept as the simplest selection since this app doesn't yet expose per-residue selection in the UI\n\n"
        "[OUTPUT]\n"
        f"{output_keyword} = {output_name}   # confirmed keyword name for {binary} -- see module docstring citations\n"
    )
    if analysis_type == "density":
        text += (
            "\n; VERIFY: density_analysis's real example control file "
            "(mdgenesis.org/examples/density_density_analysis/) also has "
            "[BOUNDARY]/[ENSEMBLE]/[FITTING]/[SPANA_OPTION]/[DENSITY_OPTION] "
            "sections (domain_x/y/z, num_cells_x/y/z, density_type, "
            "voxel_size, recenter, etc.) that this minimal skeleton does "
            "not generate -- a real WSL run of this file will likely need "
            "those filled in before it works.\n"
        )
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
