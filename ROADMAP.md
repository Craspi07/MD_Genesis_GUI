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

## Phase 5 — All-atom MD pipeline
The big one: CHARMM/AMBER force fields, solvation + ion placement,
real all-atom protein (and protein-complex/homo-oligomer) MD via
`atdyn`/`spdyn`, as a genuine second pipeline alongside the existing CG
one (not a replacement).
- [ ] New `ModelType` values (e.g. `ALL_ATOM`) and a parallel
      `resources/templates/all_atom.j2`.
- [ ] Solvation/ionization step (either shelling out to a real tool the
      way `genesis_cg_tool` is driven now, or documenting what the user
      must pre-process, per the earlier PDB-cleaning discussion).
- [ ] Multi-chain/homo-oligomer AA setup (N copies of one chain,
      symmetric or independent).
- [ ] Engine-conditional keyword handling the same way CG's
      `VVER`/`VVER_CG` split was handled.

## Phase 6 — Visual/plotting upgrade
Once Phases 2-5 produce more kinds of data (per-replica, per-restraint,
per-analysis-tool), upgrade `ui/widgets/mpl_canvas.py` from a single
energy/temperature plot to multi-panel, zoomable, exportable plots
reused across Run/Analysis/dashboard.
- [ ] Multi-panel layout (energy, temperature, restraints, replica
      exchange acceptance, etc. as separate panels, one canvas).
- [ ] Zoom/pan + PNG/CSV export.
- [ ] Reused by Phase 2's analysis plots and Phase 4's per-replica view.

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
