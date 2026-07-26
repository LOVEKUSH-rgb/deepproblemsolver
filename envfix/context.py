"""context.py — Extract code snippets from stack traces for richer Ollama prompts."""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Lines to include above and below the failing line
CONTEXT_WINDOW = 10

# ── Stack-trace patterns ──────────────────────────────────────────────────────

# Python:  File "main.py", line 42
_PYTHON_RE = re.compile(r'File "([^"]+)",\s*line (\d+)')

# Node.js: at Object.<anonymous> (main.js:42:10)  OR  at main.js:42:10
_NODE_RE = re.compile(
    r'at\s+(?:[^\s(]+\s+\()?([^()]+?\.(?:js|ts|jsx|tsx|mjs|cjs)):(\d+)'
)


@dataclass
class CodeContext:
    """A code snippet extracted from the failing file."""

    filepath: str      # path relative to cwd — safe to show the user
    line_number: int   # the line the stack trace pointed at
    start_line: int    # first line of the snippet (1-indexed, clamped)
    end_line: int      # last line of the snippet  (1-indexed, clamped)
    snippet: str       # numbered source lines ready to embed in a prompt


def extract_context(stderr: str, cwd: Optional[str] = None) -> Optional[CodeContext]:
    """
    Parse *stderr* for file paths and line numbers in common stack trace formats.

    Only files that live inside *cwd* (or its subdirectories) are read.
    System paths, site-packages, and anything outside the project root are
    silently skipped.

    For Python tracebacks the *last* in-project file is used (that's where
    the user's own code triggered the error).  For Node.js the first match
    is used (the top of the call stack).

    Args:
        stderr: The captured error output from the failed command.
        cwd:    Project root to restrict file access to. Defaults to os.getcwd().

    Returns:
        A CodeContext if a safe, readable file is found; None otherwise.
    """
    root = Path(cwd or os.getcwd()).resolve()

    python_hits: list[tuple[str, int]] = [
        (m.group(1), int(m.group(2))) for m in _PYTHON_RE.finditer(stderr)
    ]
    node_hits: list[tuple[str, int]] = [
        (m.group(1), int(m.group(2))) for m in _NODE_RE.finditer(stderr)
    ]

    # Python: try last in-project file first (closest to the actual error)
    for filepath, lineno in reversed(python_hits):
        ctx = _read_safe(filepath, lineno, root)
        if ctx:
            return ctx

    # Node.js: try first match first (top of call stack = user's code)
    for filepath, lineno in node_hits:
        ctx = _read_safe(filepath, lineno, root)
        if ctx:
            return ctx

    return None


def _read_safe(filepath: str, lineno: int, root: Path) -> Optional[CodeContext]:
    """
    Read a ±CONTEXT_WINDOW line snippet from *filepath* around *lineno*.

    Returns None if:
    - the path resolves outside *root*  (safety boundary)
    - the file doesn't exist or can't be read
    - the line number is out of range
    """
    try:
        if os.path.isabs(filepath):
            resolved = Path(filepath).resolve()
        else:
            resolved = (root / filepath).resolve()

        # ── Safety check: must be inside the project root ─────────────────
        resolved.relative_to(root)   # raises ValueError if outside

        if not resolved.is_file():
            return None

        lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
        total = len(lines)

        if lineno < 1 or lineno > total:
            return None

        # Clamp snippet window to file bounds (1-indexed)
        start = max(1, lineno - CONTEXT_WINDOW)
        end   = min(total, lineno + CONTEXT_WINDOW)

        # Build a numbered snippet so the model can reference line numbers
        snippet = "\n".join(
            f"{start + i:4d} | {line}"
            for i, line in enumerate(lines[start - 1 : end])
        )

        return CodeContext(
            filepath=str(resolved.relative_to(root)),
            line_number=lineno,
            start_line=start,
            end_line=end,
            snippet=snippet,
        )
    except (ValueError, OSError, UnicodeDecodeError):
        return None
