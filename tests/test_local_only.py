import pytest
import httpx
from unittest import mock
import os
from typer.testing import CliRunner

from envfix.main import app
from envfix.config import save_config, reset_config

from envfix import config

runner = CliRunner()

@pytest.fixture(autouse=True)
def mock_config_dir(tmp_path):
    # Mock the config directory to a temporary path to avoid PermissionErrors on Windows
    # and to keep tests isolated from the real user config.
    with mock.patch("envfix.config.CONFIG_DIR", tmp_path), \
         mock.patch("envfix.config.CONFIG_FILE", tmp_path / "config.toml"):
        yield

@mock.patch("httpx.Client.post")
def test_local_only_mode_blocks_telemetry(mock_post):
    # Enable local-only mode
    save_config({
        "local_only": True,
        "default_provider": "ollama",
        "default_category": "general"
    })
    
    # Try to trigger a diagnose command which usually sends telemetry at the end
    
    with mock.patch("envfix.ai.get_diagnosis") as mock_diagnose:
        mock_diagnose.return_value.diagnosis = "Mock diagnosis"
        mock_diagnose.return_value.fix = "echo mock"
        mock_diagnose.return_value.parsed_ok = True
        
        # We need a dummy log file
        with open("dummy_log.txt", "w") as f:
            f.write("Some fake traceback")
            
        result = runner.invoke(app, ["diagnose", "dummy_log.txt", "--ci"])
        
        assert result.exit_code == 0
        assert mock_post.called == False, "Telemetry was sent despite local_only=True!"

@mock.patch("envfix.runner.run_command")
@mock.patch("httpx.Client.post")
def test_local_only_mode_blocks_cloud_providers(mock_post, mock_run):
    # Enable local-only mode
    save_config({
        "local_only": True
    })
    
    # Attempt to run with gemini
    result = runner.invoke(app, ["run", "--provider", "gemini", "python", "-c", "import sys"])
    
    # It should exit with code 1 and block
    assert result.exit_code == 1
    assert "Local-only mode is enabled; cloud providers are disabled" in result.stdout
    assert mock_post.called == False
    assert mock_run.called == False

def test_doctor_command():
    save_config({"local_only": True})
    result = runner.invoke(app, ["doctor"])
    assert "Local-only mode: ENABLED" in result.stdout

    save_config({"local_only": False})
    result = runner.invoke(app, ["doctor"])
    assert "Local-only mode: DISABLED" in result.stdout
