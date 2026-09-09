"""Builds genesis_cg_tool command lines and post-processes its output.

Every command/flag here is either verified against the accessible
genesis_cg_tool wiki pages (Command-Line-Arguments, File-formats — see
DECISIONS.md for exactly what was fetched and when) or explicitly marked
`verified=False` with a `# VERIFY` note when it could not be confirmed
because mdgenesis.org was unreachable from this dev environment. The GUI
(page_parameters.py / tab_files.py) surfaces `verified=False` as a visible
warning rather than silently trusting it — see CLAUDE.md.
"""
from __future__ import annotations

import math
import re
import shlex
from dataclasses import dataclass
from typing import List, Tuple

CG_TOOL_SCRIPT = "~/genesis_cg_tool/src/aa_2_cg.jl"

# Idealized CA-CA virtual bond length for an extended polypeptide backbone.
CA_CA_DISTANCE_NM = 0.38  # 3.8 Angstrom, the standard trans-peptide CA spacing
CA_CA_DISTANCE_ANGSTROM = CA_CA_DISTANCE_NM * 10.0


@dataclass
class CgCommand:
    """One step of the CG-tool pipeline: either a shell command to run
    inside WSL, or a local (pure-Python) transformation of a generated
    file. `verified` mirrors whether every flag/keyword involved was
    confirmed against the real docs."""

    description: str
    command: str  # empty string for local-only steps
    verified: bool
    citation: str
    local_step: bool = False


# -- AICG2+ from PDB (verified path) -----------------------------------------
def build_aicg2p_command(pdb_filename: str, output_name: str) -> CgCommand:
    """AICG2+ conversion from a real structure file.

    `--force-field-protein AICG2+`, `--cgpdb`, and `--output-name` are all
    documented on the genesis_cg_tool wiki's Command-Line-Arguments page.
    """
    cmd = (
        f"julia {CG_TOOL_SCRIPT} {shlex.quote(pdb_filename)} "
        f"--force-field-protein AICG2+ --cgpdb --output-name {shlex.quote(output_name)}"
    )
    return CgCommand(
        description="Convert PDB to AICG2+ coarse-grained topology",
        command=cmd,
        verified=True,
        citation="genesis_cg_tool wiki: Command-Line-Arguments "
        "(--force-field-protein, --cgpdb, --output-name)",
    )


# -- HPS from sequence (unverified path, see DECISIONS.md) -------------------
def generate_extended_chain_pdb(sequence: str, chain_id: str = "A") -> str:
    """Build an idealized fully-extended CA-only backbone PDB from a bare
    sequence, so it can be fed through the same aa_2_cg.jl pipeline used
    for real structures.

    # VERIFY: could not confirm from the accessible docs whether
    genesis_cg_tool expects a full backbone (N/CA/C/O + sidechain atoms)
    or tolerates a CA-only trace for its AICG2+/CG mapping. This produces
    a CA-only trace, which is the minimum most CA-based CG mappings need;
    if the real tool requires more atoms this must be extended before
    relying on it for a real run. Confirm against
    mdgenesis.org/tutorials/genesis_tutorial_11.2_2022/ before use.
    """
    lines: List[str] = []
    x = 0.0
    for i, one_letter in enumerate(sequence, start=1):
        resname = _ONE_TO_THREE.get(one_letter, "UNK")
        lines.append(
            f"ATOM  {i:>5}  CA  {resname:>3} {chain_id}{i:>4}    "
            f"{x:>8.3f}{0.0:>8.3f}{0.0:>8.3f}{1.00:>6.2f}{0.00:>6.2f}           C\n"
        )
        x += CA_CA_DISTANCE_ANGSTROM
    lines.append("TER\n")
    lines.append("END\n")
    return "".join(lines)


def build_hps_sequence_commands(sequence: str, output_name: str, extended_pdb_filename: str) -> List[CgCommand]:
    """Full pipeline for a pasted sequence with no PDB: build an idealized
    extended-chain PDB locally, run it through aa_2_cg.jl, then mark the
    full chain as an HPS IDR region in the resulting .itp.

    See DECISIONS.md: no sequence-only or HPS-specific flag was found on
    aa_2_cg.jl itself; HPS is applied via a `[ cg_IDR_HPS_region ]` block
    in the .itp instead, which normally annotates part of a structurally-
    built chain. This whole path is marked unverified.
    """
    steps: List[CgCommand] = [
        CgCommand(
            description="Build an idealized extended-chain PDB from the sequence",
            command="",
            local_step=True,
            verified=False,
            citation="No PDB was supplied — # VERIFY: local approximation, "
            "not a documented genesis_cg_tool workflow.",
        ),
        CgCommand(
            description="Convert the idealized chain to a CG topology",
            command=(
                f"julia {CG_TOOL_SCRIPT} {shlex.quote(extended_pdb_filename)} "
                f"--force-field-protein AICG2+ --cgpdb --output-name {shlex.quote(output_name)}"
            ),
            verified=False,
            citation="# VERIFY: aa_2_cg.jl has no HPS flag; using --force-field-protein "
            "AICG2+ as the base topology builder for a fully-disordered chain is unconfirmed.",
        ),
        CgCommand(
            description="Mark the full chain as an HPS IDR region in the .itp",
            command="",
            local_step=True,
            verified=False,
            citation="genesis_cg_tool wiki: File-formats ([ cg_IDR_HPS_region ] directive; "
            "Dignon et al. PLoS Comput Biol 14(1) e1005941, 2018) — # VERIFY exact block syntax.",
        ),
    ]
    return steps


def inject_idr_hps_region(itp_text: str, start_residue: int, end_residue: int) -> str:
    """Append a `[ cg_IDR_HPS_region ]` block to an .itp's text, marking
    `start_residue`..`end_residue` (1-indexed, inclusive) as an HPS IDR.

    # VERIFY: the exact directive syntax (field names/order) is inferred
    from an AI-summarized fetch of the wiki's File-formats page, not the
    raw page text, since that page could not be fully rendered. Confirm
    field names against a real genesis_cg_tool output file before trusting
    this for a production run.
    """
    if "[ cg_IDR_HPS_region ]" in itp_text:
        return itp_text
    block = (
        "\n; # VERIFY: block syntax inferred from genesis_cg_tool wiki summary, not confirmed verbatim\n"
        "[ cg_IDR_HPS_region ]\n"
        "; IDR starting index   IDR ending index\n"
        f"{start_residue}                     {end_residue}\n"
    )
    return itp_text.rstrip("\n") + "\n" + block


_ONE_TO_THREE = {
    "A": "ALA", "R": "ARG", "N": "ASN", "D": "ASP", "C": "CYS",
    "Q": "GLN", "E": "GLU", "G": "GLY", "H": "HIS", "I": "ILE",
    "L": "LEU", "K": "LYS", "M": "MET", "F": "PHE", "P": "PRO",
    "S": "SER", "T": "THR", "W": "TRP", "Y": "TYR", "V": "VAL",
}


# -- condensate / slab replication (local, no verified CG-tool flag) --------
def build_slab_system(
    gro_text: str,
    top_text: str,
    n_copies: int,
    spacing_nm: float = 5.0,
    xy_margin_nm: float = 10.0,
) -> Tuple[str, str]:
    """Replicate a single-molecule .gro into an N-copy elongated (slab) box
    and update the .top `[ molecules ]` count to match.

    No genesis_cg_tool flag for N-copy/slab generation was found in the
    accessible docs (see DECISIONS.md), so this is done here with plain
    coordinate/topology math rather than guessed-at GENESIS flags: copies
    are placed on a line spaced `spacing_nm` apart along z, inside a box
    just big enough in x/y to hold the molecule plus `xy_margin_nm`.
    """
    if n_copies < 1:
        raise ValueError("n_copies must be >= 1")

    lines = gro_text.splitlines()
    if len(lines) < 3:
        raise ValueError("Malformed .gro file (need title, atom count, atoms, box)")

    title = lines[0]
    n_atoms = int(lines[1].strip())
    atom_lines = lines[2 : 2 + n_atoms]
    box_line = lines[2 + n_atoms]
    _orig_box = [float(v) for v in box_line.split()]

    coords = []
    for line in atom_lines:
        x, y, z = float(line[20:28]), float(line[28:36]), float(line[36:44])
        coords.append((x, y, z))
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    zs = [c[2] for c in coords]
    extent_x = (max(xs) - min(xs)) if coords else 0.0
    extent_y = (max(ys) - min(ys)) if coords else 0.0
    extent_z = (max(zs) - min(zs)) if coords else 0.0

    box_x = extent_x + xy_margin_nm
    box_y = extent_y + xy_margin_nm
    box_z = extent_z + spacing_nm * (n_copies - 1) + xy_margin_nm

    new_lines = [title, str(n_atoms * n_copies)]
    global_atom_index = 1
    for copy_index in range(n_copies):
        z_offset = spacing_nm * copy_index
        resnum_offset = copy_index * _residue_count(atom_lines)
        for line in atom_lines:
            resnum = int(line[0:5]) + resnum_offset
            resname = line[5:10]
            atomname = line[10:15]
            x = float(line[20:28])
            y = float(line[28:36])
            z = float(line[36:44]) + z_offset
            new_lines.append(
                f"{resnum % 100000:>5}{resname}{atomname}{global_atom_index % 100000:>5}"
                f"{x:>8.3f}{y:>8.3f}{z:>8.3f}"
            )
            global_atom_index += 1
    new_lines.append(f"{box_x:>10.5f}{box_y:>10.5f}{box_z:>10.5f}")
    new_gro = "\n".join(new_lines) + "\n"

    new_top = set_molecule_count_in_top(top_text, n_copies)
    return new_gro, new_top


def _residue_count(atom_lines: List[str]) -> int:
    seen = set()
    for line in atom_lines:
        seen.add(int(line[0:5]))
    return len(seen)


def set_molecule_count_in_top(top_text: str, n_copies: int) -> str:
    """Rewrite the multiplicity of the (single) molecule listed in a .top
    file's `[ molecules ]` section."""
    lines = top_text.splitlines()
    out = []
    in_molecules = False
    replaced = False
    for line in lines:
        stripped = line.strip()
        if stripped.lower() == "[ molecules ]":
            in_molecules = True
            out.append(line)
            continue
        if in_molecules and stripped.startswith("[") and stripped != "[ molecules ]":
            in_molecules = False
        if in_molecules and stripped and not stripped.startswith(";"):
            parts = stripped.split()
            if len(parts) >= 2 and not replaced:
                out.append(f"{parts[0]:<20}{n_copies}")
                replaced = True
                continue
        out.append(line)
    return "\n".join(out) + ("\n" if not top_text.endswith("\n") else "")
