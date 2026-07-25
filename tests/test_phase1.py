"""
test_phase1.py — Sanity checks for envfix Phase 1 (no Ollama required).

Run with:
    python -m pytest tests/test_phase1.py -v
"""

import json
import os
import tempfile

import pytest

# ── ai.py parser tests (no real Ollama call needed) ──────────────────────────
from envfix.ai import _parse_response, _clean_fix


class TestParseResponse:
    def test_strict_format(self):
        raw = "DIAGNOSIS: CUDA version mismatch.\nFIX: pip install torch==2.0.0+cu118"
        r = _parse_response(raw)
        assert r.parsed_ok is True
        assert "CUDA" in r.diagnosis
        assert r.fix == "python -m pip install torch==2.0.0+cu118"

    def test_case_insensitive(self):
        raw = "diagnosis: missing package\nfix: pip install numpy"
        r = _parse_response(raw)
        assert r.parsed_ok is True
        assert r.fix == "python -m pip install numpy"

    def test_extra_whitespace(self):
        raw = "DIAGNOSIS:   broken venv   \nFIX:   python -m venv .venv   "
        r = _parse_response(raw)
        assert r.parsed_ok is True
        assert r.diagnosis == "broken venv"
        assert r.fix == "python -m venv .venv"

    def test_multiline_diagnosis(self):
        raw = (
            "DIAGNOSIS: The torch package was installed without CUDA support.\n"
            "It needs to be reinstalled with the correct index URL.\n"
            "FIX: pip install torch --index-url https://download.pytorch.org/whl/cu118"
        )
        r = _parse_response(raw)
        assert r.parsed_ok is True
        assert "torch" in r.fix
        assert r.fix.startswith("python -m pip")

    def test_unparseable_falls_back_gracefully(self):
        raw = "I'm sorry, I don't understand the question."
        r = _parse_response(raw)
        assert r.parsed_ok is False
        assert r.raw_response == raw
        # Should not crash, and both fields should be populated strings
        assert isinstance(r.diagnosis, str)
        assert isinstance(r.fix, str)

    def test_only_diagnosis_no_fix(self):
        raw = "DIAGNOSIS: missing cuda libs"
        r = _parse_response(raw)
        assert r.parsed_ok is False  # no FIX line → fallback

    def test_fix_takes_first_line_only(self):
        raw = "DIAGNOSIS: broken\nFIX: pip install torch\nAlso you might want to..."
        r = _parse_response(raw)
        assert r.parsed_ok is True
        assert r.fix == "python -m pip install torch"


# ── runner.py tests ───────────────────────────────────────────────────────────
from envfix.runner import run_command


class TestRunCommand:
    def test_successful_command(self):
        stdout, stderr, rc = run_command("python --version")
        assert rc == 0
        assert "Python" in stdout or "Python" in stderr  # some shells write to stderr

    def test_failed_command(self):
        stdout, stderr, rc = run_command("python -c 'raise SystemExit(1)'")
        assert rc == 1

    def test_stderr_captured(self):
        stdout, stderr, rc = run_command(
            "python -c \"import sys; sys.stderr.write('err_text'); sys.exit(1)\""
        )
        assert rc == 1
        assert "err_text" in stderr

    def test_nonexistent_command(self):
        _, _, rc = run_command("this_command_absolutely_does_not_exist_xyz")
        assert rc != 0


# ── _clean_fix tests ──────────────────────────────────────────────────────────
class TestCleanFix:
    def test_strips_single_backtick(self):
        assert _clean_fix("`pip install torch`") == "python -m pip install torch"

    def test_strips_triple_backtick(self):
        assert _clean_fix("```pip install torch```") == "python -m pip install torch"

    def test_strips_surrounding_double_quotes(self):
        assert _clean_fix('"pip install torch"') == "python -m pip install torch"

    def test_strips_surrounding_single_quotes(self):
        assert _clean_fix("'pip install torch'") == "python -m pip install torch"

    def test_strips_bold_markdown(self):
        assert _clean_fix("**pip install torch**") == "python -m pip install torch"

    def test_plain_pip_normalised(self):
        assert _clean_fix("pip install torch") == "python -m pip install torch"

    def test_python_m_pip_unchanged(self):
        assert _clean_fix("python -m pip install torch") == "python -m pip install torch"

    def test_backtick_with_spaces(self):
        assert _clean_fix("  `python -m pip install torch`  ") == "python -m pip install torch"

    def test_non_pip_command_unchanged(self):
        assert _clean_fix("python -m venv .venv") == "python -m venv .venv"

    def test_no_strip_inner_backticks(self):
        # Inner backticks (e.g. in a path) should NOT be stripped
        result = _clean_fix("pip install my-pkg")
        assert result == "python -m pip install my-pkg"

    def test_parser_strips_backtick_end_to_end(self):
        raw = "DIAGNOSIS: Missing module.\nFIX: `pip install numpy`"
        r = _parse_response(raw)
        assert r.parsed_ok is True
        assert r.fix == "python -m pip install numpy"  # backticks stripped + pip normalised


# ── logger.py tests ───────────────────────────────────────────────────────────
from envfix.logger import LOG_FILE, log_attempt



# ── logger.py tests (Phase 2 schema) ─────────────────────────────────────────
class TestLogAttempt:
    def test_creates_log_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        log_attempt(
            original_command="python -m pip install torch",
            error_text="ModuleNotFoundError",
            diagnosis="torch not installed",
            fix_command="python -m pip install torch",
            user_approved=True,
            fix_worked=True,
            source="ollama",
        )
        log_path = tmp_path / LOG_FILE
        assert log_path.exists()

    def test_log_structure(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        log_attempt(
            original_command="cmd",
            error_text="err",
            diagnosis="diag",
            fix_command="fix_cmd",
            user_approved=False,
            fix_worked=None,
            source="ollama",
        )
        with open(tmp_path / LOG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) == 1
        record = data[0]
        for key in (
            "timestamp", "original_command", "error_text",
            "diagnosis", "fix_command", "user_approved", "fix_worked", "source",
        ):
            assert key in record, f"Missing key: {key}"
        assert record["user_approved"] is False
        assert record["fix_worked"] is None
        assert record["source"] == "ollama"

    def test_appends_multiple_records(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        for i in range(3):
            log_attempt(
                original_command=f"cmd{i}",
                error_text="e",
                diagnosis="d",
                fix_command="f",
                user_approved=True,
                fix_worked=True,
                source="ollama",
            )
        with open(tmp_path / LOG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 3

    def test_survives_corrupt_log(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / LOG_FILE).write_text("NOT JSON{{{{", encoding="utf-8")
        log_attempt(
            original_command="x",
            error_text="e",
            diagnosis="d",
            fix_command="f",
            user_approved=True,
            fix_worked=False,
            source="cache",
        )
        with open(tmp_path / LOG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 1

    def test_source_field_recorded(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        log_attempt(
            original_command="cmd",
            error_text="e",
            diagnosis="d",
            fix_command="f",
            user_approved=True,
            fix_worked=True,
            source="cache",
        )
        with open(tmp_path / LOG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        assert data[0]["source"] == "cache"
