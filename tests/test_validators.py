from pathlib import Path

import pytest

from app.validators import (
    parse_pdb,
    PdbParseError,
    validate_sequence,
    check_core_budget,
)


def _atom_line(serial, resname, chain, resseq, atomname=" CA ", altloc=" ", icode=" "):
    return (
        f"ATOM  {serial:>5} {atomname:<4}{altloc}{resname:>3} {chain}{resseq:>4}{icode}"
        f"   {0.0:>8.3f}{0.0:>8.3f}{0.0:>8.3f}{1.00:>6.2f}{0.00:>6.2f}\n"
    )


def _simple_pdb(tmp_path: Path) -> Path:
    lines = []
    serial = 1
    # Chain A: a clean 5-residue run.
    for resseq, resname in enumerate(["ALA", "GLY", "SER", "LEU", "VAL"], start=1):
        lines.append(_atom_line(serial, resname, "A", resseq))
        serial += 1
    # Chain B: has a gap (residues 1-3, then jumps to 10-11) and one
    # non-standard residue.
    for resseq, resname in [(1, "MET"), (2, "PRO"), (3, "MSE"), (10, "GLU"), (11, "ASP")]:
        lines.append(_atom_line(serial, resname, "B", resseq))
        serial += 1
    lines.append(f"HETATM{serial:>5}  O   HOH A 100      10.000  10.000  10.000  1.00  0.00\n")
    serial += 1
    lines.append(f"HETATM{serial:>5} ZN   ZN  A 101      11.000  11.000  11.000  1.00  0.00\n")

    path = tmp_path / "sample.pdb"
    path.write_text("".join(lines))
    return path


def test_parse_pdb_basic_chains(tmp_path: Path):
    info = parse_pdb(str(_simple_pdb(tmp_path)))
    assert info.model_count == 1
    chain_ids = {c.chain_id for c in info.chains}
    assert chain_ids == {"A", "B"}

    chain_a = next(c for c in info.chains if c.chain_id == "A")
    assert chain_a.residue_count == 5
    assert chain_a.sequence == "AGSLV"
    assert chain_a.nonstandard_residues == []
    assert chain_a.residue_gaps == []


def test_parse_pdb_detects_gap_and_nonstandard(tmp_path: Path):
    info = parse_pdb(str(_simple_pdb(tmp_path)))
    chain_b = next(c for c in info.chains if c.chain_id == "B")
    assert chain_b.residue_count == 5
    assert "MSE3" in chain_b.nonstandard_residues
    assert chain_b.residue_gaps == ["3-10"]
    assert any("missing residues" in w for w in info.warnings)
    assert any("non-standard" in w for w in info.warnings)


def test_parse_pdb_hetatm_groups_exclude_water(tmp_path: Path):
    info = parse_pdb(str(_simple_pdb(tmp_path)))
    assert info.hetatm_groups == ["ZN"]


def test_parse_pdb_missing_file_raises(tmp_path: Path):
    with pytest.raises(PdbParseError):
        parse_pdb(str(tmp_path / "does_not_exist.pdb"))


def test_parse_pdb_multi_model_warns(tmp_path: Path):
    lines = ["MODEL        1\n"]
    lines.append(_atom_line(1, "ALA", "A", 1))
    lines.append("ENDMDL\n")
    lines.append("MODEL        2\n")
    lines.append(_atom_line(2, "ALA", "A", 1))
    lines.append("ENDMDL\n")
    path = tmp_path / "nmr.pdb"
    path.write_text("".join(lines))

    info = parse_pdb(str(path))
    assert info.model_count == 2
    assert any("models" in w for w in info.warnings)
    # only first model's residues counted
    assert info.total_residues == 1


# -- sequence validation ---------------------------------------------------
def test_validate_sequence_valid():
    result = validate_sequence("MKTAYIAKQRQISFVKSHFSRQ")
    assert result.valid
    assert result.length == len("MKTAYIAKQRQISFVKSHFSRQ")
    assert result.errors == []


def test_validate_sequence_strips_fasta_header_and_whitespace():
    result = validate_sequence(">sp|P0A1|TEST\nMKT AYI\nAKQ\n")
    assert result.valid
    assert result.cleaned == "MKTAYIAKQ"


def test_validate_sequence_rejects_invalid_chars():
    result = validate_sequence("MKTXYZ123")
    assert not result.valid
    assert result.errors


def test_validate_sequence_empty():
    result = validate_sequence("   \n  ")
    assert not result.valid


# -- resource checks ---------------------------------------------------------
def test_check_core_budget_ok():
    result = check_core_budget(4, 4, total_cores=16)
    assert result.ok


def test_check_core_budget_mismatch():
    result = check_core_budget(3, 4, total_cores=16)
    assert not result.ok
    assert "12" in result.message
