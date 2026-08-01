"""tests/test_providers.py — Tests for provider error handling and mocked API calls."""

import os
import pytest
from unittest.mock import patch, MagicMock

from envfix.providers.gemini import GeminiProvider
from envfix.providers.groq import GroqProvider
from envfix.providers.ollama import OllamaProvider


class TestGeminiProvider:

    def test_missing_api_key_raises_error(self, monkeypatch):
        # Ensure the API key is strictly not set
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        
        provider = GeminiProvider()
        with pytest.raises(RuntimeError) as exc_info:
            provider.diagnose("test prompt")
            
        assert "GEMINI_API_KEY environment variable is not set" in str(exc_info.value)

    @patch("google.genai.Client")
    def test_successful_mocked_call(self, mock_client_class, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake_key")
        
        # Mock the client structure: client.models.generate_content().text
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "DIAGNOSIS: bad\nFIX: good"
        mock_client.models.generate_content.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        provider = GeminiProvider()
        result = provider.diagnose("test prompt")
        
        assert result == "DIAGNOSIS: bad\nFIX: good"
        mock_client_class.assert_called_once_with(api_key="fake_key")


class TestGroqProvider:

    def test_missing_api_key_raises_error(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        
        provider = GroqProvider()
        with pytest.raises(RuntimeError) as exc_info:
            provider.diagnose("test prompt")
            
        assert "GROQ_API_KEY environment variable is not set" in str(exc_info.value)

    @patch("groq.Groq")
    def test_successful_mocked_call(self, mock_groq_class, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "fake_groq_key")
        
        # Mock the Groq response structure: client.chat.completions.create().choices[0].message.content
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "DIAGNOSIS: groq error\nFIX: groq fix"
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_completion
        mock_groq_class.return_value = mock_client
        
        provider = GroqProvider()
        result = provider.diagnose("test prompt")
        
        assert result == "DIAGNOSIS: groq error\nFIX: groq fix"
        mock_groq_class.assert_called_once_with(api_key="fake_groq_key")


class TestOllamaProvider:

    @patch("ollama.chat")
    def test_successful_mocked_call(self, mock_chat):
        # Ollama doesn't require an API key by default
        mock_chat.return_value = {
            "message": {"content": "DIAGNOSIS: ollama\nFIX: ollama fix"}
        }
        
        provider = OllamaProvider()
        result = provider.diagnose("test prompt")
        
        assert result == "DIAGNOSIS: ollama\nFIX: ollama fix"
        mock_chat.assert_called_once()
