import pytest
import os
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock
from typer import Exit

from envfix.config import load_project_config, load_config
from envfix.context import trim_stack_trace


def test_malformed_yaml(tmp_path):
    yaml_file = tmp_path / ".envfix.yaml"
    yaml_file.write_text("default_provider: groq\nbad_indent:\n  - a\n - b\n")

    with patch("envfix.config.Path.cwd", return_value=tmp_path):
        with pytest.raises(Exit) as excinfo:
            load_project_config()
        assert excinfo.value.exit_code == 1


def test_valid_yaml_override(tmp_path):
    yaml_file = tmp_path / ".envfix.yaml"
    yaml_file.write_text("default_provider: groq\ndefault_model: mixtral\n")

    with patch("envfix.config.Path.cwd", return_value=tmp_path):
        config = load_project_config()
        assert config["default_provider"] == "groq"
        assert config["default_model"] == "mixtral"


def test_trim_stack_trace_ignore_patterns():
    trace = "Traceback (most recent call last):\n  File \"main.py\", line 1\nSECRET_KEY_LINE_SHOULD_BE_HIDDEN\nNameError: test"
    
    # Without ignore_patterns
    res1 = trim_stack_trace(trace)
    assert "SECRET_KEY_LINE" in res1
    
    # With ignore_patterns
    res2 = trim_stack_trace(trace, ignore_patterns=[r"SECRET_KEY"])
    assert "SECRET_KEY_LINE" not in res2
    assert "NameError: test" in res2


@patch("envfix.main.run_command")
@patch("envfix.main.Confirm.ask")
@patch("envfix.main.console.print")
@patch("envfix.main.log_attempt")
@patch("envfix.main.extract_package_name")
@patch("envfix.main.find_cached_fix")
def test_post_fix_hook_executes(mock_cache, mock_extract, mock_log, mock_print, mock_ask, mock_run, tmp_path):
    # Setup test where a command fails, LLM returns a fix, and the fix succeeds
    # To avoid huge mock setup, we'll just test the code flow inside main.py
    # by mocking load_config and the retry execution.
    from envfix.main import run
    from typer.testing import CliRunner
    from envfix.main import app
    import envfix.main
    
    yaml_file = tmp_path / ".envfix.yaml"
    yaml_file.write_text("post_fix_hook: \"echo 'hello world'\"\n")
    
    mock_extract.return_value = None
    mock_cache.return_value = None
    
    with patch("envfix.main.load_config") as mock_load:
        mock_load.return_value = {"post_fix_hook": "echo 'hello world'"}
        
        # We need run_command to return success on the retry
        # mock_run side_effect: 
        # 1. original command (fail)
        # 2. hook command (success) - wait, retry is called first!
        # 3. hook command
        
        # original fail
        mock_run.side_effect = [
            ("out", "err", 1), # original
            ("out", "", 0),    # fix retry (worked)
            ("hook run", "", 0) # hook
        ]
        
        # Mock get_diagnosis to return a fake result
        with patch("envfix.main.get_diagnosis") as mock_diag:
            mock_diag.return_value = MagicMock(parsed_ok=True, diagnosis="d", fix="fix", raw_response="raw")
            mock_ask.return_value = True # approve fix
            
            # Run CLI
            runner = CliRunner()
            result = runner.invoke(app, ["run", "python", "bad.py"])
            
            # The hook should have been called
            mock_run.assert_any_call("echo 'hello world'")
