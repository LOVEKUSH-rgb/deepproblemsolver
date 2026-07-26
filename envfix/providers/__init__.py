"""providers/__init__.py — Provider registry and factory function."""

from envfix.providers.base import AIProvider
from envfix.providers.ollama import OllamaProvider
from envfix.providers.groq import GroqProvider
from envfix.providers.gemini import GeminiProvider

_REGISTRY: dict[str, type[AIProvider]] = {
    "ollama": OllamaProvider,
    "groq":   GroqProvider,
    "gemini": GeminiProvider,
}


def get_provider(name: str, model: str) -> AIProvider:
    """
    Look up and instantiate an AIProvider by name.

    Args:
        name:  Provider name string ("ollama", "groq", "gemini").
        model: Model tag/name to pass to the provider constructor.

    Returns:
        An instantiated AIProvider ready to call `.diagnose()` on.

    Raises:
        ValueError: If `name` is not a registered provider.
    """
    cls = _REGISTRY.get(name)
    if cls is None:
        known = ", ".join(f'"{k}"' for k in _REGISTRY)
        raise ValueError(
            f"Unknown provider '{name}'. Known providers: {known}."
        )
    return cls(model=model)


__all__ = [
    "AIProvider",
    "OllamaProvider",
    "GroqProvider",
    "GeminiProvider",
    "get_provider",
]
