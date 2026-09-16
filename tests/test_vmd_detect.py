from pathlib import Path

from app.vmd_detect import detect_vmd_path


def _make_vmd(dir_path: Path) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / "vmd.exe").write_text("")


def test_detects_vmd_at_exact_root(tmp_path: Path):
    root = tmp_path / "University of Illinois" / "VMD"
    _make_vmd(root)
    found = detect_vmd_path(roots=[str(root)])
    assert found == str(root / "vmd.exe")


def test_detects_vmd_under_versioned_sibling_folder(tmp_path: Path):
    # Real gap: VMD 2.0 alpha installs under "VMD 2.0 alpha", not "VMD"
    root = tmp_path / "VMD"
    versioned = tmp_path / "VMD 2.0 alpha"
    _make_vmd(versioned)
    found = detect_vmd_path(roots=[str(root)])
    assert found == str(versioned / "vmd.exe")


def test_returns_none_when_nothing_found(tmp_path: Path):
    root = tmp_path / "nonexistent" / "VMD"
    assert detect_vmd_path(roots=[str(root)]) is None


def test_checks_multiple_roots_in_order(tmp_path: Path):
    root_a = tmp_path / "a" / "VMD"
    root_b = tmp_path / "b" / "VMD"
    _make_vmd(root_b)
    found = detect_vmd_path(roots=[str(root_a), str(root_b)])
    assert found == str(root_b / "vmd.exe")


def test_default_roots_used_when_none_given(monkeypatch):
    # Just confirm it runs against the real default list without error --
    # on this (non-Windows) dev machine none of those C:\ paths exist.
    assert detect_vmd_path() is None
