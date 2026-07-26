"""tests/test_phase6.py — Tests for Phase 6a: Smart Context extraction."""

import textwrap
from pathlib import Path

import pytest

from envfix.context import CONTEXT_WINDOW, CodeContext, extract_context


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_file(tmp_path: Path, name: str, lines: int) -> Path:
    """Create a dummy Python file with `lines` numbered lines."""
    content = "\n".join(f"line_{i} = {i}" for i in range(1, lines + 1))
    f = tmp_path / name
    f.write_text(content, encoding="utf-8")
    return f


# ── Python stack trace parsing ────────────────────────────────────────────────

class TestExtractContextPython:

    def test_extracts_simple_python_traceback(self, tmp_path):
        """Standard Python traceback → context returned."""
        script = _make_file(tmp_path, "main.py", 50)
        stderr = textwrap.dedent(f"""\
            Traceback (most recent call last):
              File "{script}", line 25, in <module>
                something_bad()
            NameError: name 'something_bad' is not defined
        """)
        ctx = extract_context(stderr, cwd=str(tmp_path))
        assert ctx is not None
        assert ctx.line_number == 25
        assert "main.py" in ctx.filepath
        assert ctx.start_line >= 1
        assert ctx.end_line <= 50

    def test_snippet_contains_target_line(self, tmp_path):
        """The snippet should include the line that failed."""
        script = _make_file(tmp_path, "app.py", 30)
        stderr = f'File "{script}", line 10, in do_thing\n    crash()'
        ctx = extract_context(stderr, cwd=str(tmp_path))
        assert ctx is not None
        assert ctx.start_line <= 10 <= ctx.end_line

    def test_clamps_to_start_of_file(self, tmp_path):
        """Error on line 3 → snippet starts at line 1, not -7."""
        script = _make_file(tmp_path, "tiny.py", 20)
        stderr = f'File "{script}", line 3, in foo\n    oops()'
        ctx = extract_context(stderr, cwd=str(tmp_path))
        assert ctx is not None
        assert ctx.start_line == 1

    def test_clamps_to_end_of_file(self, tmp_path):
        """Error on last line → snippet doesn't exceed file length."""
        script = _make_file(tmp_path, "small.py", 5)
        stderr = f'File "{script}", line 5, in bar\n    oops()'
        ctx = extract_context(stderr, cwd=str(tmp_path))
        assert ctx is not None
        assert ctx.end_line == 5

    def test_snippet_has_line_numbers(self, tmp_path):
        """Snippet lines should include line number prefixes."""
        script = _make_file(tmp_path, "main.py", 20)
        stderr = f'File "{script}", line 10, in foo'
        ctx = extract_context(stderr, cwd=str(tmp_path))
        assert ctx is not None
        assert " | " in ctx.snippet

    def test_last_inproject_file_used(self, tmp_path):
        """When multiple in-project files appear, the last one is used."""
        f1 = _make_file(tmp_path, "outer.py", 30)
        f2 = _make_file(tmp_path, "inner.py", 30)
        stderr = (
            f'File "{f1}", line 5, in outer_func\n'
            f'File "{f2}", line 15, in inner_func\n'
        )
        ctx = extract_context(stderr, cwd=str(tmp_path))
        assert ctx is not None
        assert "inner.py" in ctx.filepath
        assert ctx.line_number == 15


# ── Node.js stack trace parsing ───────────────────────────────────────────────

class TestExtractContextNode:

    def test_extracts_node_traceback(self, tmp_path):
        """Standard Node.js at-trace → context returned."""
        script = tmp_path / "server.js"
        script.write_text("\n".join(f"// line {i}" for i in range(1, 60)), encoding="utf-8")
        stderr = textwrap.dedent(f"""\
            TypeError: Cannot read property 'x' of undefined
                at Object.<anonymous> ({script}:42:10)
                at Module._compile (internal/modules/cjs/loader.js:1200:30)
        """)
        ctx = extract_context(stderr, cwd=str(tmp_path))
        assert ctx is not None
        assert ctx.line_number == 42
        assert "server.js" in ctx.filepath

    def test_node_ignores_internal_modules(self, tmp_path):
        """internal/modules/... paths should be skipped (not in project)."""
        stderr = (
            "Error: something\n"
            "    at internal/modules/cjs/loader.js:1200:30\n"
        )
        ctx = extract_context(stderr, cwd=str(tmp_path))
        assert ctx is None


# ── Safety: path escape prevention ───────────────────────────────────────────

class TestSafetyBoundary:

    def test_rejects_absolute_path_outside_cwd(self, tmp_path):
        """System files (e.g. site-packages) must not be readable."""
        system_file = Path("C:/Windows/System32/fake.py")
        stderr = f'File "{system_file}", line 1, in <module>'
        ctx = extract_context(stderr, cwd=str(tmp_path))
        assert ctx is None

    def test_rejects_dotdot_path_traversal(self, tmp_path):
        """Path traversal via ../ must be rejected."""
        evil_path = tmp_path / ".." / "secret.py"
        stderr = f'File "{evil_path}", line 5, in <module>'
        ctx = extract_context(stderr, cwd=str(tmp_path))
        assert ctx is None

    def test_nonexistent_file_returns_none(self, tmp_path):
        """A valid-looking path that doesn't exist → None."""
        stderr = f'File "{tmp_path / "ghost.py"}", line 3, in <module>'
        ctx = extract_context(stderr, cwd=str(tmp_path))
        assert ctx is None

    def test_accepts_relative_path_inside_cwd(self, tmp_path):
        """A relative path inside cwd should resolve and be read."""
        script = _make_file(tmp_path, "runner.py", 20)
        # Use relative name, not full absolute path
        stderr = f'File "runner.py", line 10, in go'
        ctx = extract_context(stderr, cwd=str(tmp_path))
        assert ctx is not None


# ── No match → graceful fallback ──────────────────────────────────────────────

class TestNoMatch:

    def test_returns_none_for_no_traceback(self, tmp_path):
        stderr = "command not found: foobar"
        ctx = extract_context(stderr, cwd=str(tmp_path))
        assert ctx is None

    def test_returns_none_for_empty_stderr(self, tmp_path):
        ctx = extract_context("", cwd=str(tmp_path))
        assert ctx is None
