import tarfile
from pathlib import Path

from app.charmm_gui_import import import_charmm_gui_archive

FIXTURE_INP = Path(__file__).parent / "fixtures" / "charmm_gui_step6.0_minimization.inp"


def _build_archive(tmp_path: Path, top_dir_name: str = "charmm-gui-1234567890") -> Path:
    # Layout matches the relative paths actually written inside the
    # fixture .inp (../toppar/..., ../1_charmm-gui/...) with the .inp
    # itself placed under genesis/, as in a real CHARMM-GUI archive
    # (confirmed via mdgenesis.org tutorials 6.1/6.2 -- see
    # app/charmm_gui_import.py's module docstring).
    src_root = tmp_path / "src" / top_dir_name
    genesis_dir = src_root / "genesis"
    genesis_dir.mkdir(parents=True)
    (genesis_dir / "step6.0_minimization.inp").write_text(FIXTURE_INP.read_text())

    toppar_dir = src_root / "toppar"
    toppar_dir.mkdir()
    (toppar_dir / "top_all36_lipid.rtf").write_text("* topology\n")
    (toppar_dir / "par_all36_lipid.prm").write_text("* parameters\n")
    (toppar_dir / "toppar_water_ions.str").write_text("* stream\n")

    charmm_gui_dir = src_root / "1_charmm-gui"
    charmm_gui_dir.mkdir()
    (charmm_gui_dir / "step5_assembly.psf").write_text("PSF\n")
    (charmm_gui_dir / "step5_assembly.pdb").write_text("ATOM\n")

    archive_path = tmp_path / f"{top_dir_name}.tgz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(src_root, arcname=top_dir_name)
    return archive_path


def test_import_finds_files_and_box_size(tmp_path: Path):
    archive_path = _build_archive(tmp_path)

    result = import_charmm_gui_archive(str(archive_path))

    assert result.success, result.message
    assert Path(result.psf_path).name == "step5_assembly.psf"
    assert Path(result.pdb_path).name == "step5_assembly.pdb"
    assert [Path(p).name for p in result.top_paths] == ["top_all36_lipid.rtf"]
    assert [Path(p).name for p in result.par_paths] == ["par_all36_lipid.prm"]
    assert [Path(p).name for p in result.str_paths] == ["toppar_water_ions.str"]
    assert result.box_x == 52.2685374
    assert result.box_y == 52.2685374
    assert result.box_z == 85.0
    for path in [result.psf_path, result.pdb_path, *result.top_paths, *result.par_paths, *result.str_paths]:
        assert Path(path).exists()


def test_import_fails_clearly_when_no_genesis_folder(tmp_path: Path):
    src_root = tmp_path / "src" / "charmm-gui-solution-builder"
    src_root.mkdir(parents=True)
    (src_root / "step5_assembly.pdb").write_text("ATOM\n")
    archive_path = tmp_path / "no_genesis.tgz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(src_root, arcname="charmm-gui-solution-builder")

    result = import_charmm_gui_archive(str(archive_path))

    assert not result.success
    assert "genesis" in result.message.lower()


def test_import_fails_clearly_on_a_non_tar_file(tmp_path: Path):
    bogus = tmp_path / "not_actually_a_tarball.tgz"
    bogus.write_text("just some text, not a real archive")

    result = import_charmm_gui_archive(str(bogus))

    assert not result.success
    assert "could not extract" in result.message.lower()


def test_import_fails_clearly_when_referenced_file_missing(tmp_path: Path):
    src_root = tmp_path / "src" / "charmm-gui-broken"
    genesis_dir = src_root / "genesis"
    genesis_dir.mkdir(parents=True)
    (genesis_dir / "step6.0_minimization.inp").write_text(FIXTURE_INP.read_text())
    # deliberately omit toppar/ and 1_charmm-gui/ -- referenced files won't exist
    archive_path = tmp_path / "broken.tgz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(src_root, arcname="charmm-gui-broken")

    result = import_charmm_gui_archive(str(archive_path))

    assert not result.success
    assert "doesn't exist" in result.message


def test_import_fails_clearly_when_required_input_key_missing(tmp_path: Path):
    src_root = tmp_path / "src" / "charmm-gui-missing-key"
    genesis_dir = src_root / "genesis"
    genesis_dir.mkdir(parents=True)
    (genesis_dir / "step6.0_minimization.inp").write_text("[INPUT]\ntopfile = a.rtf\n")
    archive_path = tmp_path / "missing_key.tgz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(src_root, arcname="charmm-gui-missing-key")

    result = import_charmm_gui_archive(str(archive_path))

    assert not result.success
    assert "missing expected [INPUT] keys" in result.message
    assert "parfile" in result.message
