"""logger.py — Appends structured attempt records to envfix_log.json."""

import json
import os
from datetime import datetime, timezone
from typing import Optional


LOG_FILE = "envfix_log.json"


def log_attempt(
    command: str,
    stderr: str,
    diagnosis: str,
    fix: str,
    approved: bool,
    worked: Optional[bool],
) -> None:
    """
    Append one attempt record to envfix_log.json in the current directory.

    Args:
        command:   The original command that failed.
        stderr:    The captured stderr from that command.
        diagnosis: The AI-generated diagnosis text.
        fix:       The AI-suggested fix command.
        approved:  Whether the user approved running the fix.
        worked:    True if the original command succeeded after the fix,
                   False if it still failed, None if fix was not approved.
    """
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "stderr": stderr,
        "diagnosis": diagnosis,
        "fix": fix,
        "approved": approved,
        "worked": worked,
    }

    # Load existing log (or start fresh)
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                log_data = json.load(f)
            if not isinstance(log_data, list):
                log_data = []
        except (json.JSONDecodeError, OSError):
            log_data = []
    else:
        log_data = []

    log_data.append(record)

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)
