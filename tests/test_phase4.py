import json
import pytest
from unittest.mock import patch, MagicMock

from envfix.ai import get_diagnosis, PROMPT_TEMPLATE
from envfix.cache import find_cached_fix
from envfix.logger import log_attempt, _load_log
from envfix.preview import is_destructive

def test_ai_prompt_includes_category():
    """Test that the category is correctly interpolated into the prompt."""
    with patch("envfix.ai.ollama") as mock_ollama:
        mock_ollama.chat.return_value = {
            "message": {"content": "DIAGNOSIS: bad\nFIX: echo ok"}
        }
        
        get_diagnosis("some error", category="node")
        
        # Check what was passed to ollama
        call_args = mock_ollama.chat.call_args[1]
        messages = call_args["messages"]
        prompt = messages[0]["content"]
        
        assert "related to the 'node' ecosystem" in prompt
        assert "some error" in prompt


def test_logger_writes_category(tmp_path, monkeypatch):
    """Test that log_attempt includes the category in the JSON."""
    monkeypatch.chdir(tmp_path)
    
    log_attempt(
        original_command="npm install",
        error_text="ENOENT",
        diagnosis="Missing package.json",
        fix_command="npm init -y",
        user_approved=True,
        fix_worked=True,
        source="ollama",
        category="node"
    )
    
    data = _load_log("envfix_log.json")
    assert len(data) == 1
    assert data[0]["category"] == "node"


def test_cache_category_mismatch(tmp_path, monkeypatch):
    """Test that the cache ignores matches with a different category."""
    monkeypatch.chdir(tmp_path)
    
    log_attempt(
        original_command="python -m missing",
        error_text="No module named missing",
        diagnosis="Missing module",
        fix_command="python -m pip install missing",
        user_approved=True,
        fix_worked=True,
        source="ollama",
        category="python"
    )
    
    # Searching for the exact same error, but with 'node' category should NOT match
    hit = find_cached_fix("No module named missing", category="node")
    assert hit is None
    
    # Searching with 'python' category SHOULD match
    hit = find_cached_fix("No module named missing", category="python")
    assert hit is not None
    assert hit.category == "python"


@pytest.mark.parametrize("cmd, expected", [
    ("rm -rf node_modules", True),
    ("sudo apt install something", True),
    ("git reset --hard HEAD", True),
    ("del /f /q temp.txt", True),
    ("rmdir /s build", True),
    ("kubectl delete pod x", True),
    ("pip install numpy", False),
    ("npm install express", False),
    ("python script.py", False),
])
def test_is_destructive(cmd, expected):
    """Test the destructive command heuristic."""
    assert is_destructive(cmd) == expected
