# Decisions Log

Running log of choices made during development and why. Newest entries at the top.

## 2026-09-14 — Validate generated control files against `-h ctrl_all` directly

Every bug in this session's real-run debugging (`VVER_CG` on cgdyn, CRLF/
`;` comments, `--use-safe-dihedral`) shared a root cause: this app's
control-file templates were built by reading tutorial pages and wiki
docs, not by checking against the actual installed GENESIS binary, so
nothing caught a mismatch until a real run failed. `mdgenesis.org` itself
recommends `<engine> -h ctrl_all` as the way to get a real template for
your exact installed version -- this app used that manually, once, to
debug the integrator bug, but nothing made it a standing check.

Added `app/ctrl_reference.py`: parses `<engine> -h ctrl_all` output into
`{section: {keyword: allowed_values_or_None}}` (a trailing comment with a
bracketed comma list, e.g. `# [LEAP,VVER]`, documents allowed values;
plain-text comments mean "known keyword, unconstrained"), and
`validate_control_text()` compares a rendered control file's keywords/
values against it, returning warnings for: a section GENESIS doesn't
recognize, a keyword GENESIS doesn't recognize within a known section, or
a value outside a keyword's documented allowed set. `WslBridge.fetch_ctrl_all()`
runs the actual command. `validate_against_installed_genesis()` chains
fetch + parse + validate, degrading to a single "could not fetch"
warning rather than raising if the binary can't be run.

**Proof of value**: `tests/test_ctrl_reference.py` reproduces the actual
`VVER_CG`-on-cgdyn bug as a direct regression test using the user's real
pasted `-h ctrl_all` output for both engines -- validating `VVER_CG`
against the cgdyn reference is flagged; validating the current
engine-conditional templates against either engine's real reference
passes cleanly.

**Deliberately advisory, not a gate**: results are warnings surfaced to a
human (via a new "Validate against GENESIS" button in the Files tab,
enabled for `run.inp`), not a hard failure blocking project creation or
saves. This module's own parsing of `-h ctrl_all`'s free-text comments
could itself be incomplete for a GENESIS version/build this wasn't
tested against -- false positives are possible, so a human reviews
rather than the app silently refusing to write a file.

**Scope note**: this only covers the control file (`run.inp`), which is
what `-h ctrl_all` describes. It does not cover the topology
(`.top`/`.itp`/`.gro`) -- GENESIS has no equivalent "dump every valid
topology directive" flag. See the conversation for what's practical
there instead (in short: no direct equivalent exists; the nearest analog
is cross-checking `aa_2_cg.jl --help`'s current flag list before invoking
it, and treating an actual short benchmark run, with the now-improved
error surfacing, as the closest thing to a topology validator this
ecosystem has).

## 2026-09-14 — Found it: `--use-safe-dihedral` default writes an unreadable dihedral type

The improved benchmark diagnosis (previous entry) surfaced the real
GENESIS-side crash reason: `Read_Grotop> [dihedrals] not supported
function type: 41`. Cross-checked two independent genesis_cg_tool wiki
pages rather than acting on the number alone:

- **File-formats** documents dihedral function types as original/"safe"
  pairs: "Type 1 / Safe Type 32", "Type 21 / Safe Type 41", "Type 22 /
  Safe Type 52" -- type 41 is the numerically-stabilized ("safe") variant
  of type 21 (a Gaussian dihedral potential), not a mistake or a
  different potential entirely.
- **Command-Line-Arguments** documents `aa_2_cg.jl --use-safe-dihedral I`:
  "0) do nothing; 1) cos^2(k*theta) type (**default**); 2) remove
  dihedral potentials with large angles; 3) sin^3(k*theta) type." The
  *default* (1) is what applies the safe transform and writes type 41 --
  `build_aicg2p_command`/`build_hps_sequence_commands`
  (`app/cgtool.py`) never passed this flag, so every AICG2+-based
  topology this app has ever generated (both plain AICG2+ and the
  HPS/sequence path, which reuses the same command builder for its base
  topology) used the default and wrote type-41 dihedrals.

This installed GENESIS 2.1.6 rejects type 41 outright, meaning it only
reads the *original* types. Fixed by adding `--use-safe-dihedral 0` to
both `aa_2_cg.jl` invocations in `app/cgtool.py` ("do nothing" per the
flag's own documented semantics -- keeps the original type 21/1/22
encoding). This affects every model type built from AICG2+'s topology
builder (AICG2+, HPS single-chain, HPS condensate), not just the
condensate project this was first hit on.

**Not yet known**: whether `--use-safe-dihedral 0`'s "original" dihedral
types are physically equivalent to the "safe" ones for this system, or
whether the "safe" transform exists specifically to avoid a real
numerical problem (singularities near certain angles, per the
File-formats page's own framing) that the original type could hit for
some structures. If a real run later shows energy/force blow-ups or
`NaN`s that a "safe" dihedral would have prevented, that's the tradeoff
made here -- getting GENESIS to read the file at all was the immediate
blocker; revisit if numerical stability becomes the next issue.

## 2026-09-14 — Benchmark diagnosis still missed a real MPI rank crash

Past the CRLF/param fixes, a benchmark run hit an actual MPI rank death
(exit code 1) -- but the diagnosis still only surfaced OpenMPI's generic
"the job to be terminated... Exit code: 1" wrapper text, not GENESIS's
own reason for the crash. Two gaps:

1. `_ERROR_PATTERNS` (app/log_parser.py) didn't match OpenMPI's actual
   wording ("exited on signal", "Exit code:", "the job to be
   terminated", "non-zero status" -- none contain "error"/"fail"/
   "abort" on the same line), so `detect_error_lines` found nothing and
   `_diagnose_empty_log` fell through to a bare last-5-lines tail dump
   that cut off before reaching the relevant part of the log. Added
   patterns for this wording.
2. Even once matched, showing only the matched line(s) isn't enough --
   OpenMPI's termination summary is itself just a symptom; GENESIS's own
   crash reason typically prints a few lines *before* it. `_diagnose_empty_log`
   now includes 5 lines of context before the first match (and the tail
   fallback grew from 5 to 15 lines / 300 to 500 chars) so the actual
   cause has a real chance of showing up in the dialog instead of a
   human having to fetch benchmark.log manually.

Still unresolved: the real root cause of *this* specific rank-2 crash
isn't known yet -- need the fuller benchmark.log to see what GENESIS
printed before OpenMPI's summary. Candidates worth checking once seen:
a `.top`/`.gro` atom-count mismatch, an unresolved `./param/*.itp`
include (verify the 2026-09-11 `param/` copy fix actually matches the
`.top`'s real include paths), or a genuine numerical blowup from the
benchmark's short 2000-step run on a freshly-built topology.

## 2026-09-11 — Three more real-run bugs: CRLF/`;`, missing `param/`, HPS keywords

### 1. Generated `.inp` files had CRLF line endings and `;` comment lines

A real installed GENESIS 2.1.6 failed to parse a generated control file
with `Unknown parameter: [output] ";..."`. Two independent bugs combined
to cause it:

- **CRLF line endings.** This GUI runs as a native Windows process (see
  CLAUDE.md/README). `pathlib.Path.write_text()`'s default newline
  handling translates every `\n` in the string to `os.linesep` on write
  -- `\r\n` on Windows -- regardless of the fact that the target file
  lives on the Linux side via `\\wsl$`. Every `write_text()` call
  producing a GENESIS/genesis_cg_tool-consumed file was silently emitting
  CRLF.
- **`;` full-line comments in `.inp` files.** `_common_sections.j2` and
  `aicg2p.j2` used `;`-prefixed full-line comments (a habit carried over
  from GROMACS `.top`/`.itp` convention, which genesis_cg_tool's own
  output legitimately uses `;` for). GENESIS's own `.inp` control-file
  parser only recognizes `#`. Every fetched tutorial control file used
  `#` exclusively -- this was an unforced, uncited departure introduced
  during template authoring, not something ever confirmed as valid.

Fixed both: added `app/text_io.py` with `write_generated_text()` (forces
`newline="\n"`, strips to ASCII-only -- see below) for every fully
app-generated GENESIS-consumed file, and `write_user_text()` (LF-only,
no ASCII stripping) for the Files tab's user-hand-edited-file save path,
since that content isn't ours to silently alter. Every `;`-comment line
in `.inp`-producing code (the templates; `app/analysis.py`'s control-file
writer had one too, in the density-tool fallback branch) was converted to
`#`. `.itp`/`.top`/`.gro` writes (genesis_cg_tool's own GROMACS-style
output, `app/cgtool.py`/`app/project_creation.py`) now also go through
`write_generated_text` for the LF/ASCII fix, but keep their `;` comments
as-is -- that's the correct GROMACS convention for those file types, not
a bug.

**Also moved long design-rationale comments out of generated files.**
Every template previously carried multi-sentence citation prose inline
(e.g. `# mdgenesis.org tutorial 11.1 pro.inp [ENERGY]: "forcefield =
RESIDCG # Residue-level CG models" -- AICG2+ itself is selected when
building the topology via...`). Per the user's explicit ask, these are
now short single-line tags (`# tutorial 11.1 pro.inp`); the full
rationale for each now lives only in DECISIONS.md (this file and the
2026-09-09/2026-09-10 entries below). Shorter lines are also strictly
safer against the same class of parser fragility this whole bug was
about.

**New test**: `test_generated_control_files_have_no_crlf_or_semicolon_comments`
and `test_write_control_file_writes_lf_and_ascii_only` in
`tests/test_control_file.py`, plus `tests/test_text_io.py` for the
helper functions directly.

### 2. Project creation never copied `genesis_cg_tool`'s `param/` directory

genesis_cg_tool's generated `.top` file `#include`s `./param/*.itp`
relative to the run directory (jobs are launched with `cd
{project.directory} && ...`). Nothing ever put a `param/` directory next
to a project's `.top` file -- every real simulation would have failed to
resolve those includes the moment it got past the control-file parsing
bug above. Added `copy_cg_tool_param()` (`app/project_creation.py`),
called from `run_cg_tool_pipeline` after the CG-tool commands and
HPS/slab post-processing, doing `cp -r ~/genesis_cg_tool/param/.
{project.directory}/param/`; a failure here now fails project creation
with a clear message rather than silently producing a project that can't
actually run. Also added a "genesis_cg_tool/param present" row to
`WslBridge.health_check()` (checked at the global/pre-project-creation
level, alongside the existing `aa_2_cg.jl --help` check, since that's
where every other environment-prerequisite check lives -- there's no
per-project health-check mechanism in this codebase to hook into instead;
flagging this interpretation explicitly in case a per-project check was
actually intended).

### 3. HPS `[ENERGY]`/`[BOUNDARY]` corrected against tutorial 11.4 (FUS)

The user cited "tutorial 18.4" for a verified single-chain FUS `[ENERGY]`
block; no such tutorial exists (`mdgenesis.org`'s highest-numbered
tutorial is 16.3). Cross-checked and found the real one:
**tutorial 11.4**, "Coarse-grained simulation of FUS condensation with
HPS model" (`genesis_tutorial_11.4_2022`) -- a citation-number slip, not
a content error; every keyword/value the user gave matches this tutorial
exactly, independently re-fetched and confirmed word-for-word:

```
[ENERGY]
forcefield = RESIDCG
electrostatic = CUTOFF
cg_cutoffdist_ele = 52.0
cg_cutoffdist_126 = 39.0
cg_pairlistdist_ele = 57.0
cg_pairlistdist_126 = 44.0
cg_sol_ionic_strength = 0.15
cg_IDR_HPS_epsilon = 0.2
```

Single-chain step (`pro.inp`): `[BOUNDARY] type = NOBC` -- confirmed,
the earlier `# VERIFY` on this is now resolved and removed from
`hps_single.j2`. Multi-chain/condensate step (`fus_120.inp`):
`[BOUNDARY] type = PBC` with `box_size_x/y/z = 180.0 / 180.0 / 1800.0` --
applied the same `[ENERGY]` block to `hps_condensate.j2` too (the
force-field parameters don't depend on chain count, only the boundary
does), and corrected `DEFAULT_CONDENSATE_BOX` in `app/control_file.py`
from an earlier unverified `(20.0, 20.0, 200.0)` guess to this real
example's `(180.0, 180.0, 1800.0)`.

**Milestone**: as of this fix, every control-file template keyword is
confirmed against either a real mdgenesis.org tutorial or a real
installed GENESIS's `-h ctrl_all` output -- no `.j2` template has a
remaining `# VERIFY` marker (`test_no_verify_markers_remain`,
`tests/test_control_file.py`). Remaining open `# VERIFY` items live
elsewhere: `app/cgtool.py`'s sequence-only/HPS path (confirmed-insufficient
CA-only PDB input, see the 2026-09-09 entry below) and `app/analysis.py`
(grotopfile/grocrdfile inferred rather than directly witnessed for
rmsd/rg/density/distmat).

**New finding, not acted on**: tutorial 11.4's own condensate example
(`fus_120.inp`) runs on `atdyn`, not `cgdyn`, contradicting this app's
`ui/page_resources.py` auto-pick logic ("cgdyn otherwise/always for
condensate" per README). Not changed here -- it wasn't part of what was
asked, and the engine-conditional integrator fix (2026-09-10 entry below)
already means either engine renders a valid control file regardless of
which one gets picked. Worth a deliberate look if condensate runs keep
surfacing engine-specific issues.

## 2026-09-10 — `integrator = VVER_CG` was engine-specific, not universal

The benchmark-error-surfacing fix above immediately paid off: the very
next benchmark run (a condensate/`cgdyn` project) reported real GENESIS's
own error --

```
Error in [Dynamics] integrator : Unsupported string: "VVER_CG"
```

straight from an installed GENESIS 2.1.6 `cgdyn`. First read as "the
mdgenesis.org-fetched value was simply wrong" (a plausible AI-summarizer
transcription error), the user then ran `-h ctrl_all` on both real
installed binaries -- GENESIS's own template-dump feature, which
`mdgenesis.org/docs/usage/` itself recommends as the source of truth --
and got a more precise answer:

```
$ cgdyn -h ctrl_all
integrator    = LEAP      # [LEAP,VVER]

$ atdyn -h ctrl_all
integrator    = LEAP      # [LEAP,VVER, VVER_CG]
```

So `VVER_CG` is real -- it's just **atdyn-only**; `cgdyn` doesn't
implement it. This lines up exactly with tutorial 11.1's own example,
which explicitly runs on `atdyn`
(`mpirun -np 4 .../bin/atdyn pro.inp > pro_md1.log`), not `cgdyn`. The
actual bug wasn't a wrong value, it was that `_common_sections.j2` is
`{% include %}`-shared across every model template regardless of which
engine (`app.project.Engine`, already tracked per-project as
`resources.engine`) will actually run the file, and it hardcoded a
single integrator value that happens to be invalid on one of the two
engines this app can launch.

Fixed by making the choice engine-conditional: added `engine: str =
"atdyn"` to `ControlFileConfig` (threaded through from
`project.resources.engine.value` at all three call sites --
`project_creation.py`, `ui/tab_run.py`'s "Continue" restart,
`app/benchmark.py`), and `_common_sections.j2` now renders `VVER_CG` for
atdyn (matching the tutorial, and presumably GENESIS's intended CG
force-calculation codepath on that binary, which is why plain `VVER` was
deliberately not chosen as a lowest-common-denominator default) or
`VVER` for cgdyn.

**Process note for future VERIFY work**: `mdgenesis.org` fetches in this
session go through `WebFetch`, which has a small/fast model summarize the
page rather than returning raw text -- worth keeping in mind, though in
this specific case the fetched value turned out to be correct (for
atdyn), just applied too broadly. A real installed binary's own error
message and its `-h ctrl_all` template dump are still the more
authoritative source when the two disagree, and are now available for
this project going forward. Every other keyword this session marked
"confirmed" from mdgenesis.org (see the 2026-09-09 entry below) hasn't
been re-cross-checked against `-h ctrl_all` output wholesale -- only this
one was, because it was the reported symptom.

## 2026-09-10 — Benchmark's "no steps completed" was swallowing the real error

A user's condensate-model benchmark failed with the generic
`"no steps completed within the timeout"` message from
`app/benchmark.py::_run_one_preset`. That message only means "the wrapper
script's shell command exited 0, but `GenesisLogParser` found zero
parseable step records in `benchmark.log`" -- it says nothing about *why*.
Two real possibilities, both silently swallowed before this fix:
1. `mpirun`/`atdyn`/`cgdyn` can exit 0 at the shell level while `run.log`
   still contains a fatal GENESIS-side error or an MPI "not enough
   slots" message (a documented common WSL2 issue per the README) --
   `detect_error_lines`/`detect_slot_error` (`app/log_parser.py`) already
   existed and are used by the real Run tab, but `benchmark.py` never
   called them on the log it fetches.
2. `app/log_parser.py`'s assumed format (`INFO:`-prefixed lines, a header
   row starting with `STEP`) was flagged `# VERIFY` from the start --
   "this session could not reach mdgenesis.org... before relying on this
   for a real run, capture a real run.log ... and adjust." No real
   GENESIS run had happened yet to check this against until now.

Fixed `_run_one_preset` to call `detect_slot_error`/`detect_error_lines`
on the fetched log text and report whichever is found, falling back to
the log's own last few lines (or "was empty") instead of a bare generic
message when nothing else explains it. This doesn't fix the underlying
`log_parser.py` format-guess issue by itself -- it makes it
*diagnosable* from the benchmark dialog directly, which is what's needed
to find out whether that's actually what's going on for this user's
report, without them having to manually fetch `benchmark.log` out of WSL.
Follow-up: once the real log content is known, `app/log_parser.py`'s
`_HEADER_FIRST_TOKEN`/`_INFO_PREFIX` assumptions should be corrected to
match it if they're wrong -- that VERIFY marker is still open.

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
