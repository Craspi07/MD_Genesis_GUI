# Decisions Log

Running log of choices made during development and why. Newest entries at the top.

## 2026-09-09 — Documentation access limitations

This session runs in a sandboxed cloud environment with an egress allowlist.
`mdgenesis.org` (GENESIS usage docs, tutorial 11.1, 11.2, 11.3) is **blocked
entirely** by the network egress proxy — every fetch attempt returned
`EGRESS_BLOCKED`. The GitHub wiki for `genesis_cg_tool` partially renders:
the Home page and two static-file fetches of `Command-Line-Arguments.md` /
`File-formats.md` (via `raw.githubusercontent.com/wiki/...`) worked; the
same pages via the normal `github.com/.../wiki/...` UI returned "error while
loading" (client-side rendering the fetch summarizer can't execute).

**What was verified from the accessible GitHub sources:**
- `aa_2_cg.jl`'s documented flags: `--force-field-protein {AICG2+,Clementi}`,
  `--force-field-DNA 3SPN.2C`, `--force-field-RNA HT`, `--aicg-scale`,
  `--CCGO-contact-scale`, `--respac`, `--protein-DNA-Go`, `--pfm`,
  `--pwmcos[-scale|-shift]`, `--mmCIF`, `--psf`, `--cgpdb`, `--cgconnect`,
  `--output-name`, `--debug`, `--show-sequence`, `-v/--verbose`, `--log`.
  **No HPS/KH flag exists on the script itself**, and **no flag for
  sequence-only input or for generating N copies / a slab box** was found
  anywhere in the accessible docs.
- The `.itp` file format (from `File-formats.md`) documents
  `[ cg_IDR_HPS_region ]` and `[ cg_IDR_KH_region ]` directives, which mark
  a residue range of an already-built molecule as disordered and cite
  Dignon et al., PLoS Comput Biol 14(1), e1005941 (2018) for the HPS model.
  This means HPS/KH is **not** a distinct sequence-to-CG code path — it's a
  post-hoc annotation on a chain that was still built through the normal
  PDB-based `aa_2_cg.jl` pipeline.

**Design decisions that follow from this:**
1. **HPS/IDR single-chain path**: for a user who pastes a sequence with no
   PDB, `cgtool.py` builds an idealized extended-chain PDB from the
   sequence locally (simple internal-coordinate chain builder, no GENESIS
   dependency), runs `aa_2_cg.jl` on that PDB with
   `--force-field-protein AICG2+` (# VERIFY: the base topology builder used
   even for a fully-disordered chain), then rewrites the resulting `.itp`
   to add a `[ cg_IDR_HPS_region ]` block spanning the full sequence and
   swaps in HPS-model params where the CG-tool's own output doesn't already
   do so. This whole path is marked `# VERIFY` in the generated files and
   surfaced as a warning in the UI ("could not confirm this command against
   GENESIS docs — inspect before running").
2. **Condensate / N-copy slab mode**: since no CG-tool flag for replication
   or slab boxes could be found, `cgtool.py` builds a single chain's CG
   topology once via the tool, then **our own Python code** (not GENESIS
   CG-tool) tiles/translates the resulting `.gro` coordinates into an
   elongated box and rewrites the `.top` `[ molecules ]` section with the
   requested multiplicity. This avoids guessing at unverified GENESIS-side
   flags — the replication is plain coordinate/topology math we fully
   control and can unit test.
3. Every keyword and flag actually observed above is cited in generated
   files as `# genesis_cg_tool wiki: Command-Line-Arguments` or similar.
   Anything not observed (AICG2+ control-file keyword values, `atdyn`
   vs `cgdyn` INI keyword names, `[BOUNDARY]`/`[ENSEMBLE]` exact value
   strings) is marked `# VERIFY` per `CLAUDE.md` and flagged in the Files
   tab until a user with real access to mdgenesis.org confirms it.
4. If/when this project is continued from an environment with unblocked
   network access, the first task should be to re-fetch
   `mdgenesis.org/docs/usage/` and tutorials 11.1–11.3 and replace every
   `# VERIFY` marker with a real citation or a corrected value.

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
