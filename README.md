# GENESIS Studio

A Windows desktop GUI (PyQt5) for setting up, running, monitoring, and
analyzing coarse-grained (CG) molecular dynamics simulations with the
[GENESIS](https://www.r-ccs.riken.jp/labs/cbrt/) 2.1.6 MD package. GENESIS
itself runs inside WSL2; the GUI drives it entirely through `wsl.exe` — no
terminal use is required day-to-day.

**⚠ Read this before a real run:** significant parts of this codebase were
written in a sandboxed environment that could not reach `mdgenesis.org`
(blocked by network egress) and could only partially load the
`genesis_cg_tool` GitHub wiki. Every GENESIS control-file keyword and
CG-tool flag that couldn't be confirmed against the real docs is marked
`# VERIFY` in the generated files and in the source (see `CLAUDE.md`).
**Full details of what's unverified and why, plus the design decisions
that follow from it, are in [`DECISIONS.md`](DECISIONS.md) — read it
before trusting a generated control file or CG-tool command for a
production run.**

## Requirements

- Windows 11 with WSL2 installed, distro `Ubuntu-24.04` (or any distro —
  configurable in first-run setup).
- Inside that WSL distro: GENESIS 2.1.6 (`atdyn`/`cgdyn` under
  `~/genesis-cpu/bin`, `spdyn` under `~/genesis-gpu/bin`), OpenMPI
  (`mpirun`), Julia via juliaup, and `genesis_cg_tool` cloned at
  `~/genesis_cg_tool`.
- Python 3.12 on the Windows side, for the GUI itself.
- (Optional) VMD, for the "Open in VMD" button in the Analysis tab.

## Install

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Run it with:

```
python main.py
```

Whenever `requirements.txt` changes, re-run `pip install -r requirements.txt`
inside the venv.

## First run

1. Launch the app; open **Tools > Health Check...** (or it will prompt on
   first launch).
2. Pick your WSL distro (Detect installed distros button lists what's
   available) and enter your Linux username.
3. Click **Run health check**. It verifies, using the exact same
   `wsl.exe -d <distro> -- bash -lc "..."` invocation a real job uses, that:
   WSL2 is running, GPUs are visible (`nvidia-smi`), `mpirun` is on PATH,
   `atdyn`/`cgdyn`/`spdyn`/`julia` are on PATH, `genesis_cg_tool`'s
   `aa_2_cg.jl --help` runs (this **precompiles Julia packages on first
   use and can take 30–90 seconds** — that's expected, not a hang), and
   `~/genesis_projects` is writable.
4. Fix any red rows using the inline hints, then click Save.

## Basic workflow

1. **File > New Project** (Ctrl+N) opens the wizard:
   - **Input**: drag in a `.pdb`/`.cif`, or switch to **Sequence** mode and
     paste an amino-acid sequence (only offered for disordered/HPS models).
   - **Model**: pick a plain-language card — Folded protein (AICG2+),
     Disordered protein/IDR (HPS), Condensate/phase separation (HPS,
     many copies, slab), or Protein-DNA (advanced). Cards that don't match
     your input (e.g. AICG2+ without a real structure) are greyed out.
   - **Parameters**: temperature, steps, timestep, output frequency,
     friction, box size, copy count (condensate mode). Defaults come from
     `resources/presets/model_defaults.json`.
   - **Resources**: engine is auto-picked (`atdyn` for a small single
     chain, `cgdyn` otherwise/always for condensate) with MPI×OMP presets
     that multiply to your core count; the exact `setsid`/`mpirun`
     wrapper that will be launched is shown before you commit to it.
   - **Review**: enter a project name and click **Create Project**. This
     runs the CG-tool conversion pipeline inside WSL in the background and
     generates the GENESIS control file.
2. The **Files** tab lists every generated file; `run.inp` is editable —
   edits are preserved across regeneration unless you explicitly click
   Regenerate.
3. The **Run** tab starts/stops the simulation (F5/Esc), tails `run.log`
   on a timer (never via piped stdout — GENESIS's Fortran output is
   block-buffered when piped, so a naive pipe would show nothing until
   the run ends), and plots energy/temperature live. Closing and
   reopening the app reattaches to a still-running job.
4. The **Analysis** tab runs GENESIS's own `*_analysis` tools (RMSD, Rg,
   Q-value, contact maps, density profile for condensate mode), plots the
   results, and exports everything to one Excel workbook.
5. **Tools > Benchmark...** times a short 2000-step run at a few MPI×OMP
   splits and can apply the fastest to the project. **Run > Queue
   Projects...** runs several projects sequentially or two at once (each
   halving its core request).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Health check row "WSL2 running" fails | Start Ubuntu once from the Start menu, then retry. |
| `mpirun` reports "not enough slots" | The Run tab retries automatically with `--oversubscribe` — this is expected under WSL2, which has no real network fabric for MPI. |
| Health check hangs on the CG-tool row | Expected on first use — Julia is precompiling packages (30–90s). Let it finish once; later runs are fast. |
| Nothing shows up in the Run tab's log | Confirm the project directory is under `~/genesis_projects` inside WSL, not somewhere only reachable via `\\wsl$` with slow 9P I/O for large files. |
| "Open in VMD" does nothing | Set the correct VMD path in Settings; default is `C:\Program Files\University of Illinois\VMD\vmd.exe`. |
| A generated control file looks wrong | It's probably one of the `# VERIFY` keywords — see `DECISIONS.md` and cross-check against the real `mdgenesis.org` docs before running. |

## Development

```
pip install -r requirements.txt
pytest -q
```

Tests run entirely headless (`QT_QPA_PLATFORM=offscreen`, set automatically
by `tests/conftest.py`) and never require a real WSL install — `app/wsl.py`
is tested against a fake `wsl.exe` shim at `tests/fixtures/fake_wsl.py`.
See `CLAUDE.md` for the project's coding conventions and `DECISIONS.md` for
the running log of design choices (including everything this session
couldn't verify against the live GENESIS docs).

### Project layout

```
main.py                  entry point
app/                      non-UI logic (WslBridge, project model, CG-tool
                           pipeline, control-file generation, log parsing,
                           the simulation runner, analysis, benchmark, queue)
ui/                        PyQt5 widgets, dialogs, and the New Project wizard
resources/templates/       Jinja2 control-file templates (one per model)
resources/presets/         JSON parameter defaults per model
tests/                     pytest suite, with fixtures/ holding the fake
                           wsl.exe shim and a sample GENESIS log
```

### Packaging (optional)

A one-folder PyInstaller build is a reasonable way to distribute this
without asking users to set up Python:

```
pyinstaller --name GenesisStudio --onedir --windowed main.py
```

This hasn't been exercised in this dev environment (no Windows available)
— treat it as a starting point, not a verified build recipe.

## Known gaps against the full spec

- **GENESIS control-file and CG-tool exact keywords**: unverified this
  session (see above and `DECISIONS.md`). Re-verify against
  `mdgenesis.org` before a production run.
- **HPS-from-sequence and condensate/slab generation**: as of 2026-09-14
  these use genesis_cg_tool's own dedicated tools --
  `cg_protein_structure_builder.jl` (sequence -> artificial IDR structure
  + CG topology) and `duplication_generator.jl` (N-copy slab
  replication) -- confirmed against mdgenesis.org tutorial 11.4 (FUS/HPS
  model), replacing an earlier from-scratch Python reimplementation. See
  `DECISIONS.md` for the full writeup, including one known simplification
  (copies are placed along a single axis, not the 3D grid the real tool
  also supports).
- **End-to-end verification on real hardware**: this dev environment has
  no Windows, no WSL, and no GENESIS install, so nothing here has been run
  against a real simulation. Every module that would normally touch
  `wsl.exe` is tested against a fake shim instead — see `DECISIONS.md`.
  The health check, a real `New Project` run, and a live Run-tab plot
  update all need to be exercised on the target machine before relying on
  this for real work.
