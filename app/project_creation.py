"""Orchestrates turning a filled-out wizard Project into an on-disk
project: writing project.json, running the CG-tool pipeline via
WslBridge, and generating the GENESIS control file.

Kept separate from ui/wizard_new_project.py so this logic (which touches
the filesystem and WslBridge) can be unit-tested without a real Qt event
loop or a real WSL install.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from app.cgtool import (
    build_aicg2p_command,
    build_hps_sequence_commands,
    generate_extended_chain_pdb,
    inject_idr_hps_region,
    build_slab_system,
    CgCommand,
)
from app.control_file import ControlFileConfig, write_control_file
from app.project import Project, ModelType, InputMode
from app.settings import Settings
from app.wsl import WslBridge


def local_directory_for(settings: Settings, project_name: str) -> str:
    r"""The local filesystem path the GUI process should read/write for a
    project's files. On the real Windows app this is the \\wsl$ UNC mount
    of ~/genesis_projects/<name>; see app/project.py's module docstring.
    """
    return rf"\\wsl$\{settings.distro}\home\{settings.linux_user}\genesis_projects\{project_name}"


@dataclass
class CreationResult:
    success: bool
    message: str
    log: str


def create_project_files(
    project: Project,
    local_directory: str,
    source_pdb_path: Optional[str] = None,
) -> List[str]:
    """Local (no-WSL-needed) part of project creation: write project.json,
    copy/generate the input structure, and return the list of files
    created so far. Safe to call before any WSL command runs.
    """
    directory = Path(local_directory)
    directory.mkdir(parents=True, exist_ok=True)
    created: List[str] = []

    project.save(local_directory)
    created.append("project.json")

    if project.input_mode == InputMode.PDB:
        if not source_pdb_path:
            raise ValueError("PDB input mode requires source_pdb_path")
        dest = directory / Path(source_pdb_path).name
        shutil.copy(source_pdb_path, dest)
        created.append(dest.name)
    else:
        pdb_text = generate_extended_chain_pdb(project.sequence)
        dest = directory / f"{project.name}_extended.pdb"
        dest.write_text(pdb_text)
        created.append(dest.name)

    return created


def build_cg_commands(project: Project, input_filename: str) -> List[CgCommand]:
    """Pick the right genesis_cg_tool command sequence for this project.
    See app/cgtool.py and DECISIONS.md for what's verified vs. # VERIFY.
    """
    if project.input_mode == InputMode.SEQUENCE:
        return build_hps_sequence_commands(
            project.sequence, output_name=project.name, extended_pdb_filename=input_filename
        )
    return [build_aicg2p_command(input_filename, output_name=project.name)]


def run_cg_tool_pipeline(
    bridge: WslBridge,
    project: Project,
    local_directory: str,
) -> CreationResult:
    """Run the CG-tool command(s) inside WSL (working directory = the
    project's WSL-side directory), post-process the .itp for HPS/IDR
    projects, and write a cgtool.log into the project directory (via
    ordinary local file I/O — local_directory is the same \\wsl$ mount, so
    no extra WSL round-trip is needed for a small text file).
    """
    directory = Path(local_directory)
    input_filename = next(
        (p.name for p in directory.iterdir() if p.suffix.lower() in (".pdb", ".cif")),
        None,
    )
    if input_filename is None:
        return CreationResult(False, "No input structure file found in project directory.", "")

    commands = build_cg_commands(project, input_filename)
    log_parts: List[str] = []
    cd = f"cd {project.directory} && "

    for step in commands:
        if step.local_step:
            log_parts.append(f"$ (local) {step.description}")
            continue
        log_parts.append(f"$ {step.command}")
        result = bridge.run(cd + step.command, timeout=600)
        log_parts.append(result.stdout)
        if result.stderr:
            log_parts.append(result.stderr)
        if not result.ok:
            log_text = "\n".join(log_parts)
            (directory / "cgtool.log").write_text(log_text)
            return CreationResult(
                False,
                f"CG-tool step failed: {step.description} (exit code {result.returncode})",
                log_text,
            )

    if project.input_mode == InputMode.SEQUENCE:
        itp_files = list(directory.glob(f"{project.name}*.itp"))
        for itp_path in itp_files:
            text = itp_path.read_text()
            itp_path.write_text(inject_idr_hps_region(text, 1, len(project.sequence)))
        log_parts.append(f"$ (local) marked {len(itp_files)} .itp file(s) as HPS IDR region")

    if project.model_type == ModelType.HPS_CONDENSATE and project.parameters.n_copies > 1:
        gro_files = list(directory.glob(f"{project.name}*.gro"))
        top_files = list(directory.glob(f"{project.name}*.top"))
        if gro_files and top_files:
            gro_text = gro_files[0].read_text()
            top_text = top_files[0].read_text()
            new_gro, new_top = build_slab_system(gro_text, top_text, project.parameters.n_copies)
            gro_files[0].write_text(new_gro)
            top_files[0].write_text(new_top)
            log_parts.append(f"$ (local) replicated system into {project.parameters.n_copies} copies (slab box)")

    log_text = "\n".join(log_parts)
    (directory / "cgtool.log").write_text(log_text)
    return CreationResult(True, "CG-tool pipeline completed.", log_text)


def generate_project_control_file(project: Project, local_directory: str, force: bool = False) -> Path:
    directory = Path(local_directory)
    top_files = list(directory.glob(f"{project.name}*.top"))
    gro_files = list(directory.glob(f"{project.name}*.gro"))
    top_name = top_files[0].name if top_files else f"{project.name}.top"
    gro_name = gro_files[0].name if gro_files else f"{project.name}.gro"

    config = ControlFileConfig(
        top_file=top_name,
        gro_file=gro_name,
        output_prefix=project.name,
        temperature_k=project.parameters.temperature_k,
        n_steps=project.parameters.n_steps,
        timestep_fs=project.parameters.timestep_fs,
        output_frequency=project.parameters.output_frequency,
        langevin_friction=project.parameters.langevin_friction,
        box_x=project.parameters.box_size_nm,
        box_y=project.parameters.box_size_nm,
        box_z=project.parameters.box_size_nm,
    )
    if project.model_type == ModelType.HPS_CONDENSATE and config.box_x is None:
        config.box_x = config.box_y = 20.0
        config.box_z = 200.0
    return write_control_file(config, project.model_type, local_directory, filename="run.inp", force=force)
