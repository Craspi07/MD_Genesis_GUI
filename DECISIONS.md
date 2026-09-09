# Decisions Log

Running log of choices made during development and why. Newest entries at the top.

## 2026-09-09 — Two real-hardware bugs found during first local install

The user's first real Windows/WSL2 install (following this README) surfaced
two bugs that no amount of doc-verification would have caught, since both
only show up against real installed software:

1. **`build_slab_system` (app/cgtool.py) crashed on a real genesis_cg_tool
   `.gro` file with `could not convert string to float: '0 0.00'`.** The
   function assumed legacy GROMACS-style rigid 8-character columns for
   x/y/z (`line[20:28]`/`[28:36]`/`[36:44]`). The genesis_cg_tool wiki's
   File-formats page — fetched in the entry below, but not acted on at the
   time — explicitly documents a fixed 20-character prefix
   (resnum/resname/atomname/atomnum) followed by "free-style formatting"
   for coordinates, i.e. NOT fixed columns. On a real file whose spacing
   didn't happen to land on 8-char boundaries, the fixed slice grabbed a
   chunk spanning two numbers. Fixed by parsing coordinates as
   whitespace-separated tokens after the 20-char prefix
   (`_parse_gro_xyz`), matching the documented format. This only affects
   `ModelType.HPS_CONDENSATE` projects with `n_copies > 1` (the only
   caller of `build_slab_system`), which is presumably what the user was
   creating when they hit it. The test fixtures in `tests/test_cgtool.py`
   previously used rigid 8-char-aligned coordinates, which happened to
   parse correctly under either the old or new code and so never would
   have caught this — updated to free-style spacing, plus a dedicated
   regression test (`test_build_slab_system_handles_free_format_coordinate_spacing`)
   using coordinate formatting that specifically breaks the old fixed-slice
   approach.
2. **`vmd_path` had no UI control.** `app/settings.py` has had a
   `vmd_path` field (persisted via `QSettings`) since early on, and
   `ui/tab_analysis.py`'s "Open in VMD" button error message tells the
   user to "set the path in Settings" — but no such field ever existed in
   `ui/dialog_settings.py`'s "Setup & Health Check" dialog. There was
   genuinely no way to change it short of editing the underlying
   `QSettings` store (the Windows registry) by hand. Added a "VMD path"
   row (text field + Browse... file picker) to that dialog, wired to
   load/save like every other field there.

## 2026-09-09 — Live mdgenesis.org access: VERIFY markers resolved

This session had live, working access to `mdgenesis.org` (previously
egress-blocked — see the "Documentation access limitations" entry below,
now superseded) and to the `genesis_cg_tool` GitHub wiki via the normal
`github.com/.../wiki/...` UI (which previously failed to render for the
fetch summarizer; it rendered fine this session). Every `# VERIFY` marker
in `resources/templates/*.j2`, `app/cgtool.py`, and `app/analysis.py` was
re-checked against real pages. What follows supersedes the corresponding
claims in the "Documentation access limitations" entry below.

### Sources fetched
- `mdgenesis.org/docs/usage/`
- `mdgenesis.org/tutorials/genesis_tutorial_11.1_2022/` (AICG2+ protein, 1PGB)
- `mdgenesis.org/tutorials/genesis_tutorial_11.2_2022/` (3SPN.2C DNA)
- `mdgenesis.org/tutorials/genesis_tutorial_11.3_2022/` (PWMcos protein-DNA)
- `mdgenesis.org/docs/examples/` and its linked per-tool pages:
  `rmsd_root-mean-square_deviation_rmsd_analysis`,
  `radius_of_gyration_rg_analysis`,
  `distance-distance_matrix_distmat_analysis`,
  `contact_contact_analysis`, `density_density_analysis`
- `github.com/genesis-release-r-ccs/genesis_cg_tool/wiki` (Home,
  Command-Line-Arguments, File-formats) — full render this session

### Control-file corrections (resources/templates/*.j2)

1. **`forcefield` is `RESIDCG`, not `AICG2+`/model-name.** Every fetched
   CG tutorial (11.1/11.2/11.3) uses `forcefield = RESIDCG` regardless of
   whether the system is AICG2+ protein, 3SPN.2C DNA, or PWMcos
   protein-DNA. The actual force-field choice (AICG2+, 3SPN.2C, Clementi,
   HT) happens when genesis_cg_tool builds the topology
   (`--force-field-protein`/`--force-field-DNA`), not via this
   control-file keyword. All four templates corrected.
2. **`electrostatic` is `CUTOFF`, not `DEBYE_HUCKEL`.** `DEBYE_HUCKEL` was
   never observed as an actual keyword value in any fetched example;
   `CUTOFF` is the value used everywhere (the tutorial's own comment
   reads `electrostatic = CUTOFF # Debye-Huckel model`, i.e. Debye-Huckel
   describes the physics under the `CUTOFF` scheme, it isn't a separate
   keyword value). Corrected in all four templates.
3. **Pairlist keyword is `cg_pairlistdist_exv` (protein-only), or a fuller
   DNA-specific set, not a generic `cg_pairlistdist`.** For AICG2+/HPS
   (protein-only, no DNA): `cg_pairlistdist_exv = 15.0` (tutorial 11.1's
   exact value). For protein+DNA: `cg_cutoffdist_ele`,
   `cg_cutoffdist_DNAbp`, `cg_pairlistdist_ele`, `cg_pairlistdist_DNAbp`,
   `cg_pairlistdist_exv`, `cg_sol_ionic_strength` (tutorial 11.2's exact
   values). `protein_dna.j2` updated accordingly.
4. **`[BOUNDARY] type` for a single AICG2+ protein is `PBC` with a box,
   not `NOBC`.** This was the biggest surprise: even tutorial 11.1's
   single-chain 1PGB run uses `type = PBC` with `box_size_x/y/z = 180.0`,
   not the previously-assumed `NOBC`. `aicg2p.j2` corrected to `PBC` and
   now requires `box_x`/`box_y`/`box_z` on `ControlFileConfig` (same
   requirement `HPS_CONDENSATE` already had) — see `app/control_file.py`
   changes below. `protein_dna.j2` keeps `NOBC`, now confirmed correct:
   both DNA melting/hybridization (tutorial 11.2) and PWMcos (tutorial
   11.3) explicitly use `type = NOBC`. `hps_single.j2` still has no real
   source (HPS/IDR isn't part of any GENESIS tutorial) and stays `NOBC`,
   marked `# VERIFY` with a note pointing at this new AICG2+ finding as
   context, not confirmation.
5. **`[INPUT]`/`[OUTPUT]` keyword names confirmed**: `grotopfile`,
   `grocrdfile`, `rstfile` (both as [INPUT] restart-read and [OUTPUT]
   restart-write), `pdbfile`, `dcdfile` all appear verbatim in tutorial
   11.1's `pro.inp`. Added a missing `pdbfile =` line to `[OUTPUT]` (the
   old template never wrote one).
6. **`logfile` is not a real GENESIS keyword — removed.** No fetched
   control file has a `logfile =` line; every tutorial runs
   `atdyn pro.inp > pro_md1.log`, redirecting stdout instead. This is
   exactly what `runner.py` already does (see `CLAUDE.md`: never rely on
   piped stdout, tail the redirected file), so the old speculative
   `logfile =` line was removed rather than kept as an unrecognized
   keyword that might confuse a real GENESIS run.
7. **`[CONSTRAINTS] rigid_bond = NO`, `[DYNAMICS]` keyword names/values
   (`integrator = VVER_CG`, `nbupdate_period = 20`,
   `eneout_period`/`crdout_period`/`rstout_period`), and `[ENSEMBLE]`
   (`tpcontrol = LANGEVIN`, `gamma_t`) are all now confirmed verbatim**
   against tutorial 11.1's `pro.inp`, so their `# VERIFY` markers were
   removed and replaced with citations.
8. **Citations are now real INI comments in the generated file, not
   Jinja-only `{# #}` template comments.** The first draft of this pass
   used `{# ... #}` for per-keyword citations, which Jinja strips from
   the rendered output entirely (and, combined with `trim_blocks`,
   collapsed several lines together). Per `CLAUDE.md` ("every keyword...
   must have a citation comment pointing to the docs page it came from"),
   citations need to actually appear in the file a user opens — fixed to
   use `#`/`;` real comments throughout.

### New, still-open finding: `box_size_nm` unit mismatch

Tutorial 11.1's example box (`box_size_x = 180.0` for a 56-residue
protein) reads as **Angstrom** — 180 nm would be absurd for that system,
180 Å (≈18 nm of padding) is a normal CG box. `SimulationParameters
.box_size_nm` (in `app/project.py`) is fed straight into `box_size_x/y/z`
with no conversion, and its own name claims nanometers. This predates
this pass (it already existed for `HPS_CONDENSATE`) and wasn't invented
by the `aicg2p.j2` fix; it's now more visible because `AICG2P` needs a
box too. Not silently reinterpreted or renamed here — flagged with a
`# VERIFY` comment in `aicg2p.j2` and logged here per `CLAUDE.md`'s "don't
silently change a default." Whoever wires up a box-size UI field should
resolve whether the value the user types is Å or nm before this matters
for a real run.

### `app/control_file.py` / call-site wiring

`AICG2P` now requires `box_x`/`box_y`/`box_z` like `HPS_CONDENSATE`
already did (`MODEL_TYPES_REQUIRING_BOX` in `control_file.py`). Added
`default_box_size(model_type, box_size_nm)` — a single fallback helper
(180.0 Å cube for AICG2P, the previous 20×20×200 for HPS_CONDENSATE) used
by all three `ControlFileConfig` call sites (`project_creation.py`,
`ui/tab_run.py`'s "Continue" restart, `app/benchmark.py`'s preset runs) so
none of them raise `ValueError` for a project with no explicit box size
configured yet.

### `app/cgtool.py`

- Re-confirmed with full docs access (not just re-guessed): **no
  HPS/KH flag and no sequence-only/N-copy/slab flag exists** on
  `aa_2_cg.jl`. Same conclusion as the blocked session, now on solid
  ground instead of "couldn't check."
- The full `aa_2_cg.jl` flag list is longer than previously captured:
  `--use-safe-dihedral`, `--3spn-use-5-phos`, `--3spn-param`,
  `--cgRNA-phosphate-Go`, `--pwmcos-ns`, `--pwmcos-ns-ene`, `--patch`,
  `--test-local-only` weren't seen in the blocked session's partial
  fetch. None of these are used by this app yet (no DNA/PWMcos CG-tool
  command builder exists — see the new gap noted below), but they're now
  documented for whoever adds one.
- **New confirmed finding, not previously known either way**:
  genesis_cg_tool's wiki Home page states `aa_2_cg.jl` requires "an
  all-(heavy)-atom PDB file for a protein." `generate_extended_chain_pdb`
  builds a **CA-only** trace for the sequence-only/HPS input path, which
  is now a *confirmed* insufficient input, not an open question. Building
  a real all-heavy-atom idealized chain (backbone + sidechain rotamers)
  is a substantially larger feature than this pass — not implemented;
  the limitation is now accurately documented in the function's
  docstring and the whole HPS/sequence pipeline remains `verified=False`
  end to end (still surfaced as a UI warning).
- `inject_idr_hps_region`'s `[ cg_IDR_HPS_region ]` block now uses the
  confirmed field format (`genesis_cg_tool` wiki: File-formats): two
  10-char right-justified integers separated by a space
  (`"%10d %10d\n"`), replacing the previous ad hoc spacing.

### `app/analysis.py`

This had the most actual bugs, not just missing citations:

- **Per-tool `[OUTPUT]` keyword names were wrong.** The old code used a
  single generic `outfile =` for every tool. Real GENESIS analysis tools
  each have their own: `rmsfile` (rmsd_analysis), `rgfile` (rg_analysis),
  `qntfile` (qval_residcg_analysis — already used the real binary name
  from "environment facts," now also confirmed by fetching tutorial
  11.1 Section 3 directly), `outfile` (distmat_analysis — confirmed
  correct for "contact_map" despite the generic-sounding name),
  `mapfile` (density_analysis). `ANALYSIS_TOOLS` now stores
  `(binary, output_keyword, output_filename, label)`.
- **`[TRAJECTORY]` was missing required fields.** The old control file
  had only `trjfile1 =`. Every fetched real example
  (rmsd/rg/density/contact/qval) also has `md_step1`, `mdout_period1`,
  `trj_format = DCD`, `trj_type = COOR+BOX` — added.
- **`[SELECTION]` was missing entirely** — every fetched example defines
  a `group1`, and `[OPTION]`/output sections reference it. Added a
  minimal `group1 = all` (marked `# VERIFY`: real examples select a
  specific atom name or segid, e.g. `an: CA` or `segid:BPTI`, not a bare
  `all`; this app doesn't expose per-residue/atom selection in the UI
  yet, so `all` is the simplest thing that at least defines the group).
- **The `average = YES` "time-averaged" [OPTION] line was fabricated —
  removed, not just re-cited.** No fetched analysis-tool example
  (rmsd/rg/density/contact/distmat/qval) has any averaging-related
  keyword; `distmat_analysis`'s real `[OPTION]` section only has
  `check_only`/`analysis_atom`/`matrix_shape`. The "Contact map
  (time-averaged)" UI button (`ui/tab_analysis.py`) still runs and still
  writes a distinctly-named output file, but the control file no longer
  claims a GENESIS keyword that doesn't exist. Actually averaging
  multiple frames' output in Python (numpy) instead was considered but
  not implemented — flagged as a product question, not silently done.
- **`density_analysis`'s output is a binary CCP4 3D electron-density map
  (`mapfile`) plus a `.pdb`, not the two-column z-profile text file the
  "Density profile (z)" button assumed.** `ANALYSIS_TOOLS["density"]`'s
  filename/extension corrected to `.ccp4`. `ui/tab_analysis.py` updated
  to stop trying to `parse_two_column_series` a binary file (which would
  either crash on decode or silently plot garbage) — it now reports the
  map file's path instead of attempting a line plot. The generated
  control file for density is also flagged as an incomplete skeleton:
  the real example additionally needs `[BOUNDARY]`/`[ENSEMBLE]`/
  `[FITTING]`/`[SPANA_OPTION]`/`[DENSITY_OPTION]` sections
  (`domain_x/y/z`, `num_cells_x/y/z`, `density_type`, `voxel_size`,
  `recenter`, etc.) this minimal skeleton doesn't generate. This is a
  real product gap (does the app even want a CCP4 viewer, or should
  "density profile along z" use a different real GENESIS mechanism?) —
  not resolved here, just accurately documented instead of shipped as a
  silently-broken feature.
- **`grotopfile`/`grocrdfile` for `[INPUT]` kept, with honest confidence
  labeling.** Every non-CG example fetched (rmsd/rg/density/distmat) uses
  atomistic `psffile`/`reffile`, not GROMACS-style CG input. The one
  directly-confirmed CG example, `qval_residcg_analysis` (tutorial 11.1
  Section 3), *does* use `grotopfile`/`grocrdfile`, matching
  `mdgenesis.org/docs/usage/`'s statement that analysis tools work
  "similar to... the MD simulators" (which do accept grotop/grocrd for
  CG runs). Since this app only ever produces CG (RESIDCG) trajectories,
  `grotopfile`/`grocrdfile` was kept for all five tools on that
  inference — but it's still marked `# VERIFY` for the four tools where
  it isn't a directly-witnessed example, rather than silently promoted
  to "confirmed."

### Still-open gaps found along the way (not VERIFY markers, not fixed here)

- **`app/cgtool.py` has no command builder for `ModelType.PROTEIN_DNA`.**
  `project_creation.py`'s `build_cg_commands` falls through to the plain
  AICG2+ builder for any non-sequence input regardless of model type, so
  a protein-DNA project's `.top`/`.gro` are never actually built with
  `--force-field-DNA 3SPN.2C`/`--protein-DNA-Go`/`--pwmcos` etc. This
  predates this pass; `protein_dna.j2`'s control-file corrections above
  are accurate for what the file *should* say once such a pipeline
  exists, but nothing currently generates matching input files for it.
  Flagged here rather than built, since it's a real new feature (DNA
  chain selection, `--pfm`/`--respac` file wiring, wizard UI) outside
  this pass's scope of fixing existing `# VERIFY` markers.
- **`app/log_parser.py`'s `# VERIFY` marker** (run.log column format) is
  outside this pass's three named files, but is directly checkable now:
  tutorial 11.1 confirms GENESIS redirects stdout to a log file rather
  than writing one directly. The exact column-name/ordering question the
  docstring raises wasn't re-checked this pass — left for a follow-up
  since it wasn't in scope.

## 2026-09-09 — Documentation access limitations (superseded above)

This session ran in a sandboxed cloud environment with an egress
allowlist. `mdgenesis.org` was blocked entirely by the network egress
proxy in that session. **A later session (this file's entry above)
had working access and re-verified everything below against the real
docs — treat the entry above as authoritative wherever it overlaps with
this one.**

**What was verified from the accessible GitHub sources (that session):**
- `aa_2_cg.jl`'s documented flags: `--force-field-protein {AICG2+,Clementi}`,
  `--force-field-DNA 3SPN.2C`, `--force-field-RNA HT`, `--aicg-scale`,
  `--CCGO-contact-scale`, `--respac`, `--protein-DNA-Go`, `--pfm`,
  `--pwmcos[-scale|-shift]`, `--mmCIF`, `--psf`, `--cgpdb`, `--cgconnect`,
  `--output-name`, `--debug`, `--show-sequence`, `-v/--verbose`, `--log`.
  (Now confirmed more complete — see the entry above.)
- The `.itp` file format documents `[ cg_IDR_HPS_region ]` and
  `[ cg_IDR_KH_region ]` directives (now confirmed exact field format —
  see the entry above), citing Dignon et al., PLoS Comput Biol 14(1),
  e1005941 (2018) for the HPS model.

**Design decisions that followed from being blocked (still current):**
1. **HPS/IDR single-chain path**: for a user who pastes a sequence with
   no PDB, `cgtool.py` builds an idealized extended-chain PDB from the
   sequence locally, runs `aa_2_cg.jl` on that PDB with
   `--force-field-protein AICG2+`, then rewrites the resulting `.itp` to
   add a `[ cg_IDR_HPS_region ]` block. Still marked `# VERIFY` — now for
   a confirmed reason (CA-only input isn't sufficient; see the entry
   above) rather than an unconfirmed one.
2. **Condensate / N-copy slab mode**: `cgtool.py` builds a single chain's
   CG topology once via the tool, then Python code (not GENESIS CG-tool)
   tiles/translates it into an elongated box. Confirmed (not just
   assumed) that no genesis_cg_tool flag for this exists — see the entry
   above.

## 2026-09-09 — Project layout

The original prompt's directory tree shows `genesis_studio/` as the name of
the project root folder itself (matching "create an empty folder... and put
this file in it"), not a nested Python package. So `main.py`, `app/`,
`ui/`, `resources/`, `tests/` etc. live directly at the repository root,
and imports are plain `from app.wsl import WslBridge` / `from ui.main_window
import MainWindow` with the repo root on `sys.path` (true when running
`python main.py` from the repo root, which is how `README.md` documents
running it).

## 2026-09-09 — No Windows/WSL/GENESIS available in the dev environment

This session runs headless on Linux with no WSL, no GENESIS install, no
Windows, and (mostly) no display. `WslBridge` is built and unit-tested
against a **fake `wsl.exe` shim** (a small Python script standing in for
the real executable) so its quoting, decoding, and process-group logic is
verified without the real thing. End-to-end verification against a real
GENESIS install (health check, an actual `atdyn`/`cgdyn` run, live log
tailing, `*_analysis` tools) has to happen on the user's real machine per
the "Definition of done" — this is called out explicitly in `README.md`
rather than silently claimed as tested.
