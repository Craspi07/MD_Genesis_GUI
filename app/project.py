"""Project model: dataclass + JSON persistence (project.json in the
project directory).

A project's simulation data lives inside the Linux filesystem
(`~/genesis_projects/<name>/`) for I/O speed. From the GUI (running on
Windows against a real WSL install) that directory is also reachable as
`\\\\wsl$\\<distro>\\home\\<user>\\genesis_projects\\<name>\\`, and small
files (project.json, control files, .top/.itp/.gro, log files) are read
and written directly at that UNC path — only large trajectory files must
never cross the boundary that way (see CLAUDE.md). `Project.save`/`load`
take a plain local directory path so the same code works whether that
path is a `\\wsl$` UNC mount (on Windows) or a local test directory (in
this dev environment, which has no real WSL to mount).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class ModelType(str, Enum):
    AICG2P = "aicg2p"  # Folded protein — AICG2+
    HPS_SINGLE = "hps_single"  # Disordered protein / IDR — HPS
    HPS_CONDENSATE = "hps_condensate"  # Multi-chain condensate — HPS slab
    PROTEIN_DNA = "protein_dna"  # AICG2+ + 3SPN.2C (advanced)


class InputMode(str, Enum):
    PDB = "pdb"
    SEQUENCE = "sequence"


class Engine(str, Enum):
    ATDYN = "atdyn"
    CGDYN = "cgdyn"


@dataclass
class SimulationParameters:
    temperature_k: float = 300.0
    n_steps: int = 1_000_000
    timestep_fs: float = 10.0  # AICG2+/HPS CG timestep is in the ~10 fs range; see # VERIFY note in control_file.py
    output_frequency: int = 1000
    langevin_friction: float = 0.01
    box_size_nm: Optional[float] = None
    n_copies: int = 1
    use_position_restraints: bool = False
    random_seed: int = 12345


@dataclass
class ResourceConfig:
    engine: Engine = Engine.ATDYN
    mpi_ranks: int = 4
    omp_threads: int = 4
    engine_overridden: bool = False


@dataclass
class Project:
    name: str
    directory: str  # e.g. "~/genesis_projects/my_protein" (Linux-side path)
    model_type: ModelType = ModelType.AICG2P
    input_mode: InputMode = InputMode.PDB
    input_path: str = ""  # Windows-side source PDB/CIF path, if input_mode == PDB
    sequence: str = ""  # if input_mode == SEQUENCE
    parameters: SimulationParameters = field(default_factory=SimulationParameters)
    resources: ResourceConfig = field(default_factory=ResourceConfig)
    created_at: str = ""
    last_run_pid: Optional[int] = None
    last_run_pgid: Optional[int] = None
    last_run_status: str = "not_started"  # not_started | running | finished | stopped | failed
    generated_files: List[str] = field(default_factory=list)
    files_with_manual_edits: List[str] = field(default_factory=list)

    # -- persistence ---------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["model_type"] = self.model_type.value
        data["input_mode"] = self.input_mode.value
        data["resources"]["engine"] = self.resources.engine.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        data = dict(data)
        data["model_type"] = ModelType(data.get("model_type", ModelType.AICG2P.value))
        data["input_mode"] = InputMode(data.get("input_mode", InputMode.PDB.value))
        params = data.get("parameters") or {}
        data["parameters"] = SimulationParameters(**params)
        resources = dict(data.get("resources") or {})
        resources["engine"] = Engine(resources.get("engine", Engine.ATDYN.value))
        data["resources"] = ResourceConfig(**resources)
        known_fields = {f for f in cls.__dataclass_fields__}
        data = {k: v for k, v in data.items() if k in known_fields}
        return cls(**data)

    def save(self, local_directory: str) -> None:
        """Write project.json into `local_directory` (a plain local path —
        on the real app this is the \\wsl$ UNC mount of `self.directory`)."""
        path = Path(local_directory)
        path.mkdir(parents=True, exist_ok=True)
        (path / "project.json").write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, local_directory: str) -> "Project":
        path = Path(local_directory) / "project.json"
        data = json.loads(path.read_text())
        return cls.from_dict(data)
