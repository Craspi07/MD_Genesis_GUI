"""Generates GENESIS control files from a typed config via Jinja2
templates, and supports round-tripping user edits.

See resources/templates/_common_sections.j2 and the per-model templates
for citations: as of 2026-09-09 every keyword is either confirmed against
a live fetch of mdgenesis.org (docs/usage/, tutorials 11.1-11.3) and the
genesis_cg_tool wiki, or explicitly marked `# VERIFY` where no official
source covers it (mainly the HPS/IDR model, which has no GENESIS
tutorial). See DECISIONS.md for the full writeup.
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


MODEL_TYPES_REQUIRING_BOX = (ModelType.HPS_CONDENSATE, ModelType.AICG2P)
# AICG2P needs box_x/y/z too because mdgenesis.org tutorial 11.1's own
# single-protein (1PGB) example runs under [BOUNDARY] type = PBC with an
# explicit box, not NOBC as previously assumed — see aicg2p.j2 and
# DECISIONS.md.


# mdgenesis.org tutorial 11.1's own example system (1PGB, 56 residues)
# uses a 180.0 x 180.0 x 180.0 box; used as the fallback whenever a
# project has no explicit SimulationParameters.box_size_nm set, for
# whichever model type needs one (see MODEL_TYPES_REQUIRING_BOX).
DEFAULT_BOX_SIZE = 180.0
DEFAULT_CONDENSATE_BOX = (20.0, 20.0, 200.0)


def default_box_size(model_type: ModelType, box_size: Optional[float]) -> tuple:
    """Resolve (box_x, box_y, box_z) for a project, applying the same
    tutorial-derived fallback used by every ControlFileConfig call site so
    a project without an explicit box size still renders instead of
    raising. Returns (None, None, None) for model types that don't need a
    box at all."""
    if model_type == ModelType.HPS_CONDENSATE:
        if box_size is not None:
            return (box_size, box_size, box_size)
        return DEFAULT_CONDENSATE_BOX
    if model_type == ModelType.AICG2P:
        size = box_size if box_size is not None else DEFAULT_BOX_SIZE
        return (size, size, size)
    return (None, None, None)


def render_control_file(config: ControlFileConfig, model_type: ModelType) -> str:
    template_name = _TEMPLATE_BY_MODEL[model_type]
    if model_type in MODEL_TYPES_REQUIRING_BOX and (
        config.box_x is None or config.box_y is None or config.box_z is None
    ):
        raise ValueError(f"{model_type.value} control files require box_x/box_y/box_z")
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
