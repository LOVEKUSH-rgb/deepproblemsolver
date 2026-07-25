"""preview.py — Plain-English dry-run descriptions for fix commands."""

import re
from typing import Optional

# Each rule: (regex_pattern, description_or_None).
# None means the command is self-explanatory — no extra text is shown.
# Rules are checked in order; first match wins.
_RULES: list[tuple[str, Optional[str]]] = [
    # ── Destructive / irreversible ────────────────────────────────────────
    (r"rm\s+.*-[a-z]*r[a-z]*|-rf\b", "⚠  Permanently deletes files/directories — cannot be undone"),
    (r"^del\b|^rd\s|^rmdir\b",        "⚠  Permanently deletes files or directories"),
    (r"git\s+clean\b",                 "Removes all untracked files from the git working directory"),
    (r"git\s+reset\s+--hard\b",        "⚠  Discards ALL uncommitted changes — cannot be undone"),
    # ── System configuration ──────────────────────────────────────────────
    (r"setx\b",                        "Permanently sets a Windows environment variable (survives reboot)"),
    (r"export\s+\w+=|^set\s+\w+=",    "Sets an environment variable for the current session only"),
    (r"chmod\b",                       "Changes file permissions on disk"),
    (r"chown\b",                       "Changes file ownership on disk"),
    # ── Internet + shell execution risk ──────────────────────────────────
    (r"(curl|wget).+\|\s*(bash|sh|python)", "⚠  Downloads a script from the internet and executes it immediately"),
    (r"\|\s*(bash|sh)\b",             "⚠  Pipes output directly into a shell interpreter"),
    (r"\bsudo\b",                      "⚠  Runs the command with administrator (root) privileges"),
    # ── Package management ────────────────────────────────────────────────
    (r"python\s+-m\s+pip\s+uninstall\b|^pip\s+uninstall\b",
                                       "Removes an installed Python package from this environment"),
    (r"conda\s+remove\b",              "Removes a conda package from the active environment"),
    # ── Self-explanatory — no preview needed (return None explicitly) ─────
    (r"python\s+-m\s+pip\s+install\b|^pip\s+install\b", None),
    (r"python\s+-m\s+venv\b",          "Creates a new Python virtual environment in the given directory"),
    (r"ollama\s+pull\b",               None),
    (r"conda\s+install\b",             None),
    (r"conda\s+create\b",              "Creates a new conda environment"),
]


def get_fix_preview(fix_cmd: str) -> Optional[str]:
    """
    Return a one-line plain-English description of what a fix command will do.

    For clearly safe / self-explanatory commands (e.g. ``pip install``) this
    returns None — showing the command text alone is enough.  For commands that
    delete files, change system config, or execute internet-fetched code, a
    short warning is returned so the user can make an informed decision before
    approving.

    Args:
        fix_cmd: The shell command string to describe.

    Returns:
        A description string (may contain ⚠), or None if no extra text needed.
    """
    for pattern, description in _RULES:
        if re.search(pattern, fix_cmd, re.IGNORECASE):
            return description  # can be None — that is intentional
    return None   # no rule matched — also no preview
