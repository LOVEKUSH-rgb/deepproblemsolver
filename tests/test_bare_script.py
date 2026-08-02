import pytest
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from envfix.main import app

runner = CliRunner()

def test_bare_script_warning():
    # We'll mock Confirm.ask to return False so it exits without running the command
    with patch("envfix.main.Confirm.ask", return_value=False) as mock_confirm:
        result = runner.invoke(app, ["run", "script.py"])
        assert result.exit_code == 1
        assert "looks like a filename, not a runnable command" in result.stdout
        assert "Did you mean 'python script.py'?" in result.stdout
        mock_confirm.assert_called_once()

def test_bare_script_proceed():
    # If the user says Yes, it should attempt to run it.
    with patch("envfix.main.Confirm.ask", return_value=True):
        with patch("envfix.main.run_command", return_value=("", "", 0)) as mock_run:
            # We mock run_command to return 0 with no output (simulating Windows silent open)
            with patch("envfix.main.os.name", "nt"): # force it to pretend it's windows
                result = runner.invoke(app, ["run", "script.py"])
                # It should catch the Windows silent open error and exit 1
                assert result.exit_code == 1
                assert "Command returned 0 but produced no output" in result.stdout
                assert "was opened in an editor" in result.stdout

def test_valid_script_runner_no_warning():
    with patch("envfix.main.Confirm.ask") as mock_confirm:
        with patch("envfix.main.run_command", return_value=("output", "", 0)):
            result = runner.invoke(app, ["run", "python", "script.py"])
            # Should succeed immediately without warning
            assert result.exit_code == 0
            mock_confirm.assert_not_called()

