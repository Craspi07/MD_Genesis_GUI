# Conventions for GENESIS Studio

- Python 3.12, venv at `.venv`; always `pip install -r requirements.txt` after changing deps.
- PyQt5 only; no PySide, no web views.
- All subprocess calls go through `app/wsl.py` (`WslBridge`); every `wsl.exe` call sets
  `WSL_UTF8=1` in the child environment.
- Long-running WSL jobs (simulations, CG-tool conversions, analysis tools) write to a log
  file inside the project directory and are tailed on a `QTimer`; never rely on piped stdout
  for live output (Fortran stdout is block-buffered under a pipe — see `runner.py` docstring).
- Jobs are launched with `setsid` so they own a process group, and are stopped by sending
  signals to that process group (`kill -TERM -- -<pgid>`, escalating to `-KILL` after a grace
  period) — never `pkill -f <binary>`.
- Never read trajectory files (`.dcd`, `.gro` frames, anything large) across the `\\wsl$`
  boundary from the Windows side; only small text outputs. VMD launching is the one exception
  (VMD itself reads across the boundary).
- Never block the GUI thread for more than ~100 ms. Subprocesses go through `QProcess`;
  CPU-bound Python work goes through `QThread`/`QRunnable`.
- Every GENESIS control-file keyword and every CG-tool command-line flag written by this
  codebase must have a citation comment pointing to the docs/tutorial/wiki page it came from,
  or be marked `# VERIFY` if it could not be confirmed against the real docs. See
  `DECISIONS.md` for what's currently unverified and why.
- Tests live in `tests/`, run with `pytest -q`. Parsers (`log_parser.py`, PDB/sequence
  validators, control-file round-trip) must have fixture-based tests under `tests/fixtures/`.
- Log every non-trivial design choice in `DECISIONS.md` — don't silently change a default or
  reinterpret a spec requirement.
- Prefer showing complete files over fragments/diffs when presenting code.
- `WslBridge` is the only module allowed to invoke `wsl.exe`; everything else calls the
  bridge, so subprocess quoting/escaping stays in one place and is mockable in tests.
