"""providers/gemini.py — Google Gemini cloud API provider."""

import os

from envfix.providers.base import AIProvider

try:
    from google import genai as _genai
except ImportError:
    _genai = None  # type: ignore[assignment]

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"


class GeminiProvider(AIProvider):
    """Calls the Google Gemini API using GEMINI_API_KEY."""

    def __init__(self, model: str = DEFAULT_GEMINI_MODEL) -> None:
        from envfix.ai import DEFAULT_MODEL  # avoid circular at module level
        self.model = DEFAULT_GEMINI_MODEL if model == DEFAULT_MODEL else model

    def diagnose(self, prompt_text: str) -> str:
        if _genai is None:
            raise RuntimeError("The 'google-genai' Python package is not installed.")

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY environment variable is not set. "
                "Please set it to your Gemini API key."
            )
        try:
            client = _genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=self.model,
                contents=prompt_text,
            )
            return response.text.strip()
        except Exception as exc:
            raise RuntimeError(f"Gemini API call failed: {exc}") from exc
