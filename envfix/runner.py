"""runner.py — Executes shell commands and captures their output."""

import subprocess
from typing import Tuple


def run_command(cmd: str) -> Tuple[str, str, int]:
    """
    Run a shell command and return (stdout, stderr, returncode).

    Args:
        cmd: The shell command string to execute.

    Returns:
        A tuple of (stdout, stderr, returncode).
        stdout and stderr are decoded strings (UTF-8, errors replaced).
    """
    result = subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    return stdout, stderr, result.returncode
