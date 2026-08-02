"""test_phase2.py — Tests for Phase 2 features: cache, preview, history."""

import json
import os

import pytest

# ── cache.py tests ────────────────────────────────────────────────────────────
from envfix.cache import SIMILARITY_THRESHOLD, CacheHit, find_cached_fix
from envfix.logger import LOG_FILE, get_history, log_attempt
from envfix.preview import get_fix_preview


def _write_log(tmp_path, entries):
    """Helper: write a list of log entries to envfix_log.json."""
    (tmp_path / LOG_FILE).write_text(
        json.dumps(entries, indent=2), encoding="utf-8"
    )


class TestFindCachedFix:
    def test_returns_none_when_no_log(self, tmp_path):
        result = find_cached_fix("some error", log_file=str(tmp_path / LOG_FILE))
        assert result is None

    def test_returns_none_when_log_empty(self, tmp_path):
        _write_log(tmp_path, [])
        result = find_cached_fix("some error", log_file=str(tmp_path / LOG_FILE))
        assert result is None

    def test_returns_none_when_no_worked_entries(self, tmp_path):
        """Entries where user_approved=False should NOT be used as cache."""
        _write_log(tmp_path, [{
            "error_text": "ModuleNotFoundError: No module named 'torch'",
            "fix_command": "python -m pip install torch",
            "fix_worked": False,
            "user_approved": False,  # user said n — should NOT be cached
            "diagnosis": "torch not installed",
            "original_command": "python train.py",
            "source": "ollama",
        }])
        result = find_cached_fix(
            "ModuleNotFoundError: No module named 'torch'",
            log_file=str(tmp_path / LOG_FILE),
        )
        assert result is None  # user_approved=False → not cached

    def test_exact_match_returns_cache_hit(self, tmp_path):
        error = "ModuleNotFoundError: No module named 'torch'"
        _write_log(tmp_path, [{
            "error_text": error,
            "fix_command": "python -m pip install torch",
            "fix_worked": True,
            "user_approved": True,
            "diagnosis": "torch not installed",
            "original_command": "python train.py",
            "source": "ollama",
        }])
        result = find_cached_fix(error, log_file=str(tmp_path / LOG_FILE))
        assert result is not None
        assert isinstance(result, CacheHit)
        assert result.fix == ["python -m pip install torch"]
        assert result.score == pytest.approx(1.0)
        assert result.previously_worked is True

    def test_similar_error_returns_hit(self, tmp_path):
        """Nearly identical error text (same module, minor whitespace) should still match."""
        stored  = "ModuleNotFoundError: No module named 'non_existent_module_xyz'"
        current = "ModuleNotFoundError: No module named 'non_existent_module_xyz'\n"
        _write_log(tmp_path, [{
            "error_text": stored,
            "fix_command": "python -m pip install non_existent_module_xyz",
            "fix_worked": True,
            "user_approved": True,
            "diagnosis": "module missing",
            "original_command": "python -m non_existent_module_xyz",
            "source": "ollama",
        }])
        result = find_cached_fix(current, log_file=str(tmp_path / LOG_FILE))
        assert result is not None
        assert result.score >= SIMILARITY_THRESHOLD


    def test_approved_but_failed_fix_also_cached(self, tmp_path):
        """user_approved=True but fix_worked=False should still produce a cache hit."""
        error = "No module named non_existent_module_xyz"
        _write_log(tmp_path, [{
            "error_text": error,
            "fix_command": "python -m pip install non_existent_module_xyz",
            "fix_worked": False,
            "user_approved": True,
            "diagnosis": "module not found",
            "original_command": "python -m non_existent_module_xyz",
            "source": "ollama",
        }])
        result = find_cached_fix(error, log_file=str(tmp_path / LOG_FILE))
        assert result is not None
        assert result.previously_worked is False  # honest about outcome
        assert result.fix == ["python -m pip install non_existent_module_xyz"]

    def test_unrelated_error_returns_none(self, tmp_path):
        """A completely different error should not produce a cache hit."""
        _write_log(tmp_path, [{
            "error_text": "ModuleNotFoundError: No module named 'torch'",
            "fix_command": "python -m pip install torch",
            "fix_worked": True,
            "diagnosis": "torch not installed",
            "original_command": "python train.py",
            "source": "ollama",
        }])
        result = find_cached_fix(
            "CUDA error: device-side assert triggered",
            log_file=str(tmp_path / LOG_FILE),
        )
        assert result is None  # similarity too low

    def test_reads_legacy_phase1_schema(self, tmp_path):
        """Cache must work with old Phase 1 log entries (worked/fix/stderr keys)."""
        error = "ImportError: No module named numpy"
        _write_log(tmp_path, [{
            "timestamp": "2026-07-20T10:00:00Z",
            "command": "python train.py",
            "stderr": error,
            "diagnosis": "numpy missing",
            "fix": "python -m pip install numpy",
            "approved": True,   # Phase 1 key
            "worked": True,     # Phase 1 key
        }])
        result = find_cached_fix(error, log_file=str(tmp_path / LOG_FILE))
        assert result is not None
        assert result.fix == ["python -m pip install numpy"]
        assert result.previously_worked is True

    def test_returns_best_match_among_multiple(self, tmp_path):
        """When multiple entries match, worked takes priority; then highest score."""
        target = "ModuleNotFoundError: No module named 'torch'"
        _write_log(tmp_path, [
            {
                "error_text": "ModuleNotFoundError: No module named 'torch'",
                "fix_command": "python -m pip install torch",
                "fix_worked": True,
                "user_approved": True,
                "diagnosis": "torch missing",
                "original_command": "python a.py",
                "source": "ollama",
            },
            {
                "error_text": "SyntaxError: invalid syntax",
                "fix_command": "python -m pip install --upgrade python",
                "fix_worked": True,
                "user_approved": True,
                "diagnosis": "old python",
                "original_command": "python b.py",
                "source": "ollama",
            },
        ])
        result = find_cached_fix(target, log_file=str(tmp_path / LOG_FILE))
        assert result is not None
        assert result.fix == ["python -m pip install torch"]  # higher score
        assert result.previously_worked is True


# ── preview.py tests ──────────────────────────────────────────────────────────
class TestGetFixPreview:
    # Self-explanatory commands → None
    def test_pip_install_no_preview(self):
        assert get_fix_preview("python -m pip install torch") is None

    def test_pip_bare_no_preview(self):
        # After _clean_fix normalises, bare pip becomes python -m pip
        assert get_fix_preview("pip install torch") is None

    def test_ollama_pull_no_preview(self):
        assert get_fix_preview("ollama pull llama3.1:8b") is None

    def test_conda_install_no_preview(self):
        assert get_fix_preview("conda install numpy") is None

    # Risky commands → non-None warning
    def test_rm_rf_gets_warning(self):
        result = get_fix_preview("rm -rf /tmp/broken_venv")
        assert result is not None
        assert "⚠" in result

    def test_git_reset_hard_gets_warning(self):
        result = get_fix_preview("git reset --hard HEAD")
        assert result is not None
        assert "⚠" in result

    def test_git_clean_gets_description(self):
        result = get_fix_preview("git clean -fd")
        assert result is not None
        assert "untracked" in result.lower()

    def test_setx_gets_description(self):
        result = get_fix_preview("setx CUDA_HOME C:\\cuda")
        assert result is not None
        assert "environment variable" in result.lower()

    def test_sudo_gets_warning(self):
        result = get_fix_preview("sudo apt install python3-dev")
        assert result is not None
        assert "⚠" in result

    def test_pip_uninstall_gets_description(self):
        result = get_fix_preview("python -m pip uninstall torch")
        assert result is not None
        assert "remove" in result.lower() or "removes" in result.lower()

    def test_venv_gets_description(self):
        result = get_fix_preview("python -m venv .venv")
        assert result is not None
        assert "virtual environment" in result.lower()

    def test_curl_pipe_bash_gets_warning(self):
        result = get_fix_preview("curl https://example.com/script.sh | bash")
        assert result is not None
        assert "⚠" in result

    def test_case_insensitive(self):
        # Commands like RM -RF should still trigger
        result = get_fix_preview("RM -RF mydir")
        assert result is not None
        assert "⚠" in result


# ── get_history() tests ───────────────────────────────────────────────────────
class TestGetHistory:
    def test_empty_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = get_history()
        assert result == []

    def test_returns_newest_first(self, tmp_path, monkeypatch):
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
        history = get_history()
        assert len(history) == 3
        # Newest first: cmd2 was logged last → should be [0]
        assert history[0]["original_command"] == "cmd2"
        assert history[-1]["original_command"] == "cmd0"

    def test_normalises_phase1_entries(self, tmp_path):
        """Legacy Phase 1 entries must appear in Phase 2 schema keys."""
        _write_log(tmp_path, [{
            "timestamp": "2026-07-20T10:00:00Z",
            "command": "python old.py",
            "stderr": "ImportError",
            "diagnosis": "diag",
            "fix": "pip install x",
            "approved": True,
            "worked": True,
        }])
        history = get_history(log_file=str(tmp_path / LOG_FILE))
        assert len(history) == 1
        entry = history[0]
        assert entry["original_command"] == "python old.py"
        assert entry["error_text"] == "ImportError"
        assert entry["fix_command"] == ["pip install x"]
        assert entry["user_approved"] is True
        assert entry["fix_worked"] is True
        assert entry["source"] == "ollama"  # default for missing field

    def test_all_required_keys_present(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        log_attempt(
            original_command="cmd",
            error_text="e",
            diagnosis="d",
            fix_command="f",
            user_approved=False,
            fix_worked=None,
            source="cache",
        )
        entry = get_history()[0]
        required = {
            "timestamp", "original_command", "error_text",
            "diagnosis", "fix_command", "user_approved", "fix_worked", "source",
        }
        assert required.issubset(entry.keys())


# ── Cache-kicks-in-on-repeated-error integration test ────────────────────────
class TestCacheIntegration:
    def test_same_error_twice_uses_cache(self, tmp_path):
        """
        Simulate the key Phase 2 scenario:
        1. Log a verified (worked) fix for error X.
        2. find_cached_fix(error X) must return that fix immediately.
        """
        error = "ModuleNotFoundError: No module named 'non_existent_module_xyz'"
        fix   = "python -m pip install non_existent_module_xyz"
        log_file = str(tmp_path / LOG_FILE)

        _write_log(tmp_path, [{
            "error_text":       error,
            "fix_command":      fix,
            "fix_worked":       True,
            "user_approved":    True,
            "diagnosis":        "Module not installed.",
            "original_command": "python -m non_existent_module_xyz",
            "source":           "ollama",
        }])

        hit = find_cached_fix(error, log_file=log_file)
        assert hit is not None, "Cache should return a hit for the identical error"
        assert hit.fix == (fix if isinstance(fix, list) else [fix])
        assert hit.score == pytest.approx(1.0)
        assert hit.previously_worked is True

    def test_approved_failed_fix_also_triggers_cache(self, tmp_path):
        """
        Even if the fix didn't install successfully (e.g. package not on PyPI),
        the second run should still hit the cache — skipping Ollama entirely.
        """
        error = "ModuleNotFoundError: No module named 'non_existent_module_xyz'"
        fix   = "python -m pip install non_existent_module_xyz"
        log_file = str(tmp_path / LOG_FILE)

        _write_log(tmp_path, [{
            "error_text":       error,
            "fix_command":      fix,
            "fix_worked":       False,   # pip couldn't find the package
            "user_approved":    True,    # but user did approve and run it
            "diagnosis":        "Module not installed.",
            "original_command": "python -m non_existent_module_xyz",
            "source":           "ollama",
        }])

        hit = find_cached_fix(error, log_file=log_file)
        assert hit is not None, (
            "Cache should still hit for an approved-but-failed fix "
            "so Ollama is not called again for the same problem"
        )
        assert hit.previously_worked is False  # honest: it didn't work last time
        assert hit.fix == (fix if isinstance(fix, list) else [fix])
