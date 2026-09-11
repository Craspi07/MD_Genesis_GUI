from pathlib import Path

from app.text_io import to_ascii, write_generated_text, write_user_text


def test_to_ascii_replaces_common_punctuation():
    assert to_ascii("a—b") == "a-b"  # em dash
    assert to_ascii("a–b") == "a-b"  # en dash
    assert to_ascii("‘quoted’") == "'quoted'"
    assert to_ascii("“quoted”") == '"quoted"'
    assert to_ascii("etc…") == "etc..."


def test_to_ascii_drops_anything_else_non_ascii():
    assert to_ascii("café") == "caf"


def test_write_generated_text_forces_lf_and_ascii(tmp_path: Path):
    path = tmp_path / "run.inp"
    write_generated_text(path, "line one—with dash\nline two\n")
    raw = path.read_bytes()
    assert b"\r" not in raw
    assert raw.decode("ascii") == "line one-with dash\nline two\n"


def test_write_user_text_forces_lf_but_keeps_content(tmp_path: Path):
    path = tmp_path / "run.inp"
    write_user_text(path, "user's own ± symbol\n")
    raw = path.read_bytes()
    assert b"\r" not in raw
    assert "±" in raw.decode("utf-8")
