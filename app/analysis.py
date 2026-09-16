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

from app.control_file import default_box_size
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


def _first_glob(local_directory: str, project_name: str, suffix: str) -> Optional[str]:
    matches = sorted(Path(local_directory).glob(f"{project_name}*{suffix}"))
    return matches[0].name if matches else None


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



# -- RMSF: avecrd_analysis -> flccrd_analysis (Roadmap Phase 2) --------------
# Both tools' [INPUT] is confirmed (mdgenesis.org example pages for
# avecrd_analysis and flccrd_analysis -- see DECISIONS.md) to take
# psffile/reffile, unlike rmsd/rg/qvalue/distmat's grotopfile/grocrdfile;
# GROMACS-format input is not documented as an alternative for either.
# genesis_cg_tool's sequence-input pipeline (cg_protein_structure_builder.jl)
# confirmed writes a .psf alongside .top/.itp/.gro/.pdb (app/cgtool.py); the
# PDB-input pipeline (aa_2_cg.jl --cgpdb) is NOT confirmed to also write
# one. Rather than guess by model_type, RMSF is only offered when a real
# .psf actually exists in the project directory at run time (checked here
# and gated in ui/tab_analysis.py), so this never silently mis-targets an
# AICG2+ project that never got a .psf written.
RMSF_AVECRD_OUTPUT = "{name}_avecrd"
RMSF_OUTPUT_NAME = "{name}_rmsf.rms"


def _trajectory_block(project: Project, extra: bool) -> str:
    """[TRAJECTORY] section shared by every *_analysis control file.

    `extra=True` adds ana_period1/repeat1/trj_natom, present in
    avecrd_analysis's and flccrd_analysis's own documented examples but
    not part of the shorter block already confirmed working for
    rmsd/rg/qvalue/distmat -- kept separate rather than risk changing a
    pattern already proven against a real GENESIS install.
    """
    lines = [
        "[TRAJECTORY]",
        f"trjfile1      = {project.name}.dcd",
        f"md_step1      = {project.parameters.n_steps}",
        f"mdout_period1 = {project.parameters.output_frequency}",
    ]
    if extra:
        lines.append(f"ana_period1   = {project.parameters.output_frequency}")
        lines.append("repeat1       = 1")
    lines.append("trj_format    = DCD")
    lines.append("trj_type      = COOR+BOX")
    if extra:
        lines.append("trj_natom     = 0")
    return "\n".join(lines) + "\n\n"


def rmsf_inputs_available(local_directory: str, project: Project) -> bool:
    psf = _first_glob(local_directory, project.name, ".psf")
    pdb = _first_glob(local_directory, project.name, ".pdb")
    return psf is not None and pdb is not None


def _write_avecrd_control_file(project: Project, local_directory: str, psf: str, pdb: str) -> Tuple[str, str, str]:
    prefix = RMSF_AVECRD_OUTPUT.format(name=project.name)
    ave_name = f"{prefix}_ave.pdb"
    aft_name = f"{prefix}_aft.pdb"
    text = (
        "[INPUT]\n"
        f"reffile = {pdb}\n"
        f"psffile = {psf}\n\n"
        "[OUTPUT]\n"
        f"pdbfile     = {prefix}.pdb\n"
        f"rmsfile     = {prefix}.rms\n"
        f"pdb_avefile = {ave_name}\n"
        f"pdb_aftfile = {aft_name}\n\n"
        + _trajectory_block(project, extra=True)
        + "[SELECTION]\n"
        "group1 = all\n\n"
        "[FITTING]\n"
        "fitting_method = TR+ROT\n"
        "fitting_atom   = 1\n"
        "mass_weight    = NO\n\n"
        "[OPTION]\n"
        "check_only     = NO\n"
        "num_iterations = 10\n"
        "analysis_atom  = 1\n"
    )
    filename = f"{project.name}_avecrd.inp"
    write_generated_text(Path(local_directory) / filename, text)
    return filename, ave_name, aft_name


def _write_flccrd_control_file(
    project: Project, local_directory: str, psf: str, pdb: str, ave_name: str, aft_name: str
) -> Tuple[str, str]:
    rmsf_name = RMSF_OUTPUT_NAME.format(name=project.name)
    text = (
        "[INPUT]\n"
        f"reffile     = {pdb}\n"
        f"psffile     = {psf}\n"
        f"pdb_avefile = {ave_name}\n"
        f"pdb_aftfile = {aft_name}\n\n"
        "[OUTPUT]\n"
        # pcafile/vcvfile/crsfile omitted: not needed for RMSF and every
        # other *_analysis tool's [OUTPUT] keyword is independently
        # optional-by-omission (# VERIFY specifically for flccrd_analysis
        # -- not directly witnessed against a real install)
        f"rmsfile = {rmsf_name}\n\n"
        + _trajectory_block(project, extra=True)
        + "[SELECTION]\n"
        "group1 = all\n\n"
        "[FITTING]\n"
        "fitting_method = TR+ROT\n"
        "fitting_atom   = 1\n"
        "mass_weight    = NO\n\n"
        "[OPTION]\n"
        "check_only    = NO\n"
        "vcv_matrix    = Global\n"
        "analysis_atom = 1\n"
    )
    filename = f"{project.name}_flccrd.inp"
    write_generated_text(Path(local_directory) / filename, text)
    return filename, rmsf_name


def run_rmsf_analysis(bridge: WslBridge, project: Project, local_directory: str) -> AnalysisRunResult:
    """Two-step RMSF pipeline: avecrd_analysis computes the average/fit
    structures flccrd_analysis then measures fluctuation against."""
    psf = _first_glob(local_directory, project.name, ".psf")
    pdb = _first_glob(local_directory, project.name, ".pdb")
    if psf is None or pdb is None:
        return AnalysisRunResult(
            success=False,
            output_path=None,
            log="RMSF needs a .psf and a .pdb file in the project directory "
            "(written by the sequence/HPS structure-builder pipeline); none found here.",
        )

    avecrd_filename, ave_name, aft_name = _write_avecrd_control_file(project, local_directory, psf, pdb)
    avecrd_result = bridge.run(
        f"cd {project.directory} && avecrd_analysis {shlex.quote(avecrd_filename)}", timeout=300
    )
    log = (avecrd_result.stdout or "") + (avecrd_result.stderr or "")
    if not avecrd_result.ok:
        return AnalysisRunResult(success=False, output_path=None, log=log)
    ave_path = Path(local_directory) / ave_name
    aft_path = Path(local_directory) / aft_name
    if not ave_path.exists() or not aft_path.exists():
        return AnalysisRunResult(
            success=False, output_path=None, log=log + "\n(avecrd_analysis did not produce the expected pdb_avefile/pdb_aftfile)"
        )

    flccrd_filename, rmsf_name = _write_flccrd_control_file(project, local_directory, psf, pdb, ave_name, aft_name)
    flccrd_result = bridge.run(
        f"cd {project.directory} && flccrd_analysis {shlex.quote(flccrd_filename)}", timeout=300
    )
    log += "\n" + (flccrd_result.stdout or "") + (flccrd_result.stderr or "")
    output_path = Path(local_directory) / rmsf_name
    if not flccrd_result.ok:
        return AnalysisRunResult(success=False, output_path=None, log=log)
    if not output_path.exists():
        return AnalysisRunResult(success=False, output_path=None, log=log + "\n(no rmsf output was produced)")
    return AnalysisRunResult(success=True, output_path=output_path, log=log)


# -- SASA: sasa_analysis (Roadmap Phase 2) -----------------------------------
# [INPUT]/[OUTPUT]/[BOUNDARY]/[SPANA_OPTION]/[SASA_OPTION] keywords below are
# all confirmed from mdgenesis.org's sasa_analysis example page (see
# DECISIONS.md). Two things are explicitly NOT confirmed and are called out
# rather than guessed silently:
#   - [BOUNDARY]'s domain_x/y/z and num_cells_x/y/z are SPANA's spatial
#     decomposition sizing; the doc example's values were sized for that
#     example's specific box/rank-count, so this uses the smallest possible
#     decomposition (a single domain, single cell) for a serial single-rank
#     analysis run instead of copying numbers that don't apply here -- # VERIFY
#     against a real install if sasa_analysis rejects this as too coarse.
#   - `radi_file` (an atom-radius definition file [SASA_OPTION] requires) has
#     no known default shipped with GENESIS, unlike vmd_path's guessable
#     Windows install path -- so it's a required Settings field
#     (`Settings.sasa_radius_file`) the user must point at a real file
#     instead of a guessed default.
SASA_OUTPUT_NAME = "{name}_sasa.txt"


def sasa_inputs_available(local_directory: str, project: Project) -> bool:
    return rmsf_inputs_available(local_directory, project)


def write_sasa_control_file(project: Project, local_directory: str, radius_file: str, psf: str, pdb: str) -> str:
    box_x, box_y, box_z = default_box_size(project.model_type, project.parameters.box_size_nm)
    output_name = SASA_OUTPUT_NAME.format(name=project.name)
    text = (
        "[INPUT]\n"
        f"psffile = {psf}\n"
        f"reffile = {pdb}\n"
        f"pdbfile = {pdb}\n\n"
        "[OUTPUT]\n"
        f"txtfile = {output_name}\n\n"
        + _trajectory_block(project, extra=True)
        + "[BOUNDARY]\n"
        "type = PBC\n"
        f"box_size_x = {box_x}\n"
        f"box_size_y = {box_y}\n"
        f"box_size_z = {box_z}\n"
        "domain_x = 1\n"
        "domain_y = 1\n"
        "domain_z = 1\n"
        "num_cells_x = 1  # VERIFY: smallest valid decomposition, not confirmed against a real install\n"
        "num_cells_y = 1  # VERIFY\n"
        "num_cells_z = 1  # VERIFY\n\n"
        "[ENSEMBLE]\n"
        "ensemble = NVT\n\n"  # matches this app's CG control files' Langevin NVT (_common_sections.j2)
        "[SELECTION]\n"
        "group1 = all\n\n"
        "[SPANA_OPTION]\n"
        "buffer = 8\n"
        "wrap = yes\n"
        "box_size = TRAJECTORY\n\n"
        "[SASA_OPTION]\n"
        "solute = 1\n"
        f"radi_file = {radius_file}\n"
        "probe_radius = 1.4\n"
        "delta_z = 0.2\n"
        "output_style = history\n"  # per-frame total SASA only, matching parse_two_column_series
        "recenter = 1\n"
    )
    filename = f"{project.name}_sasa.inp"
    write_generated_text(Path(local_directory) / filename, text)
    return filename


def run_sasa_analysis(bridge: WslBridge, project: Project, local_directory: str, radius_file: str) -> AnalysisRunResult:
    if not radius_file:
        return AnalysisRunResult(
            success=False,
            output_path=None,
            log="No SASA radius file configured. Set one in Settings (sasa_analysis's [SASA_OPTION] radi_file).",
        )
    psf = _first_glob(local_directory, project.name, ".psf")
    pdb = _first_glob(local_directory, project.name, ".pdb")
    if psf is None or pdb is None:
        return AnalysisRunResult(
            success=False,
            output_path=None,
            log="SASA needs a .psf and a .pdb file in the project directory "
            "(written by the sequence/HPS structure-builder pipeline); none found here.",
        )
    filename = write_sasa_control_file(project, local_directory, radius_file, psf, pdb)
    result = bridge.run(f"cd {project.directory} && sasa_analysis {shlex.quote(filename)}", timeout=300)
    log = (result.stdout or "") + (result.stderr or "")
    output_path = Path(local_directory) / SASA_OUTPUT_NAME.format(name=project.name)
    if not result.ok:
        return AnalysisRunResult(success=False, output_path=None, log=log)
    if not output_path.exists():
        return AnalysisRunResult(success=False, output_path=None, log=log + "\n(no sasa output was produced)")
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
