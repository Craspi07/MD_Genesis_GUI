"""Generates GENESIS control files from a typed config via Jinja2
templates, and supports round-tripping user edits.

See resources/templates/_common_sections.j2 for the full # VERIFY notice:
this session could not reach mdgenesis.org (network egress blocked — see
DECISIONS.md), so every keyword is either cited to the genesis_cg_tool
wiki (the one source that was reachable) or explicitly marked unverified.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.project import ModelType

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "resources" / "templates"

_TEMPLATE_BY_MODEL = {
    ModelType.AICG2P: "aicg2p.j2",
    ModelType.HPS_SINGLE: "hps_single.j2",
    ModelType.HPS_CONDENSATE: "hps_condensate.j2",
    ModelType.PROTEIN_DNA: "protein_dna.j2",
}


@dataclass
class ControlFileConfig:
    top_file: str
    gro_file: str
    output_prefix: str
    temperature_k: float
    n_steps: int
    timestep_fs: float
    output_frequency: int
    langevin_friction: float
    ensemble: str = "NVT"
    restart_file: Optional[str] = None
    box_x: Optional[float] = None
    box_y: Optional[float] = None
    box_z: Optional[float] = None


def _environment() -> Environment:
    # Control files are plain text (INI-style), not HTML/XML, so autoescape
    # is intentionally off.
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(disabled_extensions=(".j2",), default=False),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def render_control_file(config: ControlFileConfig, model_type: ModelType) -> str:
    template_name = _TEMPLATE_BY_MODEL[model_type]
    if model_type == ModelType.HPS_CONDENSATE and (
        config.box_x is None or config.box_y is None or config.box_z is None
    ):
        raise ValueError("HPS condensate control files require box_x/box_y/box_z")
    env = _environment()
    template = env.get_template(template_name)
    return template.render(config=config)


def write_control_file(
    config: ControlFileConfig,
    model_type: ModelType,
    local_directory: str,
    filename: str = "run.inp",
    force: bool = False,
) -> Path:
    """Write the rendered control file into `local_directory/filename`.

    If a file already exists at that path and `force` is False, it is left
    untouched and its path is returned unchanged — this is the "keep my
    edits" side of the Files tab's regenerate-vs-keep-edits choice; callers
    that want to overwrite (the "Regenerate" action) must pass force=True.
    """
    path = Path(local_directory) / filename
    if path.exists() and not force:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_control_file(config, model_type))
    return path
