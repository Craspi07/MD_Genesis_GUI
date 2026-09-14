"""Builds genesis_cg_tool command lines.

Re-confirmed 2026-09-09 with live access to both the genesis_cg_tool wiki
(Command-Line-Arguments, File-formats, Home) and mdgenesis.org -- see
DECISIONS.md for exactly what was fetched. Every command/flag here is
either verified against those pages or explicitly marked `verified=False`
with a `# VERIFY` note when no real doc source covers it. The GUI
(page_parameters.py / tab_files.py) surfaces `verified=False` as a visible
warning rather than silently trusting it -- see CLAUDE.md.

Rewritten 2026-09-14 (see DECISIONS.md): the sequence-only/HPS pipeline
used to fake a CA-only PDB locally and push it through `aa_2_cg.jl`
(the tool for converting a *real* all-heavy-atom structure), then
hand-patch the result with an `[ cg_IDR_HPS_region ]` block. That was
never a valid substitute -- genesis_cg_tool has a dedicated tool for
exactly this case, confirmed from mdgenesis.org tutorial 11.4 (FUS/HPS
model): `cg_protein_structure_builder.jl -s <fasta>` builds an artificial
IDR structure and CG topology directly from a bare sequence, no atomistic
intermediate, and already writes the IDR region markup itself. The old
fake-PDB machinery (`generate_extended_chain_pdb`, `build_hps_sequence_
commands`, `inject_idr_hps_region`) and the local coordinate-math slab
replication (`build_slab_system`) are removed entirely, replaced by
wrappers around the real tools.
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass

CG_TOOL_SCRIPT = "~/genesis_cg_tool/src/aa_2_cg.jl"
STRUCTURE_BUILDER_SCRIPT = "~/genesis_cg_tool/tools/modeling/protein_artifact/cg_protein_structure_builder.jl"
DUPLICATION_SCRIPT = "~/genesis_cg_tool/tools/modeling/duplication_modeling/duplication_generator.jl"


@dataclass
class CgCommand:
    """One step of the CG-tool pipeline: a shell command to run inside
    WSL. `verified` mirrors whether every flag/keyword involved was
    confirmed against the real docs."""

    description: str
    command: str
    verified: bool
    citation: str
    local_step: bool = False


# -- AICG2+ from a real structure (PDB/mmCIF) ---------------------------------
def build_aicg2p_command(pdb_filename: str, output_name: str) -> CgCommand:
    """AICG2+ conversion from a real all-heavy-atom structure file.

    `--force-field-protein AICG2+`, `--cgpdb`, and `--output-name` are all
    documented on the genesis_cg_tool wiki's Command-Line-Arguments page.

    `--use-safe-dihedral 0` added 2026-09-14: aa_2_cg.jl's default
    (--use-safe-dihedral 1) applies a numerically-stabilized dihedral
    transform that writes .itp dihedral function type 41 (genesis_cg_tool
    wiki: File-formats -- "Type 21 / Safe Type 41"). A real installed
    GENESIS 2.1.6 rejected that with "Read_Grotop> [dihedrals] not
    supported function type: 41". Passing 0 ("do nothing", per
    Command-Line-Arguments) keeps the original type 21 dihedral encoding,
    which GENESIS 2.1.6 does read. See DECISIONS.md.
    """
    cmd = (
        f"julia {CG_TOOL_SCRIPT} {shlex.quote(pdb_filename)} "
        f"--force-field-protein AICG2+ --cgpdb --use-safe-dihedral 0 "
        f"--output-name {shlex.quote(output_name)}"
    )
    return CgCommand(
        description="Convert PDB to AICG2+ coarse-grained topology",
        command=cmd,
        verified=True,
        citation="genesis_cg_tool wiki: Command-Line-Arguments "
        "(--force-field-protein, --cgpdb, --output-name, --use-safe-dihedral)",
    )


# -- HPS/IDR from a bare sequence, via the real dedicated tool ---------------
def build_fasta_text(sequence: str, header: str) -> str:
    """FASTA text for cg_protein_structure_builder.jl's `-s` input.

    Confirmed 2026-09-14, mdgenesis.org tutorial 11.4 (FUS/HPS model): the
    example FASTA shown is a ">"-prefixed description line followed by
    the raw sequence, e.g. "> FUS WT\\nMASNDYTQQATQ...".
    """
    return f">{header}\n{sequence}\n"


def build_structure_builder_command(fasta_filename: str) -> CgCommand:
    """Build an artificial IDR structure and CG topology directly from a
    FASTA sequence.

    Confirmed 2026-09-14 from mdgenesis.org tutorial 11.4 (FUS condensate,
    HPS model): `cg_protein_structure_builder.jl -s fus.fasta` produces
    `<basename>_cg.top`, `.itp`, `.gro`, `.psf`, and `.pdb` directly --
    named from the FASTA filename with a `_cg` suffix, no `-o` flag shown
    or needed. The tutorial's resulting .itp is used as-is; it does not
    show or need a separate step adding `[ cg_IDR_HPS_region ]` markup --
    the tool writes it itself. This replaces the previous fake-CA-only-
    PDB-through-aa_2_cg.jl workaround, which was never valid:
    aa_2_cg.jl requires a real all-heavy-atom structure (genesis_cg_tool
    wiki: Home), which a CA-only trace never was. See DECISIONS.md.

    The tutorial invokes this directly, with no `julia` prefix (unlike
    aa_2_cg.jl) -- confirmed twice against independent fetches of the
    same page. Presumably the script is directly executable (its own
    shebang); matched here exactly as shown rather than guessed at.
    """
    cmd = f"{STRUCTURE_BUILDER_SCRIPT} -s {shlex.quote(fasta_filename)}"
    return CgCommand(
        description="Build an artificial IDR structure and CG topology from the sequence",
        command=cmd,
        verified=True,
        citation="mdgenesis.org tutorial 11.4 (FUS/HPS model): "
        "cg_protein_structure_builder.jl -s <fasta>",
    )


# -- condensate / slab replication, via the real dedicated tool --------------
def build_duplication_command(top_filename: str, gro_filename: str, output_name: str, n_copies: int) -> CgCommand:
    """Replicate a single-chain CG system into an N-copy slab.

    Confirmed 2026-09-14 from mdgenesis.org tutorial 11.4: `duplication_
    generator.jl -t <top> -c <gro> -o <name> --nx --ny --nz` (real example:
    `--nx 2 --ny 2 --nz 30` for a 120-copy FUS droplet). This replaces the
    previous local Python coordinate-math replication (removed
    build_slab_system), which duplicated something genesis_cg_tool
    already provides a purpose-built tool for.

    This app currently exposes a single "copy count" to the user, not
    independent x/y/z grid dimensions, so all copies are placed along z
    only (--nx 1 --ny 1 --nz n_copies), matching the original single-axis
    "slab" design intent. The real tutorial's own 2x2x30 example shows a
    denser 3D grid is also valid (arguably more realistic for a
    condensate droplet) -- exposing nx/ny/nz separately in the UI is a
    natural follow-up, not done here since it wasn't asked. See
    DECISIONS.md.

    Confirmed directly invoked with no `julia` prefix, same as
    cg_protein_structure_builder.jl.
    """
    cmd = (
        f"{DUPLICATION_SCRIPT} -t {shlex.quote(top_filename)} -c {shlex.quote(gro_filename)} "
        f"-o {shlex.quote(output_name)} --nx 1 --ny 1 --nz {n_copies}"
    )
    return CgCommand(
        description=f"Replicate into {n_copies} copies along z (slab)",
        command=cmd,
        verified=True,
        citation="mdgenesis.org tutorial 11.4 (FUS/HPS model): "
        "duplication_generator.jl -t/-c/-o/--nx/--ny/--nz",
    )
