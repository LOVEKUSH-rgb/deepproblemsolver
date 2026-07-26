"""ai.py — Calls the local Ollama model and parses its response."""

import re
from dataclasses import dataclass
from typing import Optional

try:
    import ollama
except ImportError:  # pragma: no cover
    ollama = None  # type: ignore[assignment]


PROMPT_TEMPLATE = (
    "You are diagnosing a development environment error on a Windows machine. "
    "The user has specified this error is related to the '{category}' ecosystem "
    "(it could be Python, Node.js, package managers, build tools, permissions, or general shell errors).\n"
    "Here is the error output:\n{stderr}\n\n"
    "Give a short diagnosis (1-2 sentences) of the root cause, "
    "then give exactly ONE shell command that would likely fix it. "
    "Respond in this exact format:\n"
    "DIAGNOSIS: <text>\n"
    "FIX: <command>\n\n"
    "IMPORTANT rules for the FIX command:\n"
    "- If it's a Python pip error, use 'python -m pip install ...' instead of 'pip install ...'\n"
    "- NO backticks, NO markdown formatting, NO surrounding quotes around the command\n"
    "- Give a single runnable shell command only\n"
    "Example correct format:\n"
    "DIAGNOSIS: The torch package is not installed.\n"
    "FIX: python -m pip install torch"
)

DEFAULT_MODEL = "llama3.1:8b"


@dataclass
class DiagnosisResult:
    """Structured result from the AI model."""

    diagnosis: str
    fix: str
    raw_response: str
    parsed_ok: bool


def get_diagnosis(
    stderr: str, 
    model: str = DEFAULT_MODEL, 
    category: str = "general",
) -> DiagnosisResult:
    """
    Send stderr to the local Ollama model and parse the structured response.

    If the model doesn't follow the DIAGNOSIS/FIX format exactly, the raw
    response is returned in both fields so the caller can still display it
    without crashing.

    Args:
        stderr:   The captured error text from the failed command.
        model:    Ollama model tag to use (default: llama3.1:8b).
        category: The ecosystem category (e.g. 'node', 'python', 'general').

    Returns:
        A DiagnosisResult with diagnosis, fix, raw_response, and parsed_ok.

    Raises:
        RuntimeError: If the `ollama` package is not installed or the
                      Ollama service is unreachable.
    """
    if ollama is None:
        raise RuntimeError(
            "The 'ollama' Python package is not installed. "
            "Run: pip install ollama"
        )

    prompt = PROMPT_TEMPLATE.format(stderr=stderr, category=category)

    try:
        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        raw: str = response["message"]["content"].strip()
    except Exception as exc:
        raise RuntimeError(
            f"Ollama request failed: {exc}\n"
            "Make sure the Ollama service is running (`ollama serve`) "
            f"and the model '{model}' is pulled (`ollama pull {model}`)."
        ) from exc

    return _parse_response(raw)


def _parse_response(raw: str) -> DiagnosisResult:
    """
    Extract DIAGNOSIS and FIX from the model's raw text.

    Tries a strict regex first, then falls back to a lenient line scan.
    If neither works, marks parsed_ok=False and stuffs the raw text into
    both fields so the UI can still display something useful.
    """
    # --- Strict parse: both keys on their own lines (case-insensitive) ---
    strict = re.search(
        r"DIAGNOSIS\s*:\s*(.+?)\s*FIX\s*:\s*(.+)",
        raw,
        re.IGNORECASE | re.DOTALL,
    )
    if strict:
        diagnosis = strict.group(1).strip()
        fix = _clean_fix(strict.group(2).strip().splitlines()[0].strip())
        return DiagnosisResult(
            diagnosis=diagnosis, fix=fix, raw_response=raw, parsed_ok=True
        )

    # --- Lenient parse: scan line-by-line ---
    diagnosis: Optional[str] = None
    fix: Optional[str] = None
    for line in raw.splitlines():
        stripped = line.strip()
        if diagnosis is None and re.match(r"DIAGNOSIS\s*:", stripped, re.IGNORECASE):
            diagnosis = re.sub(r"^DIAGNOSIS\s*:\s*", "", stripped, flags=re.IGNORECASE)
        elif fix is None and re.match(r"FIX\s*:", stripped, re.IGNORECASE):
            fix = re.sub(r"^FIX\s*:\s*", "", stripped, flags=re.IGNORECASE)

    if diagnosis and fix:
        return DiagnosisResult(
            diagnosis=diagnosis, fix=_clean_fix(fix), raw_response=raw, parsed_ok=True
        )

    # --- Fallback: show raw output, don't crash ---
    return DiagnosisResult(
        diagnosis=raw,
        fix="(could not parse a fix command — see diagnosis above)",
        raw_response=raw,
        parsed_ok=False,
    )


def _clean_fix(fix: str) -> str:
    """
    Strip markdown/shell formatting artefacts from the fix command and
    normalise Windows-incompatible patterns.

    LLMs often wrap commands in backticks (`` `cmd` ``) or fenced code blocks.
    Running `` `pip install torch` `` on Windows will fail because the backtick
    is not a valid shell character there.

    Also replaces bare 'pip install' with 'python -m pip install' because pip
    is often not on the Windows PATH even when python is.
    """
    # Strip surrounding backticks: `cmd` → cmd  or ```cmd``` → cmd
    fix = fix.strip()
    fix = re.sub(r'^`+|`+$', '', fix).strip()
    # Strip surrounding single or double quotes added by the model
    if (fix.startswith('"') and fix.endswith('"')) or \
       (fix.startswith("'") and fix.endswith("'")):
        fix = fix[1:-1].strip()
    # Strip markdown emphasis like *cmd* or **cmd**
    fix = re.sub(r'^\*+|\*+$', '', fix).strip()
    # Replace bare 'pip' with 'python -m pip' so it works when pip is not on PATH
    fix = re.sub(r'^pip\b', 'python -m pip', fix)
    return fix
