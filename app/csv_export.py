"""CSV export for analysis results (Roadmap Phase 6) -- a lighter-weight
alternative to app/excel_export.py's multi-sheet workbook, for a user who
just wants plain-text data to load elsewhere. Uses Python's stdlib csv
module, no third-party dependency.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, List, Optional

from app.excel_export import AnalysisMatrix, AnalysisSeries


def _safe_filename(label: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", label).strip()
    return cleaned or "result"


def export_to_csv(
    series: Dict[str, AnalysisSeries],
    matrices: Optional[Dict[str, AnalysisMatrix]] = None,
    output_dir: str = ".",
) -> List[str]:
    """Writes one CSV file per series/matrix into `output_dir` (CSV has no
    concept of multiple sheets, unlike the Excel export). Returns the list
    of written file paths."""
    matrices = matrices or {}
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    written = []

    for s in series.values():
        path = directory / f"{_safe_filename(s.label)}.csv"
        with open(path, "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow([s.x_label, s.y_label])
            for x_val, y_val in zip(s.x.tolist(), s.y.tolist()):
                writer.writerow([x_val, y_val])
        written.append(str(path))

    for m in matrices.values():
        path = directory / f"{_safe_filename(m.label)}.csv"
        with open(path, "w", newline="") as fh:
            writer = csv.writer(fh)
            for row in m.matrix.tolist():
                writer.writerow(row)
        written.append(str(path))

    return written
