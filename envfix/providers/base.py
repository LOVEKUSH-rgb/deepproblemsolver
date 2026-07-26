"""providers/base.py — Abstract base class for all AI providers."""

from abc import ABC, abstractmethod


class AIProvider(ABC):
    """
    Abstract base for every AI backend envfix supports.

    Subclasses must implement `diagnose`, which takes a fully-rendered
    prompt string and returns the raw text response from the model.
    Parsing into (diagnosis, fix) is handled by ai.py so the logic
    lives in exactly one place.
    """

    @abstractmethod
    def diagnose(self, prompt_text: str) -> str:
        """
        Send a prompt to the AI backend and return the raw response text.

        Args:
            prompt_text: The fully-rendered prompt string.

        Returns:
            The raw text response from the model.

        Raises:
            RuntimeError: On any network, auth, or model error.
        """
