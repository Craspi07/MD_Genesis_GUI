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
    build_structure_builder_command,
    build_duplication_command,
    build_fasta_text,
    CgCommand,
)
from app.control_file import ControlFileConfig, default_box_size, write_control_file
from app.project import Project, ModelType, InputMode
from app.settings import Settings
from app.text_io import write_generated_text
from app.wsl import CommandResult, WslBridge


def local_directory_for(settings: Settings, project_name: str) -> str:
    r"""The local filesystem path the GUI process should read/write for a
    project's files. On the real Windows app this is the \\wsl$ UNC mount
    of ~/genesis_projects/<name>; see app/project.py's module docstring.
    """
    return rf"\\wsl$\{settings.distro}\home\{settings.linux_user}\genesis_projects\{project_name}"


def local_projects_root_for(settings: Settings) -> str:
    r"""The local filesystem path of the projects root itself (parent of
    every local_directory_for(...) path) -- used as the starting
    directory for File > Open Project's folder picker."""
    return rf"\\wsl$\{settings.distro}\home\{settings.linux_user}\genesis_projects"


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
    elif project.input_mode == InputMode.ALL_ATOM_PREBUILT:
        created.extend(copy_all_atom_files(project, local_directory))
    else:
        fasta_text = build_fasta_text(project.sequence, header=project.name)
        dest = directory / f"{project.name}.fasta"
        write_generated_text(dest, fasta_text)
        created.append(dest.name)

    return created


def copy_all_atom_files(project: Project, local_directory: str) -> List[str]:
    """Copies the pre-built CHARMM system's own files (topology/parameter/
    stream/PSF/PDB) into the project directory, exactly the same
    copy-in-then-reference-by-basename pattern already used for PDB-mode
    CG input (see create_project_files). generate_project_control_file's
    aa_* ControlFileConfig fields then reference just the basenames.

    Missing/renamed source files raise FileNotFoundError -- unlike
    genesis_cg_tool's outputs (which this app generates and thus knows
    the shape of), these are files a user pointed at externally, so a
    stale path must fail loudly rather than silently produce an
    incomplete project.
    """
    directory = Path(local_directory)
    copied: List[str] = []
    all_sources = (
        project.aa_top_source_paths
        + project.aa_par_source_paths
        + project.aa_str_source_paths
        + [project.aa_psf_source_path, project.aa_pdb_source_path]
    )
    for source in all_sources:
        if not source:
            continue
        dest = directory / Path(source).name
        shutil.copy(source, dest)
        copied.append(dest.name)
    return copied


def build_cg_commands(project: Project, input_filename: str) -> List[CgCommand]:
    """Pick the right genesis_cg_tool command sequence for this project.
    See app/cgtool.py and DECISIONS.md for what's verified vs. # VERIFY.

    Condensate replication (duplication_generator.jl) isn't included here
    -- it needs to run after this step's output exists on disk and a
    local rename in between (see run_cg_tool_pipeline), not as a
    standalone command string.
    """
    if project.input_mode == InputMode.SEQUENCE:
        return [build_structure_builder_command(input_filename)]
    return [build_aicg2p_command(input_filename, output_name=project.name)]


def _param_copy_command(project: Project) -> str:
    """Shell command copying genesis_cg_tool's param/ directory into the
    project directory. The generated .top file #includes ./param/*.itp
    relative to the run directory (jobs are launched with `cd
    {project.directory} && ...`), so param/ must exist alongside it --
    see DECISIONS.md."""
    return f"mkdir -p {project.directory}/param && cp -r ~/genesis_cg_tool/param/. {project.directory}/param/"


def copy_cg_tool_param(bridge: WslBridge, project: Project) -> CommandResult:
    return bridge.run(_param_copy_command(project))


def run_cg_tool_pipeline(
    bridge: WslBridge,
    project: Project,
    local_directory: str,
) -> CreationResult:
    """Run the CG-tool command(s) inside WSL (working directory = the
    project's WSL-side directory), replicate into a condensate slab when
    needed, and write a cgtool.log into the project directory (via
    ordinary local file I/O — local_directory is the same \\wsl$ mount, so
    no extra WSL round-trip is needed for a small text file).
    """
    directory = Path(local_directory)
    input_filename = next(
        (p.name for p in directory.iterdir() if p.suffix.lower() in (".pdb", ".cif", ".fasta")),
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

    if project.model_type == ModelType.HPS_CONDENSATE and project.parameters.n_copies > 1:
        gro_files = list(directory.glob(f"{project.name}*.gro"))
        top_files = list(directory.glob(f"{project.name}*.top"))
        if gro_files and top_files:
            top_path = top_files[0]
            gro_path = gro_files[0]
            single_gro_name = f"{project.name}_single.gro"
            gro_path.rename(directory / single_gro_name)
            log_parts.append(f"$ (local) renamed {gro_path.name} -> {single_gro_name}")

            dup_command = build_duplication_command(
                top_filename=top_path.name,
                gro_filename=single_gro_name,
                output_name=top_path.stem,
                n_copies=project.parameters.n_copies,
            )
            log_parts.append(f"$ {dup_command.command}")
            dup_result = bridge.run(cd + dup_command.command, timeout=600)
            log_parts.append(dup_result.stdout)
            if dup_result.stderr:
                log_parts.append(dup_result.stderr)
            if not dup_result.ok:
                log_text = "\n".join(log_parts)
                (directory / "cgtool.log").write_text(log_text)
                return CreationResult(
                    False,
                    f"CG-tool step failed: {dup_command.description} (exit code {dup_result.returncode})",
                    log_text,
                )
            # duplication_generator.jl writes the replicated .gro under
            # `output_name` (same stem as top_path, e.g. "myproj_cg.gro"),
            # leaving both it and the renamed single-chain .gro matching
            # "{project.name}*.gro" -- remove the now-unneeded single-chain
            # one so later glob-based lookups (generate_project_control_file)
            # can't pick up the wrong file.
            (directory / single_gro_name).unlink(missing_ok=True)
            log_parts.append(f"$ (local) removed {single_gro_name}")

    # genesis_cg_tool's .top #includes ./param/*.itp relative to the run
    # directory -- copy the param/ directory alongside it or GENESIS can't
    # resolve those includes. See DECISIONS.md.
    param_result = copy_cg_tool_param(bridge, project)
    log_parts.append(f"$ {_param_copy_command(project)}")
    if param_result.stdout:
        log_parts.append(param_result.stdout)
    if not param_result.ok:
        log_text = "\n".join(log_parts)
        (directory / "cgtool.log").write_text(log_text)
        return CreationResult(
            False,
            "Could not copy genesis_cg_tool/param into the project directory "
            "(needed for the generated .top file's ./param/*.itp includes).",
            log_text,
        )

    log_text = "\n".join(log_parts)
    (directory / "cgtool.log").write_text(log_text)
    return CreationResult(True, "CG-tool pipeline completed.", log_text)


def build_control_file_config(
    project: Project,
    local_directory: str,
    output_prefix: Optional[str] = None,
    n_steps: Optional[int] = None,
    output_frequency: Optional[int] = None,
    restart_file: Optional[str] = None,
) -> ControlFileConfig:
    """Builds the ControlFileConfig for `project`, branching once here on
    ALL_ATOM_CHARMM vs. every CG model type -- the one place that
    branch is decided, reused by generate_project_control_file (a real
    run) and app/benchmark.py (a short timed run under a different
    output_prefix/n_steps). Before this was factored out, benchmark.py
    duplicated only the CG-shaped half of this logic inline, which
    silently couldn't benchmark an all-atom project at all (it gated on
    finding a .top/.gro file, which an all-atom project never has) --
    see DECISIONS.md.

    `output_prefix`/`n_steps`/`output_frequency` default to the
    project's own name/parameters; benchmark.py overrides all three for
    a short per-preset run. `restart_file` set means "continue from a
    restart file" (Run tab's Continue button).
    """
    directory = Path(local_directory)
    output_prefix = output_prefix or project.name
    n_steps = project.parameters.n_steps if n_steps is None else n_steps
    output_frequency = project.parameters.output_frequency if output_frequency is None else output_frequency

    if project.model_type == ModelType.ALL_ATOM_CHARMM:
        # Files were copied in by copy_all_atom_files() under their own
        # basenames; box size comes from the user (no tutorial-derived
        # default makes sense for an already-built system -- see
        # ui/page_all_atom_input.py and DECISIONS.md).
        return ControlFileConfig(
            top_file="",
            gro_file="",
            output_prefix=output_prefix,
            temperature_k=project.parameters.temperature_k,
            n_steps=n_steps,
            timestep_fs=project.parameters.timestep_fs,
            output_frequency=output_frequency,
            langevin_friction=project.parameters.langevin_friction,
            ensemble=project.parameters.ensemble,
            pressure_atm=project.parameters.pressure_atm,
            use_position_restraints=project.parameters.use_position_restraints,
            position_restraint_force_constant=project.parameters.position_restraint_force_constant,
            remd_enabled=project.parameters.remd_enabled,
            remd_exchange_period=project.parameters.remd_exchange_period,
            remd_temperatures=project.parameters.remd_temperatures,
            gamd_enabled=project.parameters.gamd_enabled,
            gamd_update_period=project.parameters.gamd_update_period,
            gamd_sigma0_pot=project.parameters.gamd_sigma0_pot,
            box_x=project.aa_box_x,
            box_y=project.aa_box_y,
            box_z=project.aa_box_z,
            engine=project.resources.engine.value,
            aa_top_files=[Path(p).name for p in project.aa_top_source_paths],
            aa_par_files=[Path(p).name for p in project.aa_par_source_paths],
            aa_str_files=[Path(p).name for p in project.aa_str_source_paths],
            aa_psf_file=Path(project.aa_psf_source_path).name if project.aa_psf_source_path else None,
            aa_pdb_file=Path(project.aa_pdb_source_path).name if project.aa_pdb_source_path else None,
            restart_file=restart_file,
        )

    top_files = list(directory.glob(f"{project.name}*.top"))
    gro_files = list(directory.glob(f"{project.name}*.gro"))
    top_name = top_files[0].name if top_files else f"{project.name}.top"
    gro_name = gro_files[0].name if gro_files else f"{project.name}.gro"

    box_x, box_y, box_z = default_box_size(project.model_type, project.parameters.box_size_nm)
    return ControlFileConfig(
        top_file=top_name,
        gro_file=gro_name,
        output_prefix=output_prefix,
        temperature_k=project.parameters.temperature_k,
        n_steps=n_steps,
        timestep_fs=project.parameters.timestep_fs,
        output_frequency=output_frequency,
        langevin_friction=project.parameters.langevin_friction,
        ensemble=project.parameters.ensemble,
        pressure_atm=project.parameters.pressure_atm,
        use_position_restraints=project.parameters.use_position_restraints,
        position_restraint_force_constant=project.parameters.position_restraint_force_constant,
        remd_enabled=project.parameters.remd_enabled,
        remd_exchange_period=project.parameters.remd_exchange_period,
        remd_temperatures=project.parameters.remd_temperatures,
        gamd_enabled=project.parameters.gamd_enabled,
        gamd_update_period=project.parameters.gamd_update_period,
        gamd_sigma0_pot=project.parameters.gamd_sigma0_pot,
        box_x=box_x,
        box_y=box_y,
        box_z=box_z,
        engine=project.resources.engine.value,
        restart_file=restart_file,
    )


def generate_project_control_file(
    project: Project, local_directory: str, force: bool = False, restart_file: Optional[str] = None
) -> Path:
    config = build_control_file_config(project, local_directory, restart_file=restart_file)
    return write_control_file(config, project.model_type, local_directory, filename="run.inp", force=force)
