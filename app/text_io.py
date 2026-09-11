"""Writes plain-text files consumed by GENESIS/genesis_cg_tool.

Confirmed 2026-09-11 against a real installed GENESIS 2.1.6: a control
file written by this app's own default `Path.write_text()` calls failed
to parse ("Unknown parameter: [output] ...") because it contained CRLF
line endings. This GUI runs as a native Windows process (see CLAUDE.md /
README): `Path.write_text()`'s default newline handling translates `\n`
to `os.linesep` on write, which is `\r\n` on Windows, regardless of the
fact that the target file lives on the Linux side via `\\wsl$`. Every
write here forces `newline="\n"` to avoid that regardless of platform.
See DECISIONS.md for the full writeup.
"""
from __future__ import annotations

from pathlib import Path

_ASCII_REPLACEMENTS = {
    "—": "-",  # em dash
    "–": "-",  # en dash
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "…": "...",
}


def to_ascii(text: str) -> str:
    """Replace common non-ASCII punctuation with ASCII equivalents, then
    drop anything still non-ASCII."""
    for src, dst in _ASCII_REPLACEMENTS.items():
        text = text.replace(src, dst)
    return text.encode("ascii", errors="ignore").decode("ascii")


def write_generated_text(path: Path, text: str) -> None:
    """Write a fully app-generated GENESIS/genesis_cg_tool file
    (.inp/.top/.itp/.gro/.pdb): LF-only line endings, ASCII-only content.
    Safe to ASCII-strip here because this app authored every character."""
    path.write_text(to_ascii(text), encoding="ascii", newline="\n")


def write_user_text(path: Path, text: str) -> None:
    """Write back a control file a user hand-edited in the GUI (Files
    tab): LF-only line endings, but no ASCII stripping -- the user typed
    this content and it shouldn't be silently altered beyond fixing the
    line-ending bug. encoding is pinned to utf-8 rather than left to
    Python's platform-default text encoding (locale-dependent on Windows,
    e.g. cp1252), so a save behaves the same regardless of machine."""
    path.write_text(text, encoding="utf-8", newline="\n")
