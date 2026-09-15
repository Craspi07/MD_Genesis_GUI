"""QSettings-backed configuration for GENESIS Studio.

Centralizes every persisted setting (WSL distro/user, tool paths, MPI
tuning, window layout, recent projects) behind typed properties so the rest
of the app never touches QSettings keys directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from PyQt5.QtCore import QSettings

ORG_NAME = "GenesisStudio"
APP_NAME = "GenesisStudio"

DEFAULT_DISTRO = "Ubuntu-24.04"
DEFAULT_MPI_EXTRA_ARGS = "--mca btl vader,self --bind-to core --map-by socket:PE={omp_threads}"
DEFAULT_PROJECTS_SUBDIR = "genesis_projects"
DEFAULT_TOTAL_CORES = 16


@dataclass
class Settings:
    """Typed view over the persisted QSettings store.

    Call `.load()` to populate from disk and `.save()` to persist. The
    dataclass fields mirror every setting the app needs; nothing else in
    the codebase should call QSettings directly (see CLAUDE.md).
    """

    distro: str = DEFAULT_DISTRO
    linux_user: str = ""
    mpi_extra_args: str = DEFAULT_MPI_EXTRA_ARGS
    total_cores: int = DEFAULT_TOTAL_CORES
    vmd_path: str = r"C:\Program Files\University of Illinois\VMD\vmd.exe"
    sasa_radius_file: str = ""  # sasa_analysis's [SASA_OPTION] radi_file -- no confirmed default path
    # ships with GENESIS, so unlike vmd_path this has no guessed fallback; see DECISIONS.md
    last_project: str = ""
    recent_projects: List[str] = field(default_factory=list)
    window_geometry: Optional[bytes] = None
    window_state: Optional[bytes] = None
    setup_complete: bool = False
    max_recent_projects: int = 10

    # -- persistence -----------------------------------------------------
    def _qsettings(self) -> QSettings:
        return QSettings(ORG_NAME, APP_NAME)

    def load(self) -> "Settings":
        s = self._qsettings()
        self.distro = s.value("wsl/distro", DEFAULT_DISTRO, type=str)
        self.linux_user = s.value("wsl/linux_user", "", type=str)
        self.mpi_extra_args = s.value("wsl/mpi_extra_args", DEFAULT_MPI_EXTRA_ARGS, type=str)
        self.total_cores = int(s.value("wsl/total_cores", DEFAULT_TOTAL_CORES))
        self.vmd_path = s.value("tools/vmd_path", self.vmd_path, type=str)
        self.sasa_radius_file = s.value("tools/sasa_radius_file", "", type=str)
        self.last_project = s.value("projects/last", "", type=str)
        recents = s.value("projects/recent", [])
        self.recent_projects = list(recents) if recents else []
        self.window_geometry = s.value("window/geometry", None)
        self.window_state = s.value("window/state", None)
        self.setup_complete = s.value("setup/complete", False, type=bool)
        return self

    def save(self) -> None:
        s = self._qsettings()
        s.setValue("wsl/distro", self.distro)
        s.setValue("wsl/linux_user", self.linux_user)
        s.setValue("wsl/mpi_extra_args", self.mpi_extra_args)
        s.setValue("wsl/total_cores", self.total_cores)
        s.setValue("tools/vmd_path", self.vmd_path)
        s.setValue("tools/sasa_radius_file", self.sasa_radius_file)
        s.setValue("projects/last", self.last_project)
        s.setValue("projects/recent", self.recent_projects)
        if self.window_geometry is not None:
            s.setValue("window/geometry", self.window_geometry)
        if self.window_state is not None:
            s.setValue("window/state", self.window_state)
        s.setValue("setup/complete", self.setup_complete)
        s.sync()

    # -- helpers -----------------------------------------------------------
    def projects_root_wsl(self) -> str:
        """Linux-side path to the projects root, e.g. ~/genesis_projects."""
        return f"~/{DEFAULT_PROJECTS_SUBDIR}"

    def add_recent_project(self, path: str) -> None:
        if path in self.recent_projects:
            self.recent_projects.remove(path)
        self.recent_projects.insert(0, path)
        self.recent_projects = self.recent_projects[: self.max_recent_projects]
        self.last_project = path

    def mpi_args_for(self, omp_threads: int) -> str:
        return self.mpi_extra_args.format(omp_threads=omp_threads)
