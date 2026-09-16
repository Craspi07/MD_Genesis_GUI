"""Delete and rename an existing project (Dashboard actions). Kept
separate from app/project_creation.py, which is scoped to *creating* a
project.

Both operations run entirely inside WSL via WslBridge rather than
`shutil` over the `\\wsl$` UNC mount -- a real directory rename/delete
is more reliable done natively than over that mount (see CLAUDE.md and
DECISIONS.md), the same reasoning already applied elsewhere in this
app for anything beyond small file reads/writes.
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.project import Project
from app.project_creation import generate_project_control_file, local_directory_for
from app.settings import Settings
from app.wsl import WslBridge


@dataclass
class ProjectActionResult:
    success: bool
    message: str
    new_local_directory: Optional[str] = None  # set on a successful rename


def delete_project(bridge: WslBridge, project: Project) -> ProjectActionResult:
    """Permanently deletes a project's WSL directory (all its files).
    Refuses while a run is in progress -- deleting the directory out
    from under a live job would orphan its process group (the pgid
    tracking this app relies on to stop/reattach lives in project.json,
    which is about to be deleted too)."""
    if project.last_run_status == "running":
        return ProjectActionResult(False, "Stop the running simulation before deleting this project.")
    result = bridge.run(f"rm -rf {shlex.quote(project.directory)}")
    if not result.ok:
        return ProjectActionResult(False, f"Could not delete the project directory: {result.stderr.strip()}")
    return ProjectActionResult(True, f"Deleted '{project.name}'.")


def rename_project(bridge: WslBridge, settings: Settings, project: Project, new_name: str) -> ProjectActionResult:
    """Renames a project: the WSL directory itself, every generated file
    inside it prefixed with the old project name (.top/.gro/.pdb/.dcd/
    .rst/etc.), project.json, and finally regenerates run.inp (whose
    contents reference those now-renamed files by name). Anything not
    prefixed with the old name (param/, CHARMM toppar files, cgtool.log,
    minimize.inp) is deliberately left alone.

    Refuses while a run is in progress, for the same reason delete_project
    does -- the renamed directory would pull the rug out from under a
    live job's own file references mid-run.
    """
    new_name = new_name.strip()
    if not new_name:
        return ProjectActionResult(False, "Enter a new name.")
    if new_name == project.name:
        return ProjectActionResult(False, "That's already this project's name.")
    if project.last_run_status == "running":
        return ProjectActionResult(False, "Stop the running simulation before renaming this project.")

    old_name = project.name
    new_wsl_directory = f"{settings.projects_root_wsl()}/{new_name}"
    new_local_directory = local_directory_for(settings, new_name)
    if Path(new_local_directory).exists():
        return ProjectActionResult(False, f"A project named '{new_name}' already exists.")

    mv_result = bridge.run(f"mv {shlex.quote(project.directory)} {shlex.quote(new_wsl_directory)}")
    if not mv_result.ok:
        return ProjectActionResult(False, f"Could not rename the project directory: {mv_result.stderr.strip()}")

    # List files first, filter/build the rename plan in Python (not raw
    # shell string interpolation of old_name/new_name -- avoids splicing
    # user-controlled text into bash parameter-expansion syntax).
    list_result = bridge.run(f"cd {shlex.quote(new_wsl_directory)} && find . -maxdepth 1 -type f -printf '%f\\n'")
    if not list_result.ok:
        return ProjectActionResult(
            False,
            f"Renamed the project directory but could not list its files: {list_result.stderr.strip()}",
            new_local_directory=new_local_directory,
        )
    filenames = [line.strip() for line in list_result.stdout.splitlines() if line.strip()]
    rename_commands = []
    for filename in filenames:
        if not filename.startswith(old_name):
            continue
        new_filename = new_name + filename[len(old_name):]
        if new_filename == filename:
            continue
        rename_commands.append(f"mv -- {shlex.quote(filename)} {shlex.quote(new_filename)}")
    if rename_commands:
        rename_result = bridge.run(f"cd {shlex.quote(new_wsl_directory)} && " + " && ".join(rename_commands))
        if not rename_result.ok:
            return ProjectActionResult(
                False,
                f"Renamed the project directory but could not rename its generated files: {rename_result.stderr.strip()}",
                new_local_directory=new_local_directory,
            )

    project.name = new_name
    project.directory = new_wsl_directory
    project.save(new_local_directory)

    try:
        # run.inp's own contents reference the old filenames (top/gro,
        # output_prefix) -- regenerate now that those files are renamed
        # too. force=True: any manual edits to run.inp are necessarily
        # stale after a rename (they'd reference files that no longer
        # exist under those names), so they're discarded here, the same
        # as the Files tab's own "Regenerate" action already does.
        generate_project_control_file(project, new_local_directory, force=True)
    except Exception as exc:  # noqa: BLE001 - the rename itself already succeeded; surface, don't fail it
        return ProjectActionResult(
            True,
            f"Renamed to '{new_name}', but run.inp could not be regenerated automatically ({exc}) "
            "-- use the Files tab's Regenerate button.",
            new_local_directory=new_local_directory,
        )

    return ProjectActionResult(True, f"Renamed to '{new_name}'.", new_local_directory=new_local_directory)
