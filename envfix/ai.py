"""ai.py — Prompt building, response parsing, and provider dispatch for envfix."""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from envfix.context import CodeContext

from envfix.providers import get_provider


PROMPT_TEMPLATE = (
    "You are diagnosing a development environment error on a Windows machine. "
    "The user has specified this error is related to the '{category}' ecosystem "
    "(e.g., python, node, rust, go, java, docker, or general).\n"
    "This is a {category} error. Tailor your diagnosis and suggested fix command specifically for the {category} ecosystem.\n"
    "{local_context}"
    "Here is the error output:\n{stderr}\n\n"
    "First, classify this error as either:\n"
    "- ENVIRONMENT_ISSUE: caused by missing packages, version conflicts, PATH problems, or configuration — fixable with a terminal command\n"
    "- CODE_ISSUE: caused by a bug in the user's own code logic (undefined variables/functions, syntax errors, typos, incorrect logic) — NOT fixable by any terminal command\n\n"
    "If ENVIRONMENT_ISSUE: give a diagnosis and one terminal command fix.\n"
    "If CODE_ISSUE: give a diagnosis explaining the likely bug and what the user should check or change in their code, then set FIX to exactly the string NONE. Do not invent a terminal command for a code-logic problem under any circumstances.\n\n"
    "You are a friendly, expert debugging assistant.\n"
    "When you detect a CODE_ISSUE (like a SyntaxError, TypeError, or IndentationError), the DIAGNOSIS field MUST follow this structure:\n"
    "1. THE TRANSLATION: Explain the error in 1-2 sentences of extremely simple, plain English, naming the exact line number. Example: 'You forgot to put a closing parenthesis ) at the end of line 42.'\n"
    "2. CORRECTED CODE: The CORRECTED CODE section must contain the actual fixed line(s) of code as a code block, not a description. For example, for a NameError caused by an undefined bare word that looks like it was meant to be a string, prefer the most likely interpretation (a missing quote typo) over a less likely one (an intentionally undefined variable), unless context clearly suggests otherwise.\n\n"
    "Never use jargon like 'unexpected EOF while parsing' or 'invalid syntax' without immediately translating it into plain language in the same sentence.\n\n"
    "Continue to follow the existing DIAGNOSIS/FIX response format exactly — DIAGNOSIS contains this translation + fix explanation, FIX remains NONE for code-logic issues as already implemented.\n\n"
    "Respond in this exact format:\n"
    "CLASSIFICATION: <ENVIRONMENT_ISSUE or CODE_ISSUE>\n"
    "DIAGNOSIS: <text>\n"
    "FIX: <command or NONE>\n\n"
    "IMPORTANT rules for the FIX command (if not NONE):\n"
    "- If it's a Python pip error, use 'python -m pip install ...' instead of 'pip install ...'\n"
    "- NO backticks, NO markdown formatting, NO surrounding quotes around the command\n"
    "- Give a single runnable shell command only\n"
    "Example correct format:\n"
    "CLASSIFICATION: ENVIRONMENT_ISSUE\n"
    "DIAGNOSIS: The torch package is not installed.\n"
    "FIX: python -m pip install torch\n\n"
    "Example correct format for CODE_ISSUE:\n"
    "CLASSIFICATION: CODE_ISSUE\n"
    "DIAGNOSIS: 1. THE TRANSLATION: You likely meant to print the text 'hi', but forgot the quotes.\n"
    "2. CORRECTED CODE: print(\"hi\")\n"
    "FIX: NONE"
)

# Used when a code snippet from the failing file is available.
# Gives the model much richer context than the raw error text alone.
PROMPT_TEMPLATE_WITH_CONTEXT = (
    "You are diagnosing a development environment error on a Windows machine. "
    "The user has specified this error is related to the '{category}' ecosystem.\n"
    "This is a {category} error. Tailor your diagnosis and suggested fix command specifically for the {category} ecosystem.\n\n"
    "{local_context}"
    "Here is the error output:\n{stderr}\n\n"
    "Here is the relevant code from {filepath}, lines {start}-{end}:\n"
    "```\n{snippet}\n```\n\n"
    "First, classify this error as either:\n"
    "- ENVIRONMENT_ISSUE: caused by missing packages, version conflicts, PATH problems, or configuration — fixable with a terminal command\n"
    "- CODE_ISSUE: caused by a bug in the user's own code logic (undefined variables/functions, syntax errors, typos, incorrect logic) — NOT fixable by any terminal command\n\n"
    "If ENVIRONMENT_ISSUE: give a diagnosis and one terminal command fix.\n"
    "If CODE_ISSUE: give a diagnosis explaining the likely bug and what the user should check or change in their code, then set FIX to exactly the string NONE. Do not invent a terminal command for a code-logic problem under any circumstances.\n\n"
    "You are a friendly, expert debugging assistant.\n"
    "When you detect a CODE_ISSUE (like a SyntaxError, TypeError, or IndentationError), the DIAGNOSIS field MUST follow this structure:\n"
    "1. THE TRANSLATION: Explain the error in 1-2 sentences of extremely simple, plain English, naming the exact line number. Example: 'You forgot to put a closing parenthesis ) at the end of line 42.'\n"
    "2. CORRECTED CODE: The CORRECTED CODE section must contain the actual fixed line(s) of code as a code block, not a description. For example, for a NameError caused by an undefined bare word that looks like it was meant to be a string, prefer the most likely interpretation (a missing quote typo) over a less likely one (an intentionally undefined variable), unless context clearly suggests otherwise.\n\n"
    "Never use jargon like 'unexpected EOF while parsing' or 'invalid syntax' without immediately translating it into plain language in the same sentence.\n\n"
    "Continue to follow the existing DIAGNOSIS/FIX response format exactly — DIAGNOSIS contains this translation + fix explanation, FIX remains NONE for code-logic issues as already implemented.\n\n"
    "Respond in this exact format:\n"
    "CLASSIFICATION: <ENVIRONMENT_ISSUE or CODE_ISSUE>\n"
    "DIAGNOSIS: <text>\n"
    "FIX: <command or NONE>\n\n"
    "IMPORTANT rules for the FIX command (if not NONE):\n"
    "- If it's a Python pip error, use 'python -m pip install ...' instead of 'pip install ...'\n"
    "- NO backticks, NO markdown formatting, NO surrounding quotes around the command\n"
    "- Give a single runnable shell command only\n"
    "Example correct format:\n"
    "CLASSIFICATION: ENVIRONMENT_ISSUE\n"
    "DIAGNOSIS: The torch package is not installed.\n"
    "FIX: python -m pip install torch\n\n"
    "Example correct format for CODE_ISSUE:\n"
    "CLASSIFICATION: CODE_ISSUE\n"
    "DIAGNOSIS: 1. THE TRANSLATION: You likely meant to print the text 'hi', but forgot the quotes.\n"
    "2. CORRECTED CODE: print(\"hi\")\n"
    "FIX: NONE"
)

PROMPT_DOCTOR_TEMPLATE = (
    "You are diagnosing a development environment compatibility issue on a Windows machine.\n"
    "Conflict detected: {conflict_details}\n\n"
    "Explain in 1-2 plain-English sentences why this version mismatch causes problems, "
    "then suggest exactly ONE shell command that would likely fix it (e.g. downgrading/upgrading a package).\n"
    "Respond in this exact format:\n"
    "DIAGNOSIS: <text>\n"
    "FIX: <command>\n\n"
    "IMPORTANT rules for the FIX command:\n"
    "- If it's a Python pip error, use 'python -m pip install ...' instead of 'pip install ...'\n"
    "- NO backticks, NO markdown formatting, NO surrounding quotes around the command\n"
    "- Give a single runnable shell command only\n"
)

DEFAULT_MODEL = "llama3.1:8b"


def get_actual_model(model: str, provider: str) -> str:
    """Resolve the actual model string if the user left it as the Ollama default."""
    if model != DEFAULT_MODEL:
        return model
    
    if provider == "groq":
        return "llama-3.3-70b-versatile"
    elif provider == "gemini":
        return "gemini-3.5-flash"
    
    return DEFAULT_MODEL


@dataclass
class DiagnosisResult:
    """Structured result from the AI model."""

    classification: str
    diagnosis: str
    fix: str
    raw_response: str
    parsed_ok: bool
    mismatch_flagged: bool = False


def get_diagnosis(
    stderr: str,
    model: str = DEFAULT_MODEL,
    category: str = "general",
    code_context: "Optional[CodeContext]" = None,
    provider: str = "ollama",
) -> DiagnosisResult:
    """
    Send stderr (and optional code context) to the chosen AI provider.

    Args:
        stderr:       The captured error text from the failed command.
        model:        Model tag to use (default: llama3.1:8b for ollama).
        category:     The ecosystem category.
        code_context: Optional in-project code snippet extracted from the traceback.
        provider:     Which AI service to use ("ollama", "groq", or "gemini").

    Returns:
        A DiagnosisResult with diagnosis, fix, raw_response, and parsed_ok.
    """
    try:
        from envfix.indexer import query_index
        retrieved_chunks = query_index(stderr)
        if retrieved_chunks:
            chunks_text = "\n\n".join(retrieved_chunks)
            local_context = f"Here is potentially relevant code from elsewhere in the project:\n\n{chunks_text}\n\n"
        else:
            local_context = ""
    except ImportError:
        local_context = ""

    if code_context is not None:
        prompt = PROMPT_TEMPLATE_WITH_CONTEXT.format(
            stderr=stderr,
            category=category,
            filepath=code_context.filepath,
            start=code_context.start_line,
            end=code_context.end_line,
            snippet=code_context.snippet,
            local_context=local_context,
        )
    else:
        prompt = PROMPT_TEMPLATE.format(stderr=stderr, category=category, local_context=local_context)

    raw = get_provider(provider, model).diagnose(prompt)
    return _parse_response(raw)


def get_doctor_fix(
    conflict_details: str,
    model: str = DEFAULT_MODEL,
    provider: str = "ollama",
) -> DiagnosisResult:
    """
    Send a compatibility warning to the chosen AI provider to get an explanation and fix.
    """
    prompt = PROMPT_DOCTOR_TEMPLATE.format(conflict_details=conflict_details)
    raw = get_provider(provider, model).diagnose(prompt)
    return _parse_response(raw)

def _parse_response(raw: str) -> DiagnosisResult:
    """
    Extract CLASSIFICATION, DIAGNOSIS and FIX from the model's raw text.

    Tries a strict regex first, then falls back to a lenient line scan.
    If neither works, marks parsed_ok=False and stuffs the raw text into
    both fields so the UI can still display something useful.
    """
    # --- Strict parse: keys on their own lines (case-insensitive) ---
    strict = re.search(
        r"CLASSIFICATION\s*:\s*(.+?)\s*DIAGNOSIS\s*:\s*(.+?)\s*FIX\s*:\s*(.+)",
        raw,
        re.IGNORECASE | re.DOTALL,
    )
    if strict:
        classification = strict.group(1).strip()
        diagnosis = strict.group(2).strip()
        fix_raw = strict.group(3).strip().splitlines()[0].strip()
        
        # Check if the model explicitly returned NONE
        if fix_raw.upper() == "NONE":
            fix = "NONE"
        else:
            fix = _clean_fix(fix_raw)
            
        return DiagnosisResult(
            classification=classification, diagnosis=diagnosis, fix=fix, raw_response=raw, parsed_ok=True
        )

    # --- Lenient parse: scan line-by-line ---
    classification: Optional[str] = None
    diagnosis: Optional[str] = None
    fix: Optional[str] = None
    for line in raw.splitlines():
        stripped = line.strip()
        if classification is None and re.match(r"CLASSIFICATION\s*:", stripped, re.IGNORECASE):
            classification = re.sub(r"^CLASSIFICATION\s*:\s*", "", stripped, flags=re.IGNORECASE)
        elif diagnosis is None and re.match(r"DIAGNOSIS\s*:", stripped, re.IGNORECASE):
            diagnosis = re.sub(r"^DIAGNOSIS\s*:\s*", "", stripped, flags=re.IGNORECASE)
        elif fix is None and re.match(r"FIX\s*:", stripped, re.IGNORECASE):
            fix_raw = re.sub(r"^FIX\s*:\s*", "", stripped, flags=re.IGNORECASE)
            if fix_raw.upper() == "NONE":
                fix = "NONE"
            else:
                fix = _clean_fix(fix_raw)

    if diagnosis and fix:
        return DiagnosisResult(
            classification=classification or "UNKNOWN", 
            diagnosis=diagnosis, 
            fix=fix, 
            raw_response=raw, 
            parsed_ok=True
        )

    # --- Fallback: show raw output, don't crash ---
    return DiagnosisResult(
        classification="UNKNOWN",
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
