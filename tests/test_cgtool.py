from app.cgtool import (
    build_aicg2p_command,
    build_fasta_text,
    build_structure_builder_command,
    build_duplication_command,
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


def test_build_fasta_text_format():
    # mdgenesis.org tutorial 11.4 (FUS/HPS) example: "> FUS WT\nMASND..."
    text = build_fasta_text("MKTAYIAKQR", header="myprot")
    assert text == ">myprot\nMKTAYIAKQR\n"


def test_build_structure_builder_command_is_verified():
    # Confirmed 2026-09-14 from mdgenesis.org tutorial 11.4: the real
    # dedicated tool for sequence-only IDR/HPS structure+topology
    # building, replacing the old fake-CA-only-PDB-through-aa_2_cg.jl
    # workaround.
    cmd = build_structure_builder_command("myidr.fasta")
    assert cmd.verified
    assert cmd.command == (
        "~/genesis_cg_tool/tools/modeling/protein_artifact/"
        "cg_protein_structure_builder.jl -s myidr.fasta"
    )
    # confirmed twice against the real tutorial: no "julia" prefix, unlike
    # aa_2_cg.jl
    assert not cmd.command.startswith("julia")


def test_build_structure_builder_command_quotes_paths_with_spaces():
    cmd = build_structure_builder_command("my seq.fasta")
    assert "'my seq.fasta'" in cmd.command


def test_build_duplication_command_is_verified():
    # Confirmed 2026-09-14 from mdgenesis.org tutorial 11.4: the real
    # dedicated tool for N-copy slab replication, replacing the old local
    # Python coordinate-math replication (build_slab_system).
    cmd = build_duplication_command(
        top_filename="myidr_cg.top", gro_filename="myidr_single.gro", output_name="myidr_cg", n_copies=5
    )
    assert cmd.verified
    assert cmd.command == (
        "~/genesis_cg_tool/tools/modeling/duplication_modeling/duplication_generator.jl "
        "-t myidr_cg.top -c myidr_single.gro -o myidr_cg --nx 1 --ny 1 --nz 5"
    )
    assert not cmd.command.startswith("julia")
