import pytest
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from envfix.main import app

runner = CliRunner()

def test_bare_script_cancel():
    # We'll mock Prompt.ask to return "3" so it exits without running the command
    with patch("envfix.main.Prompt.ask", return_value="3") as mock_prompt:
        result = runner.invoke(app, ["run", "script.py"])
        assert result.exit_code == 1
        assert "looks like a filename, not a runnable command" in result.stdout
        assert "Did you mean" in result.stdout
        mock_prompt.assert_called_once()

def test_bare_script_proceed():
    # Option 2: If the user says 2, it should attempt to run it as-is.
    with patch("envfix.main.Prompt.ask", return_value="2"):
        with patch("envfix.main.run_command", return_value=("", "", 0)) as mock_run:
            # We mock run_command to return 0 with no output (simulating Windows silent open)
            with patch("envfix.main.os.name", "nt"): # force it to pretend it's windows
                result = runner.invoke(app, ["run", "script.py"])
                # It should catch the Windows silent open error and exit 1
                assert result.exit_code == 1
                assert "was opened in an editor" in result.stdout
                mock_run.assert_called_once_with("script.py")

def test_bare_script_fix_run():
    # Option 1: Run modified command
    with patch("envfix.main.Prompt.ask", return_value="1"):
        with patch("envfix.main.run_command", return_value=("output", "", 0)) as mock_run:
            result = runner.invoke(app, ["run", "script.py"])
            assert result.exit_code == 0
            mock_run.assert_called_once_with("python script.py")

def test_valid_script_runner_no_warning():
    with patch("envfix.main.Prompt.ask") as mock_prompt:
        with patch("envfix.main.run_command", return_value=("output", "", 0)):
            result = runner.invoke(app, ["run", "python", "script.py"])
            # Should succeed immediately without warning
            assert result.exit_code == 0
            mock_prompt.assert_not_called()

