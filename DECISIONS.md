# Decisions Log

Running log of choices made during development and why. Newest entries at the top.

## 2026-09-16 — VMD path: auto-detect + fixing "no way to set it" discoverability

Reported: "vmd is not found in the path although it is installed by
default. Also, there is no option for setting button in GUI to set the
path manually." The VMD path field (with a Browse... button) has
existed in the Settings dialog since earlier this session -- the real
problem was two-fold:

1. **Discoverability**: the dialog was only reachable via
   `Tools > Health Check...`. A user looking for "where do I set the
   VMD path" has no reason to click something labeled "Health Check."
   Renamed the menu action to `Tools > Settings...` (`ui/main_window.
   py`) -- the dialog itself still opens with its existing "Setup &
   Health Check" title, so that context isn't lost, but the menu entry
   now matches what a user would actually search for.
2. **The default path itself doesn't match every real VMD install**:
   `Settings.vmd_path` only ever had one hardcoded guess
   (`C:\Program Files\University of Illinois\VMD\vmd.exe`). Real VMD
   installers, including the 2.x alpha builds discussed earlier this
   session, commonly install under a version-suffixed folder instead
   (e.g. "VMD 2.0 alpha", "VMD 1.9.4a55") -- so "installed by default"
   can still miss this app's one guessed path.

Added `app/vmd_detect.py`'s `detect_vmd_path()`: searches a small list
of real install roots (`Program Files`/`Program Files (x86)`, with and
without the "University of Illinois" vendor folder) plus any
version-suffixed sibling folder at each root, rather than trusting one
hardcoded path. Wired to a new "Detect" button in the Settings dialog
next to the existing Browse... button -- fills the field and reports
what it found, or says plainly that nothing was found (directing the
user to Browse... manually) rather than guessing further. This mirrors
the existing "Detect installed distros" pattern already used for the
WSL distro field.

## 2026-09-16 — File > Open Project

Requested directly: reopening an already-created project previously
required either the Dashboard tab or the Projects tree dock -- there
was no File menu equivalent of "Open Project," which is the
conventional place to look for it and the only path that lets a user
open a project GENESIS Studio has never seen before in this session's
`Settings.recent_projects` (e.g. one created on a different machine
sharing the same WSL projects folder). Added `File > Open Project...`
(Ctrl+O) using `QFileDialog.getExistingDirectory`, starting at the
projects root (new `local_projects_root_for()` in
`app/project_creation.py`, factored out of the existing
`local_directory_for()` so the UNC-path construction logic stays in one
place per CLAUDE.md). Picking a folder that isn't a real project
(missing/corrupt `project.json`) shows a `QMessageBox.warning` rather
than failing silently, matching the pattern already established for
`File > New Project`'s and the dashboard's own load-failure paths.

## 2026-09-16 — Roadmap Phase 6: plotting upgrade (secondary axis, zoom/pan, CSV export)

No GENESIS docs to verify this time -- pure UI/UX, the last of the six
roadmap phases.

**Real bug fixed**: `ui/tab_run.py`'s and `ui/tab_analysis.py`'s
"temperature/energy over time" plots called `MplCanvas.set_series` for
TOTAL_ENE/POTENTIAL_ENE and TEMPERATURE all on the same single y-axis.
Energy terms run in the thousands (kcal/mol); temperature sits around
300 K. On a shared axis, temperature's line is visually flattened to
near-zero -- the plot silently failed to show what it claimed to show
whenever both were plotted together, which is every time this button
was used. `MplCanvas.set_series` gained an `axis="secondary"` option
(a lazily created `Axes.twinx()`, its own y-axis label, lines tracked
separately, and a combined legend built from both axes' handles so the
legend doesn't silently drop the secondary series). `clear()` tears the
secondary axis down (`figure.delaxes`) so re-plotting after a Start/
Stop cycle or a fresh analysis run doesn't accumulate stale axes.

**Zoom/pan/save**: matplotlib's own `NavigationToolbar2QT` (from
`matplotlib.backends.backend_qtagg`, the same backend module already
imported for `FigureCanvasQTAgg` -- no new dependency) added above the
canvas in both tabs. This is standard matplotlib, not a custom
control -- CLAUDE.md's "PyQt5 only, no web views" rule is unaffected
since this is still pure Qt widgets.

**CSV export**: added `app/csv_export.py` alongside the existing
`app/excel_export.py`, reusing the same `AnalysisSeries`/
`AnalysisMatrix` dataclasses so results collected by the Analysis tab
don't need a second in-memory representation. CSV has no equivalent of
Excel's multiple sheets, so `export_to_csv` writes one file per
series/matrix into a user-chosen directory instead of one workbook.

**Deliberately not attempted**: true multi-panel plotting (e.g., a
per-replica REMD view). Phase 4 already deferred "Run tab support for
viewing per-replica status" because REMD's real stdout output format
(what `GenesisLogParser` would need to keep parsing) was never verified
against an actual REMD run -- building a multi-panel layout for data
this app can't yet reliably parse would be exactly the kind of
speculative feature this whole roadmap's discipline avoids. Revisit
once a real REMD run's log format is confirmed.

## 2026-09-16 — Roadmap Phase 5: all-atom CHARMM control-file support (layer only)

Researched using the same GENESIS User Guide v2.0.0 PDF as Phases 3/4
(Ch. 4 `[INPUT]`, Ch. 6 `[ENERGY]`, Ch. 9 `[CONSTRAINTS]`). This phase
changed shape the most once actually read: the original `ROADMAP.md`
draft imagined this app running a solvation/ionization pipeline the way
it runs `genesis_cg_tool` for CG. Sec. 4.1 says otherwise outright:
"the users have to prepare input files... by using a setup tool" --
CHARMM needs `top, par, psf, pdb` prepared via VMD/PSFGEN, CHARMM-GUI,
or CHARMM itself; AMBER needs `prmtop, pdb/crd` via LEaP. GENESIS
itself, like `genesis_cg_tool` for CG, is never the system-building
tool -- it only ever consumes already-built files. So this app's real
job for all-atom is identical in shape to what it already does for CG:
turn a set of prepared input files into a correct control file, nothing
more.

Given that, Phase 5 shipped the control-file/template layer only --
`ModelType.ALL_ATOM_CHARMM`, `resources/templates/all_atom_charmm.j2`,
new `ControlFileConfig` fields (`aa_top_files`/`aa_par_files`/
`aa_str_files`/`aa_psf_file`/`aa_pdb_file`), and validation in
`render_control_file` (rejects the model type without all required
files, or without a box) -- fully tested in `tests/test_control_file.
py`. **Wizard/project-creation integration was deliberately not
attempted in this pass**: there's no ModelPage card, no page for
collecting the five file paths + box dimensions, and no
`project_creation.py` logic to copy them into a project directory. That
is real, well-defined remaining work (per Phase 1's own precedent of
naming what's deferred rather than silently skipping it), not
something rushed to appear complete.

**Why a new template instead of extending `_common_sections.j2`**:
that file is written entirely around this app's CG pipeline --
`VVER_CG`/`cgdyn`'s `VVER` as the only two integrator branches,
`rigid_bond = NO` hardcoded (fine for CG, wrong for real AA explicit
solvent), CG-scale timesteps (5-20 fs) implied throughout, and the
`[SELECTION]`/`[RESTRAINTS]`/`[REMD]`/`[GAMD]` additions from Phases
3-4 all assume a CG bead system. Threading AA-specific branches through
all of that would have made an already-dense shared file harder to
verify line-by-line, for a phase whose whole discipline is "verify
every line." `all_atom_charmm.j2` is self-contained and only reuses the
Phase 3/4 keyword *knowledge* (NPT pressure/gamma_p, POSI restraints),
not the file, so it can also skip [REMD]/[GAMD] entirely -- neither was
implemented for AA in this pass either, though nothing here blocks
adding them the same way CG got them.

**A genuinely good outcome of using plain `VVER` instead of CG's
`VVER_CG`**: every `# VERIFY` this session attached to NPT/REMD/GaMD's
`tpcontrol`/engine compatibility existed specifically because
`VVER_CG`/`cgdyn` fall outside the User Guide's own ATDYN/SPDYN
compatibility tables. All-atom CHARMM mode uses plain ATDYN `VVER`,
which *is* in those tables -- so NPT with `tpcontrol=LANGEVIN` is
directly confirmed for it, no caveat needed. This is a real, structural
difference between the CG and AA pipelines' risk profile, not
carelessness in one or the other.

**Confirmed CHARMM defaults used, none guessed**: `electrostatic=PME`
(default, needs PBC -- Sec. 6.2), `switchdist=10.0`/`cutoffdist=12.0`/
`pairlistdist=13.5` (Sec. 6.2 defaults), `vdw_force_switch=YES` ("should
be specified in the case of CHARMM36", Sec. 6.2), `rigid_bond=YES`/
`fast_water=YES` (Sec. 9.4's own CHARMM `[CONSTRAINTS]` example),
`nbupdate_period=10` (Sec. 7.1 default -- deliberately not reusing the
CG templates' `nbupdate_period=20`, which is cited to a CG tutorial,
not a generic default). Box size is required from the user with no
tutorial-style fallback (unlike CG's `DEFAULT_BOX_SIZE`): an all-atom
box must match whatever box the user's own setup tool already built,
and guessing one here risks silently mismatching a real prepared
system.

## 2026-09-16 — Roadmap Phase 4: REMD (T-REMD) + GaMD

Continued researching the same GENESIS User Guide v2.0.0 PDF used for
Phase 3 (Ch. 15 `[REMD]`, Sec. 5.2 REMD output files, Ch. 17 `[GAMD]`).

**Corrected a wrong assumption from `ROADMAP.md`'s own original
write-up**: it assumed REMD would need `runner.py` to "manage N
processes instead of 1 — real architecture change." The User Guide
(Ch. 15) says otherwise: "REMD simulations in GENESIS require an MPI
environment. At least one MPI process must be assigned to one replica"
-- meaning REMD is **one** `mpirun` launch of the same `atdyn`/`cgdyn`
binary with more total ranks (ranks-per-replica x n_replicas); the
control file's own `[REMD]` section tells GENESIS how to partition
ranks into replicas internally. So Phase 4 needed no new process-
management architecture: `app/runner.py`'s `build_wrapper_script`
gained an `n_replicas` parameter that just multiplies `-np`, and
`SimulationRunner.start()` passes `project.parameters.remd_n_replicas`
through when REMD is enabled. This is a good example of why this
session's discipline is "verify before building," not "guess an
architecture, then build toward the guess."

**REMD output files**: confirmed (Sec. 5.2/5.6) that REMD requires
`{}` in `logfile`/`dcdfile`/`remfile`/`rstfile` -- GENESIS substitutes
it with the replica index itself. `pdbfile` (ATDYN's restart-PDB
convenience file) is not mentioned as needing `{}` and isn't confirmed
either way, so it's omitted entirely under REMD rather than guessed
one way or the other. `app/runner.py`'s `_cleanup_previous_outputs`
extended to `rm -f` a `_rep*` glob for these files (same collision risk
as the plain-filename case already fixed 2026-09-14, just replica-
indexed).

**Scope explicitly narrowed, not guessed around**: the User Guide
documents REUS, gREST, multi-dimensional REMD, and REMD/GaMD
combinations (GaREUS) -- none of that is exposed. T-REMD (temperature
exchange) is the only REMD type implemented, since it's the simplest,
has a complete confirmed example (Sec. 15.4.1), and this app has no
existing collective-variable/reaction-coordinate concept a REUS UI
would need. Replica temperatures are typed directly by the user (space-
separated, validated to match the replica count) rather than
auto-generated, since the User Guide itself defers to an external tool
("REMD temperature generator", http://folding.bmc.uu.se/remd/) for
choosing a good ladder -- inventing a spacing formula here would be
exactly the kind of unconfirmed guess this codebase avoids.

**GaMD**: `boost_type = POTENTIAL` is the only mode offered. `DUAL`
(the GENESIS default) and `DIHEDRAL` both need a `sigma0_dih` keyword
whose documented default wasn't visible in the fetched pages -- rather
than guess a number for an energy-scale parameter, only `POTENTIAL`
(needs `sigma0_pot` only, confirmed default 6.0 kcal/mol) is exposed.
`update_period` defaults to GENESIS's own documented 0, but 0 means
"never adapt" -- a syntactically valid, scientifically inert control
file -- so `render_control_file` now raises if `gamd_enabled` and
`update_period <= 0`, and the wizard checkbox auto-fills 500 (a
non-zero starting point the user must still review, not a validated
GENESIS-recommended value) the moment it's checked, so the checkbox is
never left in that silently-broken state.

**Engine gating**: the User Guide's own regression-test directory
listing (Sec. 2.1.4) names `test_gamd_atdyn`/`test_gamd_spdyn` but no
cgdyn equivalent, and `test_remd_spdyn`/`test_remd_common` but neither
an atdyn- nor cgdyn-specific REMD test. Since this app only ever
targets atdyn/cgdyn (never spdyn), *neither* engine's REMD support is
directly confirmed, so REMD's `# VERIFY` note applies regardless of
engine; GaMD's only applies when the engine isn't atdyn, since atdyn
specifically is confirmed while cgdyn is not.

## 2026-09-16 — Roadmap Phase 3: NPT ensemble + position restraints

Verified against the real **GENESIS User Guide v2.0.0 PDF**
(`mdgenesis.org/assets/fundamental/GENESIS_UserGuide_v2.0.0.pdf`, fetched
live and parsed page-by-page since restraints/ensembles aren't covered by
any tutorial page) rather than a tutorial, since this phase's features
are general engine behavior, not one CG model's example. This is the
first time this session verified against the actual engine reference
manual instead of a tutorial or `-h ctrl_all` -- worth noting because it
opens up the same source for later phases.

**Position restraints (real bug fix)**: `ui/page_parameters.py`'s
"Apply position restraints" checkbox and `SimulationParameters.
use_position_restraints` have existed since before this roadmap, wired
all the way through `Project.save`/`load` and into the wizard's project
object -- but `app/control_file.py` never read the field. The checkbox
did nothing. Confirmed the real GENESIS syntax (User Guide Sec. 13.1):
`[RESTRAINTS] nfunctions=1, function1=POSI, constant1=<force
constant>, select_index1=1`, referencing a `[SELECTION] group1=all`,
with reference coordinates supplied via a new `[INPUT] groreffile =
<same .gro as grocrdfile>` line (POSI's reference value is otherwise
ignored per the docs -- confirmed groreffile is the correct keyword for
GROMACS-format input, alongside the doc's reffile/ambreffile
alternatives for other formats). Added `SimulationParameters.
position_restraint_force_constant` (default 10.0, matching the User
Guide's own POSI example in Sec. 16.4) since the checkbox alone had no
way to set restraint strength, and wired both fields through
`app/project_creation.py` and `ui/tab_run.py`'s `_on_continue` (the two
places that build a `ControlFileConfig`).

**NPT ensemble**: `ControlFileConfig.ensemble`/`SimulationParameters.
ensemble` already existed but were dead too -- always "NVT", never
exposed anywhere. Confirmed real `[ENSEMBLE]` keywords for NPT (Sec.
10.1): `pressure` (atm), `gamma_p` (Langevin barostat friction, default
0.1 ps^-1). Added an ensemble combo (NVT/NPT) and a pressure field to
the wizard's Parameters page, gated to `MODEL_TYPES_REQUIRING_BOX`
(AICG2P, HPS_CONDENSATE) since NPT needs a periodic box to compress —
`render_control_file` now raises `ValueError` if NPT is requested for a
NOBC model type (HPS_SINGLE, PROTEIN_DNA) instead of silently emitting
a control file GENESIS would reject.

One thing explicitly NOT carried over from the doc as confirmed: the
User Guide's own ATDYN/SPDYN tpcontrol-compatibility table (Sec. 10.1)
lists `LANGEVIN` as valid for NVT/NPT/NPAT/NPgT under generic ATDYN's
`VVER`, but that table never mentions `VVER_CG` (atdyn's CG-specific
integrator, used by every template this app renders for atdyn) or
`cgdyn` at all -- both are CG-tool-specific binaries outside this
general user guide's coverage, and this session already has one proven
case (the original VVER_CG bug) where a real CG binary's behavior
genuinely differed from generic engine expectations. Rather than repeat
that mistake, `tpcontrol = LANGEVIN` is kept unchanged for NPT (least
change from what's already proven working for NVT) but the generated
`.inp` file itself gets an explicit `# VERIFY` block explaining exactly
why, directing the user to check a real `atdyn`/`cgdyn -h ctrl_all`
before trusting an NPT run. NPAT/NPgT ensembles were not implemented at
all -- both require `isotropy` settings meaningful only for membrane
systems (Sec. 10.1: `SEMI-ISO`/`XY-FIXED`), and this app has no
membrane/lipid CG force field to exercise them against.

Bonus: researching this phase's `[RESTRAINTS]`/`[ENSEMBLE]` sections in
the User Guide PDF also surfaced the full `[REMD]` section reference
(Ch. 15) needed for Roadmap Phase 4 -- saved for that phase rather than
acted on now, but means Phase 4 starts with real keyword documentation
already in hand instead of a fresh research pass.

## 2026-09-15 — Roadmap Phase 2: RMSF and SASA added to the Analysis tab

RMSD/Rg/Q-value/contact-map/density already existed in `app/analysis.py`
before this roadmap; the two tools genuinely missing were RMSF and SASA.
Both needed real research (`mdgenesis.org`'s own example pages, fetched
live) rather than reuse of the existing `write_analysis_control_file`
pattern, because both tools take fundamentally different `[INPUT]`.

**RMSF**: confirmed there is no single "rmsf_analysis" binary -- the
real tool is `flccrd_analysis` (root-mean-square fluctuation), and it
needs a prerequisite `avecrd_analysis` run first to produce
`pdb_avefile`/`pdb_aftfile` (average and "after-fit" reference
structures). Confirmed exact keywords from mdgenesis.org's own example
pages:
- `avecrd_analysis`: `[INPUT] reffile`/`psffile`; `[OUTPUT] pdbfile`/
  `rmsfile`/`pdb_avefile`/`pdb_aftfile`; `[TRAJECTORY]` (with
  `ana_period1`/`repeat1`/`trj_natom`, shown in the doc example but not
  part of the shorter block already proven for rmsd/rg/qvalue/distmat --
  kept as a second, separate block rather than risk changing a working
  pattern); `[SELECTION]`; `[FITTING] fitting_method=TR+ROT`; `[OPTION]`.
- `flccrd_analysis`: same `[INPUT]` shape plus `pdb_avefile`/
  `pdb_aftfile` from the avecrd step; `[OUTPUT] rmsfile` (pcafile/
  vcvfile/crsfile omitted as not needed -- `# VERIFY`, not directly
  witnessed that omitting them is safe for this specific tool, though
  every other GENESIS analysis tool's `[OUTPUT]` keywords are
  independently optional by omission).

Neither tool's docs show `grotopfile`/`grocrdfile` (GROMACS format) as
an alternative to `psffile`/`reffile` -- unlike rmsd_analysis etc.,
which do. This matters because it's genuinely unconfirmed whether
`aa_2_cg.jl --cgpdb` (the AICG2+/PDB-input pipeline) writes a `.psf` at
all; only `cg_protein_structure_builder.jl` (the sequence/HPS pipeline)
is confirmed to (`app/cgtool.py`'s own docstring). Rather than guess by
`project.model_type`, `rmsf_inputs_available()` checks for a real
`.psf`+`.pdb` in the project directory at call time and the Analysis
tab's RMSF button is enabled/disabled from that, with a tooltip
explaining why when disabled. If it turns out `aa_2_cg.jl` also writes
a `.psf`, this gate does the right thing automatically with no code
change; if not, it never sends an AICG2+ project into a pipeline that
was never confirmed to work for it.

**SASA**: confirmed the real tool is `sasa_analysis` (SPANA framework),
needing `[INPUT] psffile`/`reffile`/`pdbfile` (same `reffile`==`pdbfile`
duplication shown in the doc's own example), `[OUTPUT] txtfile`,
`[BOUNDARY]`, `[ENSEMBLE]`, `[SELECTION]`, `[SPANA_OPTION]`,
`[SASA_OPTION]` (`solute`, `radi_file`, `probe_radius=1.4`,
`delta_z=0.2`, `output_style`, `recenter`). `output_style = history`
chosen specifically because it's documented as "temporal profile of
total SASA only" -- a plain two-column series `parse_two_column_series`
already handles, unlike `atomic`/`atomic+history`'s per-atom output.
Same `.psf`/`.pdb` gating as RMSF (`sasa_inputs_available`, currently
identical to `rmsf_inputs_available`).

Two things called out instead of guessed:
- `[BOUNDARY]`'s `domain_x/y/z`/`num_cells_x/y/z` (SPANA spatial
  decomposition sizing): the doc example's values were sized for that
  example's own box and parallel rank count, so copying them would be
  exactly the kind of unfounded guess this whole codebase's discipline
  exists to avoid. Used the smallest possible decomposition (a single
  domain, single cell) for a serial single-rank run instead, with an
  explicit `# VERIFY` written directly into the generated `.inp` file
  (not just a code comment) so it's visible if the user opens the file,
  and will need confirming against a real install.
- `radi_file` (an atom-radius definition file `[SASA_OPTION]` requires):
  no default ships anywhere documented, unlike `vmd_path`'s guessable
  Windows install path. Rather than hardcode a guessed path, added
  `Settings.sasa_radius_file` (new Settings dialog field, empty by
  default) the user must point at a real file; the SASA button stays
  disabled with a tooltip until it's set, and `run_sasa_analysis`
  refuses with an explicit message if called without one.

## 2026-09-15 — Roadmap Phase 1: multi-project dashboard + workflow clarity

Asked to "expand the GUI to include everything GENESIS can do and make
it better" -- too broad to attempt as one change, so it became a
six-phase plan (`ROADMAP.md`), sequenced by risk/dependency and executed
one phase at a time. This entry covers Phase 1, the only phase with no
new control-file/engine surface to verify.

Problems fixed:
- The center tabs only ever showed a static "Welcome to GENESIS Studio"
  label or one open project at a time -- no visibility into any other
  project's existence or status without reopening it. Added
  `ui/dashboard.py`'s `ProjectDashboard`: a table over
  `Settings.recent_projects` showing name/model type/last run
  status/last-modified, colored by status, double-click to open.
- The Projects tree dock (`ui/main_window.py`) only ever held a single
  placeholder item or the one currently-open project -- it now lists
  every recent project (bolded/expanded for whichever one is open),
  double-click opens it, same as the dashboard.
- `MainWindow._on_new_project`'s failure path silently did nothing if
  the freshly created project couldn't be reloaded (`except (OSError,
  ValueError): project = None` then just skip) -- the exact class of
  silent failure this whole roadmap's "workflow clarity" phase exists
  to close. Now shows a `QMessageBox.warning` naming the directory and
  the exception instead.
- Run status changes (`RunTab.runner.status_changed`) now trigger
  `MainWindow.refresh_project_views()` so the dashboard/tree don't go
  stale while a simulation most recently opened is still running.

Design choice: the Dashboard is a permanent tab at index 0, never
removed by `open_project()` (which now only clears tabs *after* it) --
switching projects no longer requires going back through File > Open;
clicking the Dashboard tab is always available.

A project whose `project.json` can't be loaded (moved/deleted folder,
corrupt file) is shown as "missing / unreadable" in both the dashboard
and the tree instead of being silently dropped from the list, so a
vanished project doesn't look like it never existed.

## 2026-09-14 — Run tab could silently sit at "running" with no log/plot

Reported symptom: "the status is running, but there is no plot, no log
whatsoever seen in GUI." `SimulationRunner.start()` (`app/runner.py`)
launches the real job backgrounded (`setsid bash -c '...' < /dev/null &`)
and immediately reports `status_changed("running")` -- there is no
synchronous way to know whether `mpirun`/GENESIS actually started.
`poll()` then just tails `run.log` and checks `run.pgid`; if GENESIS
crashes before writing either (most likely: the exact same "Open_file>
File ... already exists" crash already proven for benchmark presets
below, but here against a leftover `{project.name}.rst`/`.pdb`/`.dcd`
from a previous attempt in the same project directory), both stay empty
forever and the tab sits at "running" with zero feedback -- matching the
report exactly.

Two fixes, both in `app/runner.py`:

1. `start(is_continuation=False)` now calls `_cleanup_previous_outputs()`
   first, which `rm -f`s `{project.name}.pdb`/`.dcd` unconditionally and
   `{project.name}.rst` only for a *fresh* (non-continuation) start --
   a continuation run needs its own `.rst` as `[INPUT]`, so cleanup must
   not destroy the very file "Continue from restart file" resumes from.
   `ui/tab_run.py` threads `is_continuation` through `_on_start` (False)
   and `_on_continue` (True) via a shared `_start_run()` helper.
2. `poll()` now tracks `_stalled_poll_count`: it increments only while
   *both* `run.log` has produced no new text *and* `run.pgid` has never
   been read (`self._pgid is None`), and resets to 0 the moment either
   condition clears. After `MAX_STALLED_POLLS = 5` (~10s at the default
   2s interval) it stops the timer, sets `last_run_status = "failed"`,
   and emits an actionable `error_detected` message telling the user to
   check the project folder for a leftover restart file. `tab_run.py`'s
   `_on_status_changed` already treated `"failed"` the same as
   `"finished"` for re-enabling Start/disabling Stop.

Not yet confirmed against the user's actual project directory whether a
leftover `.rst` is the real root cause here (vs. some other immediate
launch failure) -- the fix is safe/correct either way (cleanup before a
fresh start is always correct, and surfacing a stalled launch instead of
silence is always an improvement), but the specific root cause for this
report is still unverified.

## 2026-09-14 — "View structure in VMD" added to the Files tab

The only existing VMD hook (Analysis tab's "Open in VMD") loads the
trajectory (`{project}.dcd`), which only exists after a run. There was no
way to eyeball the generated structure itself right after project
creation, before running anything -- a real gap noticed while explaining
where VMD lives in the GUI.

Added a "View structure in VMD" button to the Files tab's top row
(`ui/tab_files.py`), independent of the file list selection. It globs
`{project.name}*.pdb` first, falling back to `{project.name}*.gro` --
naming differs by which pipeline built it (`cg_protein_structure_
builder.jl` for sequence input writes `{name}_cg.pdb`; `aa_2_cg.jl`'s
`--cgpdb` flag for PDB input writes `{name}.pdb`), and `.pdb` is
preferred since VMD reads it natively without needing to guess
connectivity. Mirrors the Analysis tab's existing VMD-launch pattern
(check `settings.vmd_path` exists, `subprocess.Popen`, report failures
rather than silently doing nothing).

## 2026-09-14 — Benchmark presets collided on shared output filenames

Real progress worth noting: the 4x4 preset in a benchmark sweep actually
completed a full short simulation successfully (first fully-successful
real GENESIS run this whole debugging session). The next preset (8x2)
then failed:

```
[STEP5] Perform Molecular Dynamics Simulation
Open_file> File benchmark.rst already exists  rank_no = 0
```

Root cause: `_run_one_preset` (`app/benchmark.py`) used a fixed
`output_prefix="benchmark"` (and fixed `benchmark.inp`/`.log`/`.pgid`
filenames) for *every* preset in the sweep. GENESIS refuses to silently
overwrite an existing restart file, so the first successful preset's
`benchmark.rst` blocked every preset that ran after it.

Fixed by tagging every preset's files with its own `ranks`/`threads`
(`benchmark_4x4.inp`, `benchmark_8x2.rst`, etc.) instead of one shared
name. Also added an explicit `rm -f` of that preset's own output files
before running it, even though the tag is now unique per preset within
one sweep -- without this, simply re-running the benchmark a second time
on the same project would hit the identical collision against the
*previous run's* leftover files for that same tag.

## 2026-09-14 — The sequence-input pipeline was using the wrong tool entirely

Every fix so far this session (VVER_CG, CRLF/`;`, `--use-safe-dihedral`)
patched a real bug on a pipeline that was, at a deeper level, never the
right approach to begin with. Asked directly why topology generation
"isn't working for our case" when the tutorial's own sequence-to-topology
step works fine by hand, and re-read tutorial 11.4 (FUS condensate, HPS
model) specifically for how it gets from a bare sequence to a structure:

> "Unlike the normal way to get 'native' information from available PDB
> structures, we don't have any reference structure for IDRs. Therefore,
> we will generate a straight initial conformation for the IDR... we use
> the GENESIS-CG-tool to create an artificial structure and topology
> files from this sequence:
> `tools/modeling/protein_artifact/cg_protein_structure_builder.jl`"

This is a **separate, dedicated script** from `aa_2_cg.jl` -- it takes a
FASTA sequence directly and writes CG topology/coordinate files itself,
with no atomistic PDB intermediate at all. The app's old sequence
pipeline (`generate_extended_chain_pdb` + `build_hps_sequence_commands`
+ `inject_idr_hps_region`) instead fabricated a fake CA-only PDB locally
and pushed it through `aa_2_cg.jl` -- the tool for converting a *real*
all-heavy-atom structure (confirmed 2026-09-09 from genesis_cg_tool's own
wiki: a CA-only trace was never sufficient input to it). That workaround
was invented because this project didn't know the real tool existed, not
because the real tool doesn't exist. Every `--use-safe-dihedral`-style
bug found on this path was a real, independently-confirmed fix, but it
was fixing symptoms on the wrong pipeline.

Also found while confirming this: the condensate/multi-chain step in the
same tutorial does **not** use `aa_2_cg.jl` or local replication math
either -- it uses another dedicated tool,
`tools/modeling/duplication_modeling/duplication_generator.jl`, which
takes the single-chain `.top`/`.gro` and replicates it via `--nx/--ny/--nz`
grid dimensions (real example: `--nx 2 --ny 2 --nz 30` for a 120-copy FUS
droplet). This directly replaces `build_slab_system`, the local Python
coordinate-math replication this app had implemented for the same
undocumented-sounding reason ("no genesis_cg_tool flag for this was
found" -- true of `aa_2_cg.jl`, false of genesis_cg_tool as a whole,
which ships a purpose-built tool for it).

### What changed (`app/cgtool.py`, `app/project_creation.py`)

Confirmed byte-exact against two independent fetches of tutorial 11.4
(after the `WebFetch` summarizer's earlier `VVER_CG` slip taught the
lesson to double-check):

```
cg_protein_structure_builder.jl -s fus.fasta
duplication_generator.jl -t fus_cg.top -c fus_single.gro -o fus_cg --nx 2 --ny 2 --nz 30
```

Both are invoked **without** a `julia` prefix (unlike `aa_2_cg.jl`,
which the wiki's own examples always show as `julia src/aa_2_cg.jl ...`)
-- presumably these are directly-executable scripts with their own
shebang; matched exactly as shown rather than guessed at.

Removed entirely, per the explicit instruction not to leave the old
workaround in place: `generate_extended_chain_pdb`,
`build_hps_sequence_commands`, `inject_idr_hps_region`,
`build_slab_system`, `_parse_gro_xyz`, `_residue_count`,
`set_molecule_count_in_top`, `CA_CA_DISTANCE_NM/ANGSTROM`,
`_ONE_TO_THREE`. `build_aicg2p_command` (the real-PDB path) is untouched
-- it was never the broken piece.

Added: `build_fasta_text` (the `-s` input GENESIS-CG-tool expects,
confirmed format `>header\nSEQUENCE\n` from the tutorial's own FASTA
example), `build_structure_builder_command`, `build_duplication_command`.
`create_project_files` now writes a `.fasta` for sequence-mode input
instead of a fake `.pdb`. `run_cg_tool_pipeline` no longer has a
post-hoc "inject HPS region" step (the real tool already writes that
itself -- the tutorial shows no separate step for it either) or a
post-hoc "replicate in Python" step; the condensate case now renames the
single-chain `.gro` out of the way, calls `duplication_generator.jl`,
then deletes the temporary rename target so later glob-based file lookups
(`{project.name}*.gro`) can't pick up the stale single-chain file instead
of the replicated one.

### What's simplified, not fully matched

This app exposes one scalar "copy count" to the user, not the real
tool's independent `--nx/--ny/--nz` grid. All copies are placed along a
single axis (`--nx 1 --ny 1 --nz n_copies`) to match the previous
single-axis "slab" design intent, not the tutorial's own denser 2x2x30
grid. Exposing nx/ny/nz separately in the wizard UI is a reasonable
follow-up if a denser/more realistic condensate packing matters, not
done here since it wasn't asked and would need new UI, not just a
`cgtool.py` change.

### Still unverified

Whether `cg_protein_structure_builder.jl`'s dihedral output has the same
`--use-safe-dihedral`-style version sensitivity `aa_2_cg.jl` did --
it takes no such flag (confirmed: "no ... flags are shown" beyond `-s`
in the tutorial), so if its output hits an analogous "unsupported
function type" on this installed GENESIS, there's no flag-based fix
available the way there was for `aa_2_cg.jl`; would need investigating
fresh if it comes up.

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
