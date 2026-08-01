"""logger.py — Structured JSON logging + history reader for envfix."""

import getpass
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

from envfix.embeddings import get_embedding
from envfix.telemetry import send_telemetry


def get_log_file() -> str:
    """
    Return the path to this user's envfix log file.

    The filename is derived from the OS username so that multiple
    users on a shared machine each get their own separate history.

    Examples:
        alice   -> envfix_log_alice.json
        bob     -> envfix_log_bob.json
    """
    # Sanitise the username so it's always safe to use in a filename
    raw = getpass.getuser()
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", raw)
    return f"envfix_log_{safe}.json"


# Legacy constant kept for backward compat (tests, cache.py default arg)
LOG_FILE = get_log_file()


def log_attempt(
    original_command: str,
    error_text: str,
    diagnosis: str,
    fix_command: str,
    user_approved: bool,
    fix_worked: Optional[bool],
    source: str = "ollama",
    category: str = "general",
    context_included: bool = False,
    provider: str = "ollama",
    entry_type: str = "reactive_fix",
    redacted_secrets_count: int = 0,
    classification: str = "UNKNOWN",
    mismatch_flagged: bool = False,
) -> None:
    """
    Append one attempt record to the user's personal log file.

    Phase 4 schema
    ──────────────
    {
      "timestamp":        ISO-8601 UTC string,
      "original_command": the shell command that failed,
      "error_text":       captured stderr (or stdout) from that command,
      "diagnosis":        AI-generated or cache-sourced diagnosis,
      "fix_command":      the suggested fix command,
      "user_approved":    whether the user said y to apply it,
      "fix_worked":       True/False after retry, None if not approved,
      "source":           "ollama" | "cache",
      "category":         ecosystem category (e.g. "python", "node", "general"),
      "context_included": whether a code snippet was injected into the prompt,
      "provider":         the AI provider used (e.g., "ollama", "groq", "gemini"),
      "classification":   error classification (ENVIRONMENT_ISSUE vs CODE_ISSUE),
      "mismatch_flagged": true if a fix was given for a code-logic error
    }

    Args:
        original_command: The failing shell command.
        error_text:       Captured stderr/stdout of the failure.
        diagnosis:        Diagnosis text (from model or cache).
        fix_command:      Suggested fix command.
        user_approved:    True if the user approved running the fix.
        fix_worked:       True/False after re-run, None if not applied.
        source:           Where the fix came from: "ollama" or "cache".
        category:         The ecosystem category.
        context_included: Whether a code snippet was included in the prompt.
        provider:         The AI provider used.
    """
    record: dict[str, Any] = {
        "timestamp":        datetime.now(timezone.utc).isoformat(),
        "entry_type":       entry_type,
        "original_command": original_command,
        "error_text":       error_text,
        "diagnosis":        diagnosis,
        "fix_command":      fix_command,
        "user_approved":    user_approved,
        "fix_worked":       fix_worked,
        "source":           source,
        "category":         category,
        "context_included": context_included,
        "provider":         provider,
        "classification":   classification,
        "mismatch_flagged": mismatch_flagged,
    }
    
    # Optionally compute and store a semantic embedding of the error text
    embedding = get_embedding(error_text)
    if embedding:
        record["embedding"] = embedding

    log_data = _load_log(get_log_file())
    log_data.append(record)
    _save_log(log_data, get_log_file())
    
    # Try to deduce error type
    error_lines = [line.strip() for line in error_text.splitlines() if line.strip()]
    error_type = "Unknown"
    if error_lines:
        last_line = error_lines[-1]
        if ":" in last_line:
            error_type = last_line.split(":")[0].split(" ")[-1]
        else:
            error_type = last_line[:50]

    # Only send telemetry for reactive_fix attempts
    if entry_type == "reactive_fix":
        send_telemetry(
            error_type=error_type,
            provider_used=provider or "unknown",
            was_cache_hit=(source == "cache"),
            fix_applied=user_approved,
            fix_worked=fix_worked,
            redacted_secrets_count=redacted_secrets_count
        )


def get_history(log_file: str = LOG_FILE) -> list[dict[str, Any]]:
    """
    Load and return all log entries, newest-first.

    Transparently reads both Phase 1 (legacy) and Phase 2 schemas.
    Each returned dict is guaranteed to have these keys:
        timestamp, original_command, error_text, diagnosis,
        fix_command, user_approved, fix_worked, source, category
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
        "category":         entry.get("category", "general"),
        "context_included": bool(entry.get("context_included", False)),
        "provider":         entry.get("provider", "ollama"),
        "entry_type":       entry.get("entry_type", "reactive_fix"),
    }
