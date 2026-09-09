"""Loads JSON parameter presets from resources/presets/."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

from app.project import ModelType

PRESETS_DIR = Path(__file__).resolve().parent.parent / "resources" / "presets"


@lru_cache(maxsize=1)
def load_model_defaults() -> Dict[str, Any]:
    return json.loads((PRESETS_DIR / "model_defaults.json").read_text())


def defaults_for(model_type: ModelType) -> Dict[str, Any]:
    return dict(load_model_defaults().get(model_type.value, {}))
