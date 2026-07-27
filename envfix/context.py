"""context.py — Extract code snippets from stack traces for richer Ollama prompts."""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from envfix.redact import redact_secrets

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
        snippet = redact_secrets(snippet)

        return CodeContext(
            filepath=str(resolved.relative_to(root)),
            line_number=lineno,
            start_line=start,
            end_line=end,
            snippet=snippet,
        )
    except (ValueError, OSError, UnicodeDecodeError):
        return None


def is_external_path(path_str: str, root: Path) -> bool:
    """Check if a path indicates a framework/stdlib or is outside the project root."""
    path_str = path_str.replace("\\", "/")
    if any(marker in path_str for marker in ["site-packages", "node_modules", "lib/python", "vendor/"]):
        return True
    
    path_obj = Path(path_str)
    if path_obj.is_absolute():
        try:
            path_obj.resolve().relative_to(root)
        except (ValueError, OSError):
            return True
            
    return False


def trim_stack_trace(stderr: str, cwd: Optional[str] = None, ignore_patterns: Optional[list[str]] = None) -> str:
    """
    Trim external frames (site-packages, node_modules) from stack traces.
    Strips any lines matching the provided regex patterns (ignore_patterns).
    Caps the final text at ~12000 chars (approx 3000 tokens), keeping the bottom.
    """
    root = Path(cwd or os.getcwd()).resolve()
    lines = stderr.splitlines()
    
    compiled_patterns = []
    if ignore_patterns:
        for p in ignore_patterns:
            try:
                compiled_patterns.append(re.compile(p))
            except re.error:
                pass
    
    out_lines = []
    hidden_count = 0
    skip_next = False
    
    for line in lines:
        if compiled_patterns and any(p.search(line) for p in compiled_patterns):
            continue
            
        if skip_next:
            skip_next = False
            # Python's code line under the frame is usually indented
            if line.startswith("    ") or line.startswith("\t"):
                continue
        
        # Check Python frame
        py_match = re.search(r'File "([^"]+)",\s*line \d+', line)
        if py_match:
            path = py_match.group(1)
            if is_external_path(path, root):
                hidden_count += 1
                skip_next = True
                continue
                
        # Check Node frame
        node_match = re.search(r'at\s+(?:[^\s(]+\s+\()?([^()]+?\.(?:js|ts|jsx|tsx|mjs|cjs)):(\d+)', line)
        if node_match:
            path = node_match.group(1)
            if is_external_path(path, root):
                hidden_count += 1
                continue
        
        # Keep this line, flush hidden marker if needed
        if hidden_count > 0:
            out_lines.append(f"  [... {hidden_count} external frames hidden ...]")
            hidden_count = 0
            
        out_lines.append(line)
        
    if hidden_count > 0:
        out_lines.append(f"  [... {hidden_count} external frames hidden ...]")
        
    trimmed = "\n".join(out_lines)
    
    # Fallback if trimming removed everything useful
    if not re.search(r'[a-zA-Z]', trimmed):
        trimmed = stderr
        
    # Cap at ~12000 chars (keeping the bottom, which holds the actual error)
    MAX_CHARS = 12000
    if len(trimmed) > MAX_CHARS:
        trimmed = "... [truncated] ...\n" + trimmed[-(MAX_CHARS - 25):]
        
    return trimmed
