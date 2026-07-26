"""git_utils.py — Git safety backup utilities."""

import subprocess
import time
from typing import Optional


def is_in_git_repo(cwd: Optional[str] = None) -> bool:
    """Check if the current directory is inside a Git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=cwd, capture_output=True, text=True, check=False
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except FileNotFoundError:
        return False


def has_uncommitted_changes(cwd: Optional[str] = None) -> bool:
    """Check if there are any uncommitted changes in the repository."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd, capture_output=True, text=True, check=False
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except FileNotFoundError:
        return False


def create_safety_stash(cwd: Optional[str] = None) -> bool:
    """
    Create a non-destructive stash of the current working directory.
    Uses 'git stash create' and 'git stash store' to avoid removing changes
    from the working directory (unlike 'git stash push').
    """
    try:
        # Create stash object
        create_result = subprocess.run(
            ["git", "stash", "create"],
            cwd=cwd, capture_output=True, text=True, check=False
        )
        
        if create_result.returncode != 0:
            return False
            
        commit_hash = create_result.stdout.strip()
        if not commit_hash:
            return False  # Nothing to stash (e.g. only untracked files and no -u)
            
        # Store it
        timestamp = int(time.time())
        msg = f"envfix-auto-backup-{timestamp}"
        
        store_result = subprocess.run(
            ["git", "stash", "store", "-m", msg, commit_hash],
            cwd=cwd, capture_output=True, text=True, check=False
        )
        
        return store_result.returncode == 0
    except FileNotFoundError:
        return False
