"""tests/test_git_utils.py — Tests for git backup feature."""

import subprocess
import pytest
from unittest.mock import patch, MagicMock

from envfix.git_utils import is_in_git_repo, has_uncommitted_changes, create_safety_stash


@patch("envfix.git_utils.subprocess.run")
def test_is_in_git_repo_true(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="true\n")
    assert is_in_git_repo() is True


@patch("envfix.git_utils.subprocess.run")
def test_is_in_git_repo_false(mock_run):
    mock_run.return_value = MagicMock(returncode=128, stdout="fatal: not a git repo")
    assert is_in_git_repo() is False


@patch("envfix.git_utils.subprocess.run")
def test_has_uncommitted_changes_true(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout=" M file.py\n?? untracked.py")
    assert has_uncommitted_changes() is True


@patch("envfix.git_utils.subprocess.run")
def test_has_uncommitted_changes_false(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="")
    assert has_uncommitted_changes() is False


@patch("envfix.git_utils.subprocess.run")
def test_create_safety_stash_success(mock_run):
    # First call: git stash create -> returns hash
    create_result = MagicMock(returncode=0, stdout="a1b2c3d4e5f6\n")
    # Second call: git stash store -> returns success
    store_result = MagicMock(returncode=0)
    
    mock_run.side_effect = [create_result, store_result]
    
    assert create_safety_stash() is True
    assert mock_run.call_count == 2
    
    create_call_args = mock_run.call_args_list[0][0][0]
    assert create_call_args == ["git", "stash", "create"]
    
    store_call_args = mock_run.call_args_list[1][0][0]
    assert store_call_args[:3] == ["git", "stash", "store"]
    assert "envfix-auto-backup-" in store_call_args[4]
    assert store_call_args[5] == "a1b2c3d4e5f6"


@patch("envfix.git_utils.subprocess.run")
def test_create_safety_stash_nothing_to_stash(mock_run):
    # Returns empty if there's nothing that can be stashed
    create_result = MagicMock(returncode=0, stdout="\n")
    mock_run.return_value = create_result
    
    assert create_safety_stash() is False
    assert mock_run.call_count == 1
