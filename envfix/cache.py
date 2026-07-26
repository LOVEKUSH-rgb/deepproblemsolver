"""cache.py — Known-fix cache: fuzzy-match current errors against past verified fixes."""

import json
import os
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional

from envfix.logger import get_log_file
from envfix.embeddings import get_embedding, cosine_similarity

# Minimum similarity ratio (0–1) to consider a log entry a match.
# 0.92 is deliberately conservative: we only surface cache hits when
# the error text is nearly identical (same module name, same error type).
# Too low and structurally-similar errors (e.g. two different ModuleNotFoundErrors)
# get matched to each other even when the missing package differs.
SIMILARITY_THRESHOLD = 0.92

# Threshold for semantic cosine similarity if sentence-transformers is installed.
# 0.80 is empirically chosen to match identical errors with different variable names.
SEMANTIC_THRESHOLD = 0.80


@dataclass
class CacheHit:
    """A previously verified fix that closely matches the current error."""

    fix: str
    diagnosis: str
    score: float            # 0.0 – 1.0 similarity ratio
    original_command: str   # the command that originally triggered the error
    previously_worked: bool # True if fix_worked=True in the log entry
    category: str           # The ecosystem category of the error


def find_cached_fix(
    error_text: str,
    log_file: str = "",           # empty string → resolved at call-time
    threshold: float = SIMILARITY_THRESHOLD,
    category: str = "general",
) -> Optional[CacheHit]:
    """
    Search the user's log for a previously attempted fix for a similar error.

    log_file defaults to the current user's personal log file if not supplied.
    Passing an explicit path is still supported (used in tests).

    Two tiers:
    - Prefers entries where the fix is CONFIRMED to have worked (fix_worked=True).
    - Falls back to entries where the user APPROVED the fix (user_approved=True)
      even if fix_worked=False/None — this surfaces "we've already tried this"
      so Ollama is not called again for the same problem.

    Uses difflib.SequenceMatcher for lightweight fuzzy string similarity.
    Supports both Phase 1 (worked/fix/stderr) and Phase 2 schemas transparently.

    Args:
        error_text: The current stderr text to match against.
        log_file:   Path to the JSON log file (defaults to cwd).
        threshold:  Minimum SequenceMatcher ratio to accept as a hit.
        category:   The ecosystem category. Only matches logs with the same category.

    Returns:
        A CacheHit with the best-matching fix, or None if no good match found.
    """
    if not log_file:
        log_file = get_log_file()

    if not os.path.exists(log_file):
        return None

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            log_data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    if not isinstance(log_data, list) or not log_data:
        return None

    # We keep two best candidates: one that worked, one that was merely approved.
    best_worked:   Optional[tuple[float, CacheHit]] = None
    best_approved: Optional[tuple[float, CacheHit]] = None
    
    current_embedding = get_embedding(error_text)

    for entry in log_data:
        # ── Support both Phase 1 and Phase 2 schemas ─────────────────────
        fix_worked = (
            entry.get("fix_worked")
            if "fix_worked" in entry
            else entry.get("worked")
        )
        user_approved = (
            entry.get("user_approved")
            if "user_approved" in entry
            else entry.get("approved", False)
        )

        # Only use entries the user actually approved (ignore "n" declines)
        if not user_approved:
            continue

        entry_category = entry.get("category", "general")
        if entry_category != category:
            continue

        stored_error: str = entry.get("error_text") or entry.get("stderr", "")
        fix: str          = entry.get("fix_command") or entry.get("fix", "")
        diagnosis: str    = entry.get("diagnosis", "")
        original_cmd: str = entry.get("original_command") or entry.get("command", "")

        if not stored_error or not fix:
            continue
            
        stored_embedding = entry.get("embedding")
        is_semantic = False
        
        if current_embedding and stored_embedding:
            score = cosine_similarity(current_embedding, stored_embedding)
            is_semantic = True
            hit_threshold = SEMANTIC_THRESHOLD
        else:
            score = SequenceMatcher(None, error_text, stored_error).ratio()
            hit_threshold = SIMILARITY_THRESHOLD

        if score < hit_threshold:
            continue

        hit = CacheHit(
            fix=fix,
            diagnosis=diagnosis,
            score=score,
            original_command=original_cmd,
            previously_worked=bool(fix_worked),
            category=entry_category,
        )

        if fix_worked:
            if best_worked is None or score > best_worked[0]:
                best_worked = (score, hit)
        else:
            if best_approved is None or score > best_approved[0]:
                best_approved = (score, hit)

    # Prefer a confirmed-working hit over a merely-approved one
    if best_worked:
        return best_worked[1]
    if best_approved:
        return best_approved[1]
    return None
