from app.cgtool import (
    build_aicg2p_command,
    build_hps_sequence_commands,
    generate_extended_chain_pdb,
    inject_idr_hps_region,
    build_slab_system,
    set_molecule_count_in_top,
    CA_CA_DISTANCE_ANGSTROM,
)


def test_build_aicg2p_command_is_verified():
    cmd = build_aicg2p_command("protein.pdb", "myprot")
    assert cmd.verified
    assert "--force-field-protein AICG2+" in cmd.command
    assert "--cgpdb" in cmd.command
    assert "--output-name myprot" in cmd.command
    assert "protein.pdb" in cmd.command


def test_build_aicg2p_command_disables_safe_dihedral():
    # Real installed GENESIS 2.1.6 rejected the "safe" dihedral encoding
    # (--use-safe-dihedral's default of 1) with "Read_Grotop> [dihedrals]
    # not supported function type: 41" -- see DECISIONS.md (2026-09-14).
    cmd = build_aicg2p_command("protein.pdb", "myprot")
    assert "--use-safe-dihedral 0" in cmd.command


def test_build_aicg2p_command_quotes_paths_with_spaces():
    cmd = build_aicg2p_command("my protein.pdb", "out")
    assert "'my protein.pdb'" in cmd.command


def test_generate_extended_chain_pdb_atom_count_and_spacing():
    seq = "MKTAYIAKQR"
    pdb_text = generate_extended_chain_pdb(seq, chain_id="A")
    atom_lines = [l for l in pdb_text.splitlines() if l.startswith("ATOM")]
    assert len(atom_lines) == len(seq)
    assert pdb_text.strip().splitlines()[-1] == "END"

    x_first = float(atom_lines[0][30:38])
    x_second = float(atom_lines[1][30:38])
    assert abs((x_second - x_first) - CA_CA_DISTANCE_ANGSTROM) < 1e-6


def test_build_hps_sequence_commands_are_unverified():
    steps = build_hps_sequence_commands("MKTAYIAKQR", "myidr", "myidr_extended.pdb")
    assert len(steps) == 3
    assert all(not s.verified for s in steps)
    assert steps[1].local_step is False
    assert "myidr_extended.pdb" in steps[1].command
    assert "--use-safe-dihedral 0" in steps[1].command


def test_inject_idr_hps_region_adds_block_once():
    itp = "[ moleculetype ]\n; name  nrexcl\nMOL  3\n"
    updated = inject_idr_hps_region(itp, 1, 50)
    assert "[ cg_IDR_HPS_region ]" in updated
    assert "1" in updated and "50" in updated

    updated_again = inject_idr_hps_region(updated, 1, 50)
    assert updated_again.count("[ cg_IDR_HPS_region ]") == 1


def _gro_atom_line(resnum, resname, atomname, atomnum, x, y, z):
    # genesis_cg_tool's real .gro output uses "free-style formatting" for
    # coordinates after the fixed 20-char prefix (wiki: File-formats), not
    # rigid 8-char columns -- a single space separator (rather than
    # exactly-aligned 8.3f fields) reflects that and would have caught the
    # fixed-width-slicing bug this test file now regression-tests below.
    return f"{resnum:>5}{resname:<5}{atomname:>5}{atomnum:>5} {x:.3f} {y:.3f} {z:.3f}"


def _sample_gro():
    lines = [
        "test molecule",
        "2",
        _gro_atom_line(1, "MOL", "CA", 1, 0.000, 0.000, 0.000),
        _gro_atom_line(1, "MOL", "CB", 2, 0.100, 0.000, 0.000),
        "   3.00000   3.00000   3.00000",
    ]
    return "\n".join(lines) + "\n"


def _sample_top():
    return (
        "[ system ]\n"
        "test system\n\n"
        "[ molecules ]\n"
        "MOL                 1\n"
    )


def test_set_molecule_count_in_top():
    updated = set_molecule_count_in_top(_sample_top(), 5)
    assert "MOL                 5" in updated


def test_build_slab_system_replicates_atoms_and_box(tmp_path=None):
    gro, top = build_slab_system(_sample_gro(), _sample_top(), n_copies=3, spacing_nm=5.0, xy_margin_nm=10.0)
    lines = gro.splitlines()
    assert lines[1].strip() == "6"  # 2 atoms * 3 copies
    atom_lines = lines[2:8]
    assert len(atom_lines) == 6

    box_line = lines[8]
    box_x, box_y, box_z = [float(v) for v in box_line.split()]
    assert box_z > 5.0 * 2  # spacing * (n_copies - 1) plus margin
    assert "MOL                 3" in top


def test_build_slab_system_handles_free_format_coordinate_spacing():
    """Regression test for "could not convert string to float: '0 0.00'":
    a real genesis_cg_tool .gro file's coordinate spacing doesn't
    necessarily line up with rigid 8-char columns (fixed 20-char prefix,
    then free-style formatting per the wiki's File-formats page). This
    line's coordinates use 1 decimal place and single-space separators --
    slicing line[20:28]/[28:36]/[36:44] on it grabs a chunk spanning two
    numbers and fails float(); splitting on whitespace after the prefix
    does not.
    """
    gro = (
        "test molecule\n"
        "2\n"
        "    1MOL     CA    1 0.0 0.0 0.0\n"
        "    1MOL     CB    2 1.0 0.0 0.0\n"
        "   3.00000   3.00000   3.00000\n"
    )
    gro_out, _top = build_slab_system(gro, _sample_top(), n_copies=2, spacing_nm=5.0, xy_margin_nm=10.0)
    assert gro_out.splitlines()[1].strip() == "4"
