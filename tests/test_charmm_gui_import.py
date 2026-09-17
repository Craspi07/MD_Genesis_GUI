import tarfile
from pathlib import Path

from app.charmm_gui_import import extract_charmm_gui_archive


def _cryst1_line(a: float, b: float, c: float) -> str:
    # PDB format spec v3.3 CRYST1 record: Real(9.3) fields for a/b/c
    # (columns 7-15/16-24/25-33), Real(7.2) for the angles -- the same
    # fixed-column convention app/validators.py already relies on for
    # ATOM records.
    return f"CRYST1{a:9.3f}{b:9.3f}{c:9.3f}{90.0:7.2f}{90.0:7.2f}{90.0:7.2f} P 1           1\n"


def _build_solution_builder_archive(tmp_path: Path, top_dir_name: str = "charmm-gui-1234567890") -> Path:
    src_root = tmp_path / "src" / top_dir_name
    src_root.mkdir(parents=True)

    toppar_dir = src_root / "toppar"
    toppar_dir.mkdir()
    (toppar_dir / "top_all36_prot.rtf").write_text("* topology\n")
    (toppar_dir / "par_all36m_prot.prm").write_text("* parameters\n")
    (toppar_dir / "toppar_water_ions.str").write_text("* stream\n")
    # CHARMM-GUI bundles its whole library -- extras shouldn't be picked
    (toppar_dir / "toppar_all36_carb_glycopeptide.str").write_text("* unrelated\n")

    # intermediate stage, should be ignored in favor of the final step
    (src_root / "step1_pdbreader.psf").write_text("PSF\n")
    (src_root / "step1_pdbreader.pdb").write_text("ATOM\n")

    (src_root / "step5_input.psf").write_text("PSF\n")
    (src_root / "step5_input.pdb").write_text(_cryst1_line(68.26, 80.24, 66.59) + "ATOM\n")

    archive_path = tmp_path / f"{top_dir_name}.tgz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(src_root, arcname=top_dir_name)
    return archive_path


def test_extract_finds_final_step_files_box_and_toppar_dir(tmp_path: Path):
    archive_path = _build_solution_builder_archive(tmp_path)

    result = extract_charmm_gui_archive(str(archive_path))

    assert result.success, result.message
    assert Path(result.psf_path).name == "step5_input.psf"
    assert Path(result.pdb_path).name == "step5_input.pdb"
    assert result.box_x == 68.26
    assert result.box_y == 80.24
    assert result.box_z == 66.59
    assert Path(result.toppar_dir).name == "toppar"
    assert Path(result.extracted_dir).exists()


def test_extract_picks_highest_numbered_step_pair(tmp_path: Path):
    src_root = tmp_path / "src" / "cg"
    src_root.mkdir(parents=True)
    (src_root / "step3_input.psf").write_text("PSF\n")
    (src_root / "step3_input.pdb").write_text(_cryst1_line(1.0, 1.0, 1.0))
    (src_root / "step5_input.psf").write_text("PSF\n")
    (src_root / "step5_input.pdb").write_text(_cryst1_line(68.26, 80.24, 66.59))
    archive_path = tmp_path / "cg.tgz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(src_root, arcname="cg")

    result = extract_charmm_gui_archive(str(archive_path))

    assert result.success
    assert Path(result.psf_path).name == "step5_input.psf"
    assert result.box_x == 68.26


def test_extract_succeeds_without_a_final_step_pair(tmp_path: Path):
    # A user who trimmed the archive down, or a builder variant that
    # doesn't use the stepN_input naming -- extraction should still
    # succeed and hand back the folder for manual picking.
    src_root = tmp_path / "src" / "cg"
    toppar_dir = src_root / "toppar"
    toppar_dir.mkdir(parents=True)
    (toppar_dir / "top_all36_prot.rtf").write_text("* topology\n")
    (src_root / "final_system.pdb").write_text("ATOM\n")
    archive_path = tmp_path / "cg.tgz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(src_root, arcname="cg")

    result = extract_charmm_gui_archive(str(archive_path))

    assert result.success
    assert result.psf_path == ""
    assert result.pdb_path == ""
    assert result.box_x is None
    assert Path(result.toppar_dir).name == "toppar"
    assert "No stepN_input.psf/.pdb pair found" in result.message


def test_extract_succeeds_without_a_pdb_cryst1_record(tmp_path: Path):
    src_root = tmp_path / "src" / "cg"
    src_root.mkdir(parents=True)
    (src_root / "step5_input.psf").write_text("PSF\n")
    (src_root / "step5_input.pdb").write_text("ATOM\n")  # no CRYST1 line
    archive_path = tmp_path / "cg.tgz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(src_root, arcname="cg")

    result = extract_charmm_gui_archive(str(archive_path))

    assert result.success
    assert result.psf_path
    assert result.box_x is None


def test_extract_fails_clearly_on_a_non_tar_file(tmp_path: Path):
    bogus = tmp_path / "not_actually_a_tarball.tgz"
    bogus.write_text("just some text, not a real archive")

    result = extract_charmm_gui_archive(str(bogus))

    assert not result.success
    assert "could not extract" in result.message.lower()
