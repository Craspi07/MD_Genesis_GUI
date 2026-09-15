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

## Phase 3 — Structural restraints & advanced ensembles
Extends control-file templates: `[RESTRAINTS]` (positional/distance/
dihedral), NPT/NPAT ensemble options, membrane-aware boundary settings.
Needed before Phase 5's all-atom work reuses the same machinery.
- [ ] `[SELECTION]`/`[RESTRAINTS]` sections for positional/distance/
      dihedral restraints, exposed as an optional wizard page.
- [ ] NPT/NPAT ensemble choice (currently NVT-only via Langevin) where
      the underlying model supports it.
- [ ] `# VERIFY`-marked membrane/PBC box options for future membrane
      protein support.

## Phase 4 — Enhanced sampling (REMD / GaMD)
Layered on top of whatever ensembles exist from Phase 3.
- [ ] `[REMD]` control-file section + multi-replica job launch/monitor
      (runner.py needs to manage N processes instead of 1 — real
      architecture change, not just a template addition).
- [ ] GaMD control-file section for existing CG (and later AA) models.
- [ ] Run tab / dashboard support for viewing per-replica status.

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
