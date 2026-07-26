"""ai.py — Calls local or cloud AI models and parses their responses."""

import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from envfix.context import CodeContext


try:
    import ollama
except ImportError:  # pragma: no cover
    ollama = None  # type: ignore[assignment]

try:
    import groq
except ImportError:
    groq = None

try:
    from google import genai
except ImportError:
    genai = None


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

# Used when a code snippet from the failing file is available.
# Gives the model much richer context than the raw error text alone.
PROMPT_TEMPLATE_WITH_CONTEXT = (
    "You are diagnosing a development environment error on a Windows machine. "
    "The user has specified this error is related to the '{category}' ecosystem.\n\n"
    "Here is the error output:\n{stderr}\n\n"
    "Here is the relevant code from {filepath}, lines {start}-{end}:\n"
    "```\n{snippet}\n```\n\n"
    "Using both the error and the code above, give a precise diagnosis (1-2 sentences) "
    "that references the actual code where possible, "
    "then give exactly ONE shell command that would likely fix it. "
    "Respond in this exact format:\n"
    "DIAGNOSIS: <text>\n"
    "FIX: <command>\n\n"
    "IMPORTANT rules for the FIX command:\n"
    "- If it's a Python pip error, use 'python -m pip install ...' instead of 'pip install ...'\n"
    "- NO backticks, NO markdown formatting, NO surrounding quotes around the command\n"
    "- Give a single runnable shell command only\n"
    "Example correct format:\n"
    "DIAGNOSIS: Line 42 calls `train()` before the model is loaded.\n"
    "FIX: python -m pip install torch"
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

    diagnosis: str
    fix: str
    raw_response: str
    parsed_ok: bool


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
    if code_context is not None:
        prompt = PROMPT_TEMPLATE_WITH_CONTEXT.format(
            stderr=stderr,
            category=category,
            filepath=code_context.filepath,
            start=code_context.start_line,
            end=code_context.end_line,
            snippet=code_context.snippet,
        )
    else:
        prompt = PROMPT_TEMPLATE.format(stderr=stderr, category=category)

    if provider == "ollama":
        if ollama is None:
            raise RuntimeError(
                "The 'ollama' Python package is not installed. "
                "Run: pip install ollama"
            )
        try:
            response = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response["message"]["content"].strip()
        except Exception as exc:
            raise RuntimeError(
                f"Ollama request failed: {exc}\n"
                "Make sure the Ollama service is running (`ollama serve`) "
                f"and the model '{model}' is pulled (`ollama pull {model}`)."
            ) from exc

    elif provider == "groq":
        if groq is None:
            raise RuntimeError("The 'groq' Python package is not installed.")
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY environment variable is not set. "
                "Please set it to your Groq API key."
            )
        try:
            client = groq.Groq(api_key=api_key)
            actual_model = get_actual_model(model, provider)
            chat_completion = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=actual_model,
            )
            raw = chat_completion.choices[0].message.content.strip()
        except Exception as exc:
            raise RuntimeError(f"Groq request failed: {exc}") from exc

    elif provider == "gemini":
        if genai is None:
            raise RuntimeError("The 'google-genai' Python package is not installed.")
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY environment variable is not set. "
                "Please set it to your Gemini API key."
            )
        try:
            client = genai.Client(api_key=api_key)
            actual_model = get_actual_model(model, provider)
            response = client.models.generate_content(
                model=actual_model, 
                contents=prompt
            )
            raw = response.text.strip()
        except Exception as exc:
            raise RuntimeError(f"Gemini API call failed: {exc}") from exc

    else:
        raise ValueError(f"Unknown provider: {provider}")

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
