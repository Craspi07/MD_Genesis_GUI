"""WslBridge: the single point of contact with wsl.exe.

Every subprocess call that crosses into WSL goes through this module (see
CLAUDE.md). This keeps quoting/escaping and the UTF-16/UTF-8 decoding
quirks of wsl.exe in one place, and makes the rest of the app mockable in
tests without a real WSL install.
"""
from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Sequence

from PyQt5.QtCore import QObject, QProcess, QProcessEnvironment, pyqtSignal

DEFAULT_WSL_EXE = "wsl.exe"


def decode_wsl_output(data: bytes) -> str:
    """Decode output from wsl.exe.

    `wsl.exe -l -v` and other management subcommands emit UTF-16LE
    regardless of WSL_UTF8 (a long-standing wsl.exe quirk); decoding that
    as UTF-8 yields null-padded garbage. Detect embedded NUL bytes and
    fall back to utf-16-le in that case; otherwise decode as UTF-8 (which
    is what every command run through `bash -lc` with WSL_UTF8=1 set will
    actually produce).
    """
    if not data:
        return ""
    if b"\x00" in data:
        try:
            return data.decode("utf-16-le", errors="replace").lstrip("﻿")
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass
class TailResult:
    text: str
    offset: int


@dataclass
class HealthCheckItem:
    name: str
    ok: bool
    detail: str
    fix_hint: str = ""


class WslBridge:
    """The only module allowed to invoke wsl.exe.

    `wsl_exe` is overridable (used by tests to point at a fake shim
    standing in for the real Windows executable, since this codebase is
    also developed/tested on non-Windows hosts).
    """

    def __init__(self, distro: str = "Ubuntu-24.04", wsl_exe: str = DEFAULT_WSL_EXE):
        self.distro = distro
        self.wsl_exe = wsl_exe

    # -- environment -------------------------------------------------------
    def _env(self) -> dict:
        env = os.environ.copy()
        env["WSL_UTF8"] = "1"
        return env

    def _bash_login_argv(self, command: str) -> List[str]:
        # The whole `command` is passed as a single bash -lc argument, not
        # split/re-quoted by us, so callers building `command` must
        # shlex.quote any interpolated values themselves (see wslpath/which
        # /tail below for examples). -l sources ~/.profile -> ~/.bashrc,
        # which is what puts GENESIS/Julia/CUDA on PATH.
        return [self.wsl_exe, "-d", self.distro, "--", "bash", "-lc", command]

    # -- synchronous ---------------------------------------------------------
    def run(self, command: str, timeout: Optional[float] = None) -> CommandResult:
        """Run `command` inside WSL via a login bash shell.

        Uses the exact same invocation shape as real job launches (see
        CLAUDE.md gotcha #7 in the original spec: the health check must use
        the runner's exact shell invocation so a green check guarantees a
        job will find the binaries).
        """
        proc = subprocess.run(
            self._bash_login_argv(command),
            capture_output=True,
            env=self._env(),
            timeout=timeout,
        )
        return CommandResult(
            returncode=proc.returncode,
            stdout=decode_wsl_output(proc.stdout),
            stderr=decode_wsl_output(proc.stderr),
        )

    def run_management(self, argv: Sequence[str], timeout: Optional[float] = None) -> CommandResult:
        """Run a wsl.exe management subcommand directly (e.g. `-l -v`),
        bypassing bash -lc since these aren't Linux commands."""
        proc = subprocess.run(
            [self.wsl_exe, *argv],
            capture_output=True,
            env=self._env(),
            timeout=timeout,
        )
        return CommandResult(
            returncode=proc.returncode,
            stdout=decode_wsl_output(proc.stdout),
            stderr=decode_wsl_output(proc.stderr),
        )

    # -- path helpers ----------------------------------------------------
    def wslpath(self, windows_path: str) -> Optional[str]:
        result = self.run(f"wslpath -a {shlex.quote(windows_path)}")
        if not result.ok:
            return None
        return result.stdout.strip()

    def which(self, name: str) -> Optional[str]:
        result = self.run(f"which {shlex.quote(name)}")
        if not result.ok:
            return None
        path = result.stdout.strip()
        return path or None

    # -- log tailing -------------------------------------------------------
    def tail(self, path: str, offset: int = 0) -> TailResult:
        """Read bytes appended to `path` (inside WSL) since byte `offset`.

        Used to poll run.log / CG-tool / analysis log files on a QTimer
        instead of relying on piped stdout, which is block-buffered for
        Fortran programs and would otherwise deliver no output until a job
        finishes (gotcha #1).
        """
        quoted = shlex.quote(path)
        size_result = self.run(f"stat -c %s {quoted} 2>/dev/null || echo 0")
        try:
            size = int(size_result.stdout.strip() or "0")
        except ValueError:
            size = 0
        if size <= offset:
            return TailResult(text="", offset=offset)
        result = self.run(f"tail -c +{offset + 1} {quoted}")
        return TailResult(text=result.stdout, offset=size)

    # -- async QProcess runner --------------------------------------------
    def run_async(self, command: str, parent: Optional[QObject] = None) -> "AsyncCommand":
        """Short interactive commands only (health check, CG-tool --help).
        Long jobs must redirect to a file and be tailed (see runner.py)."""
        return AsyncCommand(self, command, parent=parent)

    # -- distro discovery ---------------------------------------------------
    def list_distros(self) -> List[str]:
        """Parse `wsl.exe -l -v` into a list of installed distro names."""
        result = self.run_management(["-l", "-v"])
        if not result.ok:
            return []
        names: List[str] = []
        for line in result.stdout.splitlines():
            line = line.strip().lstrip("*").strip()
            if not line or line.upper().startswith("NAME"):
                continue
            name = line.split()[0]
            names.append(name)
        return names

    # -- health check --------------------------------------------------------
    def health_check(self) -> List[HealthCheckItem]:
        items: List[HealthCheckItem] = []

        wsl_running = self.run_management(["-l", "-v"])
        items.append(
            HealthCheckItem(
                name="WSL2 running",
                ok=wsl_running.ok and self.distro in wsl_running.stdout,
                detail=wsl_running.stdout.strip() or wsl_running.stderr.strip(),
                fix_hint="Start Ubuntu once from the Start menu, then retry.",
            )
        )

        gpu = self.run("nvidia-smi -L")
        items.append(
            HealthCheckItem(
                name="GPU visible in WSL (nvidia-smi)",
                ok=gpu.ok and "GPU" in gpu.stdout,
                detail=gpu.stdout.strip() or gpu.stderr.strip(),
                fix_hint="Install/update the NVIDIA driver with WSL support on Windows.",
            )
        )

        mpirun = self.which("mpirun")
        mpi_version = self.run("mpirun --version") if mpirun else None
        items.append(
            HealthCheckItem(
                name="mpirun found",
                ok=mpirun is not None and (mpi_version.ok if mpi_version else False),
                detail=(mpi_version.stdout.splitlines()[0] if mpi_version and mpi_version.ok else (mpirun or "not found on PATH")),
                fix_hint="Check OpenMPI is installed and on PATH via ~/.bashrc.",
            )
        )

        for binary, hint in [
            ("atdyn", "Check ~/genesis-cpu/bin is on PATH in ~/.bashrc."),
            ("cgdyn", "Check ~/genesis-cpu/bin is on PATH in ~/.bashrc."),
            ("spdyn", "Check ~/genesis-gpu/bin is on PATH in ~/.bashrc."),
            ("julia", "Check juliaup's ~/.juliaup/bin is on PATH in ~/.bashrc."),
        ]:
            path = self.which(binary)
            items.append(
                HealthCheckItem(
                    name=f"{binary} found",
                    ok=path is not None,
                    detail=path or "not found on PATH",
                    fix_hint=hint,
                )
            )

        cgtool = self.run("julia ~/genesis_cg_tool/src/aa_2_cg.jl --help", timeout=180)
        items.append(
            HealthCheckItem(
                name="genesis_cg_tool runs (aa_2_cg.jl --help)",
                ok=cgtool.ok,
                detail=(cgtool.stdout or cgtool.stderr).strip()[:300],
                fix_hint="First run precompiles Julia packages and can take 30-90s; retry if it timed out.",
            )
        )

        param_dir = self.run("test -d ~/genesis_cg_tool/param && ls ~/genesis_cg_tool/param")
        items.append(
            HealthCheckItem(
                name="genesis_cg_tool/param present",
                ok=param_dir.ok and bool(param_dir.stdout.strip()),
                detail=param_dir.stdout.strip()[:300] or "~/genesis_cg_tool/param missing or empty",
                fix_hint=(
                    "Generated .top files #include ./param/*.itp -- this directory is "
                    "copied into every new project, and needs to exist under genesis_cg_tool "
                    "for that to work. Re-check your genesis_cg_tool clone."
                ),
            )
        )

        write_check = self.run(
            "mkdir -p ~/genesis_projects && touch ~/genesis_projects/.write_test "
            "&& rm ~/genesis_projects/.write_test && echo OK"
        )
        items.append(
            HealthCheckItem(
                name="~/genesis_projects is writable",
                ok=write_check.ok and "OK" in write_check.stdout,
                detail=write_check.stdout.strip() or write_check.stderr.strip(),
                fix_hint="Check filesystem permissions inside WSL.",
            )
        )

        cores = self.run("nproc")
        ram = self.run("free -g | awk '/^Mem:/{print $2}'")
        items.append(
            HealthCheckItem(
                name="Resources detected",
                ok=cores.ok,
                detail=f"{cores.stdout.strip() or '?'} logical cores, {ram.stdout.strip() or '?'} GB RAM",
            )
        )

        return items


class AsyncCommand(QObject):
    """QProcess-based async runner for one WSL command.

    Emits `line(str)` as stdout/stderr lines arrive and `finished(int)`
    with the exit code. Intended for short interactive commands (health
    check probes, CG-tool --help); long simulation/analysis jobs should be
    launched through runner.py, which redirects to a log file and tails it
    (piped stdout from Fortran binaries is block-buffered and would
    otherwise deliver nothing until the job ends).
    """

    line = pyqtSignal(str)
    finished = pyqtSignal(int)
    errored = pyqtSignal(str)

    def __init__(self, bridge: WslBridge, command: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._bridge = bridge
        self._command = command
        self._process = QProcess(self)
        self._process.setProcessEnvironment(self._qprocess_environment())
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.readyReadStandardError.connect(self._on_stderr)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_error)
        self._buffer = b""

    @staticmethod
    def _qprocess_environment() -> QProcessEnvironment:
        env = QProcessEnvironment.systemEnvironment()
        env.insert("WSL_UTF8", "1")
        return env

    def start(self) -> None:
        argv = self._bridge._bash_login_argv(self._command)
        self._process.start(argv[0], argv[1:])

    def _emit_lines(self, chunk: bytes) -> None:
        self._buffer += chunk
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            self.line.emit(decode_wsl_output(line))

    def _on_stdout(self) -> None:
        self._emit_lines(bytes(self._process.readAllStandardOutput()))

    def _on_stderr(self) -> None:
        self._emit_lines(bytes(self._process.readAllStandardError()))

    def _on_finished(self, exit_code: int, _exit_status) -> None:
        if self._buffer:
            self.line.emit(decode_wsl_output(self._buffer))
            self._buffer = b""
        self.finished.emit(exit_code)

    def _on_error(self, error) -> None:
        self.errored.emit(str(error))

    def kill(self) -> None:
        self._process.kill()
