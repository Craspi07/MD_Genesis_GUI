#!/usr/bin/env python3
"""A fake `wsl.exe` used by tests/test_wsl.py.

Stands in for the real Windows executable so WslBridge's argv
construction and decoding can be exercised on any platform. Understands
just enough of the real CLI shape to be useful:

  fake_wsl.py -l -v                          -> UTF-16LE distro listing
  fake_wsl.py -d <distro> -- bash -lc "<cmd>" -> runs <cmd> via bash -c,
                                                   forwarding the environment
                                                   (so a WSL_UTF8 check works)
"""
import subprocess
import sys


def main() -> int:
    argv = sys.argv[1:]

    if argv[:2] == ["-l", "-v"]:
        text = (
            "  NAME              STATE           VERSION\n"
            "* Ubuntu-24.04      Running         2\n"
        )
        sys.stdout.buffer.write(text.encode("utf-16-le"))
        return 0

    if len(argv) >= 5 and argv[0] == "-d" and argv[2] == "--" and argv[3] == "bash" and argv[4] == "-lc":
        command = argv[5] if len(argv) > 5 else ""
        completed = subprocess.run(["bash", "-c", command])
        return completed.returncode

    sys.stderr.write(f"fake_wsl: unhandled invocation: {argv!r}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
