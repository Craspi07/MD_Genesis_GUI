# GENESIS Studio Roadmap

Multi-pass plan to grow this GUI from "CG-only, one project at a time"
toward covering GENESIS's real feature set, executed one phase at a
time. Each phase: verify every new control-file keyword/CLI flag
against real mdgenesis.org/genesis_cg_tool docs (citation comment or
`# VERIFY`, per CLAUDE.md) before wiring it into a template, add
fixture-based tests, log the decisions in `DECISIONS.md`, commit, push.
No real GENESIS/Julia binaries are installed in this container, so
verification here is doc/wiki-based, not `-h ctrl_all`-based; anything
that can't be confirmed against the real docs gets `# VERIFY` and stays
flagged until it's checked against the user's real install, exactly as
established earlier this session.

Status legend: `[ ]` not started, `[~]` in progress, `[x]` done.

## Phase 1 — Multi-project dashboard + workflow clarity [x] done 2026-09-15
CG-only, no new engine surface. Turns the current placeholder project
tree + single-project-at-a-time window into a real home screen.
- [x] Welcome tab replaced with a project dashboard: every recent
      project (from `Settings.recent_projects`) shown with name, model
      type, last run status, last-modified time; double-click to open.
- [x] Project tree dock mirrors the same list (not just the currently
      open project) with a status icon/color per project.
- [x] "Remove from list" / "Open containing folder" actions on the
      dashboard.
- [x] (2026-09-16) "Delete..." / "Rename..." actions on the dashboard --
      delete permanently removes the project directory (confirmed,
      blocked while a run is in progress); rename does a full WSL
      directory + prefixed-generated-file rename with `run.inp`
      regenerated to match. See `DECISIONS.md`.
- [x] Closed one concrete silent-failure gap (`_on_new_project` no
      longer no-ops on a load failure). Broader "every WslBridge failure
      gets a consistent message" audit deferred -- not scoped tightly
      enough to do safely in this pass; revisit if a specific silent
      failure gets reported, the same way runner.py's stalled-poll fix
      started from a real bug report rather than a speculative sweep.

## Phase 2 — Deeper analysis suite [x] done 2026-09-15
CG-only still. RMSD/Rg/Q-value/contact-map/density were already present
before this roadmap; this phase added the two genuinely missing tools.
- [x] RMSD, Rg, Q-value, contact map -- already existed, unchanged.
- [x] RMSF, via GENESIS's real two-tool pipeline (`avecrd_analysis` ->
      `flccrd_analysis`), gated on a real `.psf`/`.pdb` existing in the
      project directory rather than guessed by model type (see
      DECISIONS.md -- only genesis_cg_tool's sequence/HPS pipeline is
      confirmed to write a `.psf`; the PDB-input/AICG2+ pipeline is not).
- [x] SASA, via `sasa_analysis`, gated the same way plus a required
      `Settings.sasa_radius_file` (no guessable default -- see
      DECISIONS.md) the user must point at a real radius-definition
      file.
- [ ] Per-tool result plotting still single-panel (existing `MplCanvas`)
      -- multi-panel/zoom/export deferred to Phase 6 as planned.

## Phase 3 — Structural restraints & advanced ensembles [x] done 2026-09-16
Extends control-file templates directly -- the highest-risk phase so
far, verified against GENESIS's own official User Guide PDF (v2.0.0,
fetched live) rather than tutorial pages, since restraints/ensembles
aren't tutorial-specific.
- [x] `[SELECTION]`/`[RESTRAINTS]` section for positional (`POSI`)
      restraints, wired to the wizard's "Apply position restraints"
      checkbox -- which existed in the UI since before this roadmap but
      was never actually consumed by control_file.py (a real dead
      control, now fixed). Distance/dihedral restraints are documented
      (User Guide Sec. 13.1) but not exposed in the UI yet -- POSI was
      the one the app already had a UI affordance for; the others are a
      natural follow-up, not implemented speculatively.
- [x] NPT ensemble choice, gated to model types that actually have a
      periodic box (`MODEL_TYPES_REQUIRING_BOX` -- AICG2P,
      HPS_CONDENSATE); `render_control_file` now raises if NPT is
      requested for a NOBC model type instead of silently emitting an
      unusable file. NPAT/NPgT deliberately not implemented -- both are
      membrane-specific (isotropy=XY-FIXED / SEMI-ISO) and this app has
      no membrane/lipid support to exercise them against, so adding
      them now would be untestable guessing.
- [ ] Membrane/PBC options for future membrane protein support --
      deferred; no membrane CG force field exists in this app yet, so
      there's nothing to attach boundary options to (would be Phase 5+
      scope, not this phase's).

## Phase 4 — Enhanced sampling (REMD / GaMD) [x] done 2026-09-16
Corrected assumption from the original write-up: REMD does **not**
need runner.py to manage N processes. GENESIS User Guide 2.0.0 Ch. 15
confirms REMD is one `mpirun` launch of the same binary with more total
ranks (ranks-per-replica x n_replicas) -- GENESIS's own `[REMD]` section
tells it how to partition those ranks into replicas internally. So this
phase reused the existing single-launch machinery instead of a new
architecture.
- [x] `[REMD]` control-file section (T-REMD: temperature exchange only
      -- REUS/gREST/multi-dimensional REMD documented in the User Guide
      but not exposed, to keep the wizard's temperature-list UI simple
      and avoid guessing a collective-variable UI that has no use case
      in this app yet) + `runner.py`'s `build_wrapper_script` scaling
      `-np` by replica count; `_cleanup_previous_outputs` extended to
      glob `_rep*` per-replica output files.
- [x] `[GAMD]` control-file section (`boost_type = POTENTIAL` only --
      DUAL/DIHEDRAL need a `sigma0_dih` default this app couldn't
      confirm, so they're not offered rather than guessed), gated with
      a `# VERIFY` note when the engine isn't atdyn (the User Guide's
      own regression tests only name `test_gamd_atdyn`/`test_gamd_spdyn`,
      not cgdyn).
- [ ] Run tab / dashboard support for viewing per-replica status --
      deferred. Each replica does get its own `logfile`/`dcdfile` (Sec.
      5.2), so this is now plumbable, but parsing real REMD stdout to
      confirm the standard-output format `GenesisLogParser` would need
      to keep working hasn't been verified against a real run yet.

## Phase 5 — All-atom MD pipeline [x] done 2026-09-16 (control-file layer + wizard integration)
The big one, and the one that most changed shape once actually
researched. GENESIS User Guide 2.0.0 Sec. 4.1 confirms GENESIS itself
never builds atomistic systems (adding missing atoms/H, solvating,
placing ions) -- that's always done by an external setup tool (VMD/
PSFGEN, CHARMM-GUI, or CHARMM for the CHARMM force field; LEaP for
AMBER), the exact same relationship this app already has with
`genesis_cg_tool` for CG models. So "the all-atom pipeline" isn't a
system-building pipeline this app runs -- it's control-file generation
for a system the user already built elsewhere, same shape as every CG
model type, just with CHARMM's real [INPUT]/[ENERGY]/[CONSTRAINTS]
keywords instead of RESIDCG's.
- [x] New `ModelType.ALL_ATOM_CHARMM` + `resources/templates/
      all_atom_charmm.j2` (deliberately NOT built on `_common_sections.
      j2`, which is entirely CG-specific -- VVER_CG, rigid_bond=NO,
      CG-scale timesteps). Confirmed real CHARMM-force-field defaults
      (User Guide Ch. 4/6/9): `topfile`/`parfile`/`strfile`/`psffile`/
      `pdbfile` in `[INPUT]`, `electrostatic=PME`/`switchdist=10.0`/
      `cutoffdist=12.0`/`pairlistdist=13.5`/`vdw_force_switch=YES` in
      `[ENERGY]`, `rigid_bond=YES`/`fast_water=YES` (SHAKE+SETTLE) in
      `[CONSTRAINTS]`, plain `VVER` integrator (not this app's CG-only
      `VVER_CG`) -- and because it's plain ATDYN `VVER`, Phase 3/4's
      NPT/restraints support apply to it with no `# VERIFY` caveat,
      unlike CG's `VVER_CG`/cgdyn uncertainty.
- [x] `render_control_file` rejects `ALL_ATOM_CHARMM` without all four
      required input files, and without a box (PME needs one) --
      same "raise instead of guess" pattern as Phase 3's NPT/NOBC guard.
- [x] **Wizard/project-creation integration** (added 2026-09-16, after
      being flagged as the obvious next step and then explicitly
      requested). The Input page gained a third mode, "Pre-built
      all-atom system (CHARMM)"; picking it routes through a dedicated
      All-Atom Files page (file pickers for topfile(s)/parfile(s)/
      optional strfile(s)/psffile/pdbfile + box x/y/z) instead of the
      CG PDB/sequence page, via `NewProjectWizard.nextId()`; the Model
      page then only offers the "All-atom (CHARMM)" card. `app/
      project_creation.py` gained `copy_all_atom_files()` (same
      copy-into-project-dir-then-reference-by-basename pattern as PDB
      mode) and a shared `build_control_file_config()` used by both a
      fresh project and a benchmark sweep. The engine picker is locked
      to atdyn for this model type (cgdyn is CG-only -- no CHARMM/PME
      support). `[REMD]`/`[GAMD]` sections were factored out of
      `_common_sections.j2` into a shared `_remd_gamd_sections.j2` so
      all-atom mode gets the same REMD/GaMD support Phase 4 built for
      CG, instead of silently dropping those settings if a user enabled
      them before switching to all-atom mode -- a real gap this
      integration pass caught and closed, not merely UI wiring.
      `ui/tab_run.py`'s "Continue from restart file" and
      `app/benchmark.py`'s benchmark sweep both used to hardcode the
      CG-shaped half of control-file generation inline and would have
      broken (or, for benchmarking, refused to run at all) for an
      all-atom project; both now go through the same shared
      `build_control_file_config()` all model types use.
- [x] **Two real correctness bugs found and fixed** (2026-09-16) by
      cloning and diffing against the real `genesis_tutorial_materials`
      GitHub repo (GENESIS's own team's tutorial-3.3, PDB 2QMT) rather
      than guessing what a "validation protein" should look like:
      (1) the POSI restraint selection was `group1 = all`, restraining
      solvent along with the protein and defeating equilibration's
      purpose -- fixed to protein backbone only; (2) there was no
      energy-minimization stage before MD, a real common cause of a
      first-few-steps blow-up on a freshly solvated system -- fixed
      with a new `all_atom_minimize.j2` template + `app/
      project_creation.py`'s `run_minimization()`, run automatically
      (no new checkbox) before every all-atom project's main `run.inp`
      is generated. See DECISIONS.md for the full diff against the real
      reference, including what already matched with no changes needed.
- [x] **Import a CHARMM-GUI archive (.tgz) directly** (2026-09-17, revised
      same day after a real-usage bug report -- see DECISIONS.md for
      both the original design and the correction). Windows can't open
      a .tgz natively, so this was a real workflow blocker for the most
      common way to prepare an all-atom system. New `app/charmm_gui_
      import.py` extracts the archive with Python's own `tarfile` (no
      WSL involved -- this needed a decompressor, not a Linux shell)
      into a temp folder, auto-detects the final `stepN_input.psf`/
      `.pdb` pair Solution/Membrane Builder writes and the box size from
      that PDB's own `CRYST1` record (standard PDB format, not CHARMM-
      GUI-specific), and points the existing topology/parameter/stream
      file pickers at the extracted `toppar/` folder rather than
      guessing which of its 40+ bundled files a given system needs.
      Wired into the All-Atom Files wizard page as an "Import from
      CHARMM-GUI archive..." button, on a `QThread` with the same
      exception-safety guard every other worker in this codebase has
      (a missing one crashed the app on the first real-world try).
- [ ] AMBER (`prmtopfile`/`ambcrdfile`) and multi-chain/homo-oligomer AA
      setup (N copies of one prepared chain) -- documented in the User
      Guide (Ch. 4.1.2) but not implemented; homo-oligomer AA setup
      also depends on the external setup tool (e.g. CHARMM-GUI's own
      "Multimer" builder), same as single-chain AA does.
- [ ] Analysis tab's RMSD/Rg/Q-value/contact-map tools (`app/analysis.
      py`) still only generate `grotopfile`/`grocrdfile` (GROMACS)
      `[INPUT]` sections -- not yet updated to use `psffile`/`pdbfile`
      for an all-atom project, so those buttons would currently produce
      a wrong/unusable analysis control file for an ALL_ATOM_CHARMM
      project. A real, scoped gap, not attempted in this pass.

## Phase 6 — Visual/plotting upgrade [x] done 2026-09-16
No new GENESIS keywords to verify -- this phase is pure UI/UX, and the
one concrete plotting bug it fixes was found by actually looking at
what the Run tab's plot does, not speculated in advance.
- [x] Fixed a real bug: the Run tab's and Analysis tab's "temperature/
      energy over time" plots put TEMPERATURE (~hundreds of K) on the
      same y-axis as energy terms (often thousands of kcal/mol) --
      temperature's own variation was effectively invisible next to
      energy's much larger scale. `ui/widgets/mpl_canvas.py`'s
      `MplCanvas.set_series` now takes an `axis="secondary"` option
      (a lazily-created `twinx()` axis with its own label and a combined
      legend), used for TEMPERATURE in both `ui/tab_run.py` and
      `ui/tab_analysis.py`.
- [x] Zoom/pan/save, via matplotlib's own `NavigationToolbar2QT` --
      already ships with the `matplotlib` dependency this app already
      has (no new dependency), added above the canvas in both the Run
      and Analysis tabs.
- [x] CSV export (`app/csv_export.py`), alongside the existing Excel
      export -- one CSV file per accumulated series/matrix (CSV has no
      "sheets" the way the Excel workbook does), reusing the same
      `AnalysisSeries`/`AnalysisMatrix` dataclasses so no new analysis-
      result representation was needed.
- [ ] True multi-panel (stacked subplots for e.g. per-replica REMD
      status) not implemented -- deferred along with Phase 4's own
      "per-replica status" item, since REMD's real stdout output format
      still isn't verified against an actual run (see Phase 4 notes),
      and building a multi-panel layout for data this app can't yet
      parse would be speculative.

## Sequencing note
Phases are ordered by risk/dependency, not strictly by the order
features were requested: dashboard first because it's fast and lowers
risk on everything after it (better error visibility while more moving
parts get added), analysis suite second because it has no new
control-file surface, restraints/ensembles third because Phase 5 needs
that machinery, enhanced sampling fourth because it needs Phase 3's
ensembles, all-atom fifth because it is the largest and riskiest change
and benefits from every pattern established in 1-4, plotting upgrade
last because it's most useful once there's more data to visualize.
