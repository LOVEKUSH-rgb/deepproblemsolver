"""logger.py — Structured JSON logging + history reader for envfix."""

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

LOG_FILE = "envfix_log.json"


def log_attempt(
    original_command: str,
    error_text: str,
    diagnosis: str,
    fix_command: str,
    user_approved: bool,
    fix_worked: Optional[bool],
    source: str = "ollama",
) -> None:
    """
    Append one attempt record to envfix_log.json in the current directory.

    Phase 2 schema
    ──────────────
    {
      "timestamp":        ISO-8601 UTC string,
      "original_command": the shell command that failed,
      "error_text":       captured stderr (or stdout) from that command,
      "diagnosis":        AI-generated or cache-sourced diagnosis,
      "fix_command":      the suggested fix command,
      "user_approved":    whether the user said y to apply it,
      "fix_worked":       True/False after retry, None if not approved,
      "source":           "ollama" | "cache"
    }

    Args:
        original_command: The failing shell command.
        error_text:       Captured stderr/stdout of the failure.
        diagnosis:        Diagnosis text (from model or cache).
        fix_command:      Suggested fix command.
        user_approved:    True if the user approved running the fix.
        fix_worked:       True/False after re-run, None if not applied.
        source:           Where the fix came from: "ollama" or "cache".
    """
    record: dict[str, Any] = {
        "timestamp":        datetime.now(timezone.utc).isoformat(),
        "original_command": original_command,
        "error_text":       error_text,
        "diagnosis":        diagnosis,
        "fix_command":      fix_command,
        "user_approved":    user_approved,
        "fix_worked":       fix_worked,
        "source":           source,
    }

    log_data = _load_log()
    log_data.append(record)
    _save_log(log_data)


def get_history(log_file: str = LOG_FILE) -> list[dict[str, Any]]:
    """
    Load and return all log entries, newest-first.

    Transparently reads both Phase 1 (legacy) and Phase 2 schemas.
    Each returned dict is guaranteed to have these keys:
        timestamp, original_command, error_text, diagnosis,
        fix_command, user_approved, fix_worked, source
    """
    raw = _load_log(log_file)
    normalised = []
    for entry in raw:
        normalised.append(_normalise_entry(entry))
    return list(reversed(normalised))  # newest first


# ── Private helpers ───────────────────────────────────────────────────────────

def _load_log(log_file: str = LOG_FILE) -> list[dict[str, Any]]:
    """Load JSON log; return empty list on any error."""
    if not os.path.exists(log_file):
        return []
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_log(log_data: list[dict[str, Any]], log_file: str = LOG_FILE) -> None:
    """Write the log list to disk as pretty-printed JSON."""
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)


def _normalise_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """
    Convert a Phase 1 log entry into the Phase 2 schema.
    Phase 2 entries pass through unchanged.
    """
    return {
        "timestamp":        entry.get("timestamp", ""),
        "original_command": entry.get("original_command") or entry.get("command", ""),
        "error_text":       entry.get("error_text") or entry.get("stderr", ""),
        "diagnosis":        entry.get("diagnosis", ""),
        "fix_command":      entry.get("fix_command") or entry.get("fix", ""),
        "user_approved":    entry.get("user_approved") if "user_approved" in entry else entry.get("approved", False),
        "fix_worked":       entry.get("fix_worked") if "fix_worked" in entry else entry.get("worked"),
        "source":           entry.get("source", "ollama"),
    }
