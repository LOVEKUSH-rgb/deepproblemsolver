"""cache.py — Known-fix cache: fuzzy-match current errors against past verified fixes."""

import json
import os
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional

# Minimum similarity ratio (0–1) to consider a log entry a match.
# 0.85 is deliberately conservative: we only surface cache hits when
# the error looks nearly identical to a past one.
SIMILARITY_THRESHOLD = 0.85


@dataclass
class CacheHit:
    """A previously verified fix that closely matches the current error."""

    fix: str
    diagnosis: str
    score: float          # 0.0 – 1.0 similarity ratio
    original_command: str  # the command that originally triggered the error


def find_cached_fix(
    error_text: str,
    log_file: str = "envfix_log.json",
    threshold: float = SIMILARITY_THRESHOLD,
) -> Optional[CacheHit]:
    """
    Search envfix_log.json for a previously verified fix for a similar error.

    Uses difflib.SequenceMatcher for lightweight fuzzy string similarity.
    Only considers log entries where the fix is confirmed to have worked.
    Supports both the Phase 1 schema (worked/fix/stderr) and the new
    Phase 2 schema (fix_worked/fix_command/error_text) transparently.

    Args:
        error_text: The current stderr text to match against.
        log_file:   Path to the JSON log file (defaults to cwd).
        threshold:  Minimum SequenceMatcher ratio to accept as a hit.

    Returns:
        A CacheHit with the best-matching fix, or None if no good match found.
    """
    if not os.path.exists(log_file):
        return None

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            log_data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    if not isinstance(log_data, list) or not log_data:
        return None

    best: Optional[CacheHit] = None
    best_score = 0.0

    for entry in log_data:
        # ── Support both Phase 1 and Phase 2 schemas ─────────────────────
        # Phase 2 keys take precedence; Phase 1 keys are fallback.
        worked = (
            entry.get("fix_worked")
            if "fix_worked" in entry
            else entry.get("worked")
        )
        if not worked:
            continue  # only cache hits that actually fixed the problem

        stored_error: str = entry.get("error_text") or entry.get("stderr", "")
        fix: str = entry.get("fix_command") or entry.get("fix", "")
        diagnosis: str = entry.get("diagnosis", "")
        original_cmd: str = (
            entry.get("original_command") or entry.get("command", "")
        )

        if not stored_error or not fix:
            continue

        score = SequenceMatcher(None, error_text, stored_error).ratio()
        if score > best_score:
            best_score = score
            best = CacheHit(
                fix=fix,
                diagnosis=diagnosis,
                score=score,
                original_command=original_cmd,
            )

    if best and best.score >= threshold:
        return best

    return None
