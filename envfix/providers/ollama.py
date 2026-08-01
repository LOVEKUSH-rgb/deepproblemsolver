"""providers/ollama.py — Ollama local model provider."""

from envfix.providers.base import AIProvider


DEFAULT_OLLAMA_MODEL = "llama3.1:8b"


class OllamaProvider(AIProvider):
    """Runs inference against a locally running Ollama service."""

    def __init__(self, model: str = DEFAULT_OLLAMA_MODEL) -> None:
        self.model = model

    def diagnose(self, prompt_text: str) -> str:
        try:
            import ollama as _ollama
        except ImportError:
            raise RuntimeError(
                "The 'ollama' Python package is not installed. "
                "Run: pip install ollama"
            )

        try:
            response = _ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt_text}],
            )
            return response["message"]["content"].strip()
        except Exception as exc:
            if "connect" in str(exc).lower():
                raise RuntimeError(
                    "[!] Could not connect to local Ollama server. Make sure Ollama "
                    "is running (run 'ollama serve' in another terminal)."
                ) from exc
            raise RuntimeError(
                f"Ollama request failed: {exc}\n"
                "Make sure the Ollama service is running (`ollama serve`) "
                f"and the model '{self.model}' is pulled (`ollama pull {self.model}`)."
            ) from exc
