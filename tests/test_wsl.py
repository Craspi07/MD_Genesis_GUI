"""Tests for app.wsl.WslBridge against a fake wsl.exe shim (see
tests/fixtures/fake_wsl.py) — this codebase is developed on non-Windows
hosts, so these tests exercise argv construction, quoting, and decoding
without a real WSL install.
"""
import os
from pathlib import Path

import pytest
from PyQt5.QtCore import QEventLoop, QTimer

from app.wsl import WslBridge, decode_wsl_output

FAKE_WSL = str(Path(__file__).parent / "fixtures" / "fake_wsl.py")


@pytest.fixture
def bridge() -> WslBridge:
    return WslBridge(distro="Ubuntu-24.04", wsl_exe=FAKE_WSL)


# -- decoding -----------------------------------------------------------
def test_decode_utf16le_management_output(bridge: WslBridge):
    result = bridge.run_management(["-l", "-v"])
    assert result.ok
    assert "Ubuntu-24.04" in result.stdout
    assert "\x00" not in result.stdout


def test_decode_utf8_plain():
    assert decode_wsl_output("hello".encode("utf-8")) == "hello"


def test_decode_empty():
    assert decode_wsl_output(b"") == ""


# -- run() / environment -------------------------------------------------
def test_run_sets_wsl_utf8(bridge: WslBridge):
    result = bridge.run("echo $WSL_UTF8")
    assert result.ok
    assert result.stdout.strip() == "1"


def test_run_login_shell_expands_variables(bridge: WslBridge):
    result = bridge.run("echo hello world && echo $HOME")
    assert result.ok
    lines = result.stdout.strip().splitlines()
    assert lines[0] == "hello world"
    assert lines[1] == os.environ.get("HOME", lines[1])


def test_run_nonzero_exit(bridge: WslBridge):
    result = bridge.run("exit 7")
    assert not result.ok
    assert result.returncode == 7


# -- quoting: spaces, parens, $ ------------------------------------------
def test_which_and_tail_quote_paths_with_spaces_and_parens(bridge: WslBridge, tmp_path: Path):
    tricky = tmp_path / "my (project) file $var.txt"
    tricky.write_text("line one\nline two\n")

    tail_result = bridge.tail(str(tricky), offset=0)
    assert tail_result.text == "line one\nline two\n"
    assert tail_result.offset == len(tail_result.text.encode())


def test_tail_incremental(bridge: WslBridge, tmp_path: Path):
    f = tmp_path / "run.log"
    f.write_text("first\n")
    first = bridge.tail(str(f), offset=0)
    assert first.text == "first\n"

    with open(f, "a") as fh:
        fh.write("second\n")
    second = bridge.tail(str(f), offset=first.offset)
    assert second.text == "second\n"
    assert second.offset > first.offset


def test_tail_no_new_data_returns_empty(bridge: WslBridge, tmp_path: Path):
    f = tmp_path / "run.log"
    f.write_text("only\n")
    first = bridge.tail(str(f), offset=0)
    second = bridge.tail(str(f), offset=first.offset)
    assert second.text == ""
    assert second.offset == first.offset


def test_which_missing_binary_returns_none(bridge: WslBridge):
    assert bridge.which("definitely-not-a-real-binary-xyz") is None


def test_which_found(bridge: WslBridge):
    assert bridge.which("bash") is not None


def test_command_with_dollar_and_parens_not_expanded_by_us(bridge: WslBridge):
    # The literal command string is handed to bash -lc as ONE argv element;
    # bash (not Python) interprets $ and (), which is the desired behavior
    # for a real shell command.
    result = bridge.run("echo $(( 2 + 2 ))")
    assert result.ok
    assert result.stdout.strip() == "4"


# -- ctrl_all reference fetch ------------------------------------------------
def test_fetch_ctrl_all_reports_failure_when_engine_missing(bridge: WslBridge):
    # "atdyn"/"cgdyn" aren't installed in this dev environment -- the
    # command genuinely fails, which is what a caller must handle. See
    # app/ctrl_reference.py's validate_against_installed_genesis.
    result = bridge.fetch_ctrl_all("not-a-real-engine")
    assert not result.ok


# -- distro discovery -------------------------------------------------------
def test_list_distros(bridge: WslBridge):
    assert bridge.list_distros() == ["Ubuntu-24.04"]


# -- health_check ----------------------------------------------------------
def test_health_check_returns_items(bridge: WslBridge):
    items = bridge.health_check()
    names = [item.name for item in items]
    assert "WSL2 running" in names
    assert "mpirun found" in names
    assert "genesis_cg_tool/param present" in names
    assert all(hasattr(item, "ok") for item in items)


# -- async runner ----------------------------------------------------------
def _spin_until(predicate, timeout_ms=5000):
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)

    def check():
        if predicate():
            loop.quit()

    poll = QTimer()
    poll.timeout.connect(check)
    poll.start(10)
    timer.start(timeout_ms)
    loop.exec_()
    poll.stop()
    timer.stop()


def test_async_command_emits_lines_and_finishes(bridge: WslBridge):
    cmd = bridge.run_async("echo line1 && echo line2")
    lines = []
    finished = {"code": None}
    cmd.line.connect(lines.append)
    cmd.finished.connect(lambda code: finished.__setitem__("code", code))
    cmd.start()

    _spin_until(lambda: finished["code"] is not None)

    assert finished["code"] == 0
    assert lines == ["line1", "line2"]
