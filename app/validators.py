"""PDB/sequence sanity checks and basic resource checks (F2.1, F6).

No external structural-biology dependency (no biopython in
requirements.txt) — this is a deliberately small parser that reads just
enough of the PDB ATOM/HETATM/MODEL records to build the chain summary the
wizard's Input page needs and to catch the common footguns before handing
a file to genesis_cg_tool: multiple NMR-style models, missing residues,
and non-standard residues.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

# Standard 20 amino acids, three-letter -> one-letter.
THREE_TO_ONE: Dict[str, str] = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
}
STANDARD_ONE_LETTER: Set[str] = set(THREE_TO_ONE.values())


@dataclass
class ChainInfo:
    chain_id: str
    residue_count: int
    sequence: str
    nonstandard_residues: List[str] = field(default_factory=list)
    residue_gaps: List[str] = field(default_factory=list)  # human-readable "12-15" gap descriptions
    is_protein: bool = True


@dataclass
class PdbInfo:
    path: str
    model_count: int
    chains: List[ChainInfo]
    hetatm_groups: List[str]
    warnings: List[str]

    @property
    def total_residues(self) -> int:
        return sum(c.residue_count for c in self.chains)


class PdbParseError(ValueError):
    pass


def parse_pdb(path: str) -> PdbInfo:
    """Parse a PDB file into a PdbInfo summary.

    Only ATOM/HETATM/MODEL/ENDMDL records are read; CIF files are not
    parsed here (the wizard only offers CIF as a pass-through to
    genesis_cg_tool's --mmCIF flag, not for local inspection).
    """
    p = Path(path)
    if not p.exists():
        raise PdbParseError(f"File not found: {path}")

    model_count = 0
    in_model = False
    # chain_id -> ordered dict of resseq -> (resname, one_letter_or_None)
    chain_residues: Dict[str, "OrderedResidues"] = {}
    hetatm_groups: Set[str] = set()

    with p.open("r", errors="replace") as fh:
        for line in fh:
            record = line[:6].strip()
            if record == "MODEL":
                model_count += 1
                if in_model:
                    # a second MODEL before ENDMDL: stop parsing further
                    # models to avoid double-counting residues.
                    break
                in_model = True
                continue
            if record == "ENDMDL":
                in_model = False
                continue
            if record == "HETATM":
                resname = line[17:20].strip()
                if resname and resname != "HOH":
                    hetatm_groups.add(resname)
                continue
            if record != "ATOM":
                continue
            if model_count > 1:
                # only summarize the first model
                continue
            altloc = line[16:17].strip()
            if altloc not in ("", "A"):
                continue  # skip alternate conformers past the first
            chain_id = line[21:22].strip() or "A"
            resname = line[17:20].strip()
            try:
                resseq = int(line[22:26])
            except ValueError:
                continue
            icode = line[26:27].strip()
            key = (resseq, icode)
            chain_residues.setdefault(chain_id, OrderedResidues()).add(key, resname)

    if not chain_residues:
        raise PdbParseError("No ATOM records found — is this a valid PDB file?")

    chains: List[ChainInfo] = []
    warnings: List[str] = []
    if model_count > 1:
        warnings.append(
            f"File contains {model_count} models (NMR-style ensemble); only the first model was summarized."
        )

    for chain_id, residues in chain_residues.items():
        keys = residues.ordered_keys()
        seq_chars = []
        nonstandard = []
        for key in keys:
            resname = residues.resname(key)
            one = THREE_TO_ONE.get(resname)
            if one is None:
                nonstandard.append(f"{resname}{key[0]}")
                one = "X"
            seq_chars.append(one)
        gaps = _find_gaps(keys)
        chains.append(
            ChainInfo(
                chain_id=chain_id,
                residue_count=len(keys),
                sequence="".join(seq_chars),
                nonstandard_residues=nonstandard,
                residue_gaps=gaps,
            )
        )
        if nonstandard:
            warnings.append(
                f"Chain {chain_id}: {len(nonstandard)} non-standard residue(s): {', '.join(nonstandard[:10])}"
                + (" ..." if len(nonstandard) > 10 else "")
            )
        if gaps:
            warnings.append(f"Chain {chain_id}: possible missing residues at {', '.join(gaps)}")

    return PdbInfo(
        path=str(p),
        model_count=max(model_count, 1),
        chains=chains,
        hetatm_groups=sorted(hetatm_groups),
        warnings=warnings,
    )


class OrderedResidues:
    def __init__(self) -> None:
        self._order: List[tuple] = []
        self._names: Dict[tuple, str] = {}

    def add(self, key: tuple, resname: str) -> None:
        if key not in self._names:
            self._order.append(key)
            self._names[key] = resname

    def ordered_keys(self) -> List[tuple]:
        return self._order

    def resname(self, key: tuple) -> str:
        return self._names[key]


def _find_gaps(keys: List[tuple]) -> List[str]:
    """Detect non-contiguous residue numbering (a common sign of missing
    residues in the crystal structure)."""
    gaps: List[str] = []
    prev: Optional[int] = None
    for resseq, _icode in keys:
        if prev is not None and resseq - prev > 1:
            gaps.append(f"{prev}-{resseq}")
        prev = resseq
    return gaps


# -- sequence validation (F2.1 sequence mode) --------------------------------
@dataclass
class SequenceValidation:
    valid: bool
    cleaned: str
    length: int
    errors: List[str]


def validate_sequence(raw: str) -> SequenceValidation:
    """Validate a pasted amino-acid sequence for the HPS/IDR sequence-input
    path. Accepts only the 20 standard one-letter codes; whitespace and
    newlines (e.g. pasted FASTA body) are stripped, a leading FASTA header
    line (starting with '>') is dropped.
    """
    errors: List[str] = []
    lines = [line for line in raw.splitlines() if not line.startswith(">")]
    cleaned = "".join(lines).strip().upper().replace(" ", "")

    if not cleaned:
        errors.append("Sequence is empty.")
        return SequenceValidation(valid=False, cleaned="", length=0, errors=errors)

    invalid_chars = sorted({c for c in cleaned if c not in STANDARD_ONE_LETTER})
    if invalid_chars:
        errors.append(
            "Sequence contains characters that aren't standard amino acids: "
            + ", ".join(invalid_chars)
        )

    if len(cleaned) < 2:
        errors.append("Sequence must have at least 2 residues.")

    return SequenceValidation(
        valid=not errors,
        cleaned=cleaned,
        length=len(cleaned),
        errors=errors,
    )


# -- resource checks (F6) -----------------------------------------------------
@dataclass
class ResourceCheck:
    ok: bool
    message: str


def check_disk_space(bridge, path: str, min_gb: float = 5.0) -> ResourceCheck:
    """Warn before a run if free disk space in WSL is low (F6)."""
    import shlex

    result = bridge.run(f"df -BG --output=avail {shlex.quote(path)} | tail -1")
    try:
        free_gb = float(result.stdout.strip().rstrip("G"))
    except (ValueError, AttributeError):
        return ResourceCheck(ok=True, message="Could not determine free disk space.")
    if free_gb < min_gb:
        return ResourceCheck(
            ok=False,
            message=f"Only {free_gb:.1f} GB free at {path} (minimum recommended: {min_gb:.0f} GB).",
        )
    return ResourceCheck(ok=True, message=f"{free_gb:.1f} GB free at {path}.")


def check_core_budget(mpi_ranks: int, omp_threads: int, total_cores: int = 16) -> ResourceCheck:
    """MPI ranks x OMP_NUM_THREADS should equal the machine's physical core
    count (the CPU rule from the original spec's environment facts)."""
    product = mpi_ranks * omp_threads
    if product != total_cores:
        return ResourceCheck(
            ok=False,
            message=(
                f"{mpi_ranks} ranks x {omp_threads} threads = {product}, "
                f"not {total_cores} cores. Adjust ranks/threads to multiply to {total_cores}."
            ),
        )
    return ResourceCheck(ok=True, message=f"{mpi_ranks} ranks x {omp_threads} threads = {total_cores} cores.")
