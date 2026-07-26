"""providers/groq.py — Groq cloud API provider."""

import os

from envfix.providers.base import AIProvider

try:
    import groq as _groq
except ImportError:
    _groq = None  # type: ignore[assignment]

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


class GroqProvider(AIProvider):
    """Calls Groq's cloud inference API using GROQ_API_KEY."""

    def __init__(self, model: str = DEFAULT_GROQ_MODEL) -> None:
        # If the caller passed the generic Ollama default, swap it for the
        # correct Groq model so the user never needs to specify --model.
        from envfix.ai import DEFAULT_MODEL  # avoid circular at module level
        self.model = DEFAULT_GROQ_MODEL if model == DEFAULT_MODEL else model

    def diagnose(self, prompt_text: str) -> str:
        if _groq is None:
            raise RuntimeError("The 'groq' Python package is not installed.")

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY environment variable is not set. "
                "Please set it to your Groq API key."
            )
        try:
            client = _groq.Groq(api_key=api_key)
            completion = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt_text}],
                model=self.model,
            )
            return completion.choices[0].message.content.strip()
        except Exception as exc:
            raise RuntimeError(f"Groq request failed: {exc}") from exc
