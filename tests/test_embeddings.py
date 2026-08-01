"""tests/test_embeddings.py — Test semantic caching features and graceful degradation."""

import pytest
from unittest.mock import patch, MagicMock

import envfix.embeddings


def test_graceful_degradation_when_missing():
    # If sentence_transformers failed to import, everything returns None/0.0
    with patch.dict('sys.modules', {'sentence_transformers': None}):
        assert envfix.embeddings.get_embedding("test") is None
        assert envfix.embeddings.cosine_similarity([1.0], [1.0]) == 0.0


@patch("sentence_transformers.SentenceTransformer")
@patch("sentence_transformers.util")
def test_successful_embedding(mock_util, mock_st_class):
    # Mock model and its encode method
    mock_model = MagicMock()
    mock_tensor = MagicMock()
    mock_tensor.tolist.return_value = [0.1, 0.2, 0.3]
    mock_model.encode.return_value = mock_tensor
    mock_st_class.return_value = mock_model
    
    # Reset the global model to force reload
    envfix.embeddings._model = None
    
    result = envfix.embeddings.get_embedding("hello error")
    assert result == [0.1, 0.2, 0.3]
    
    # It should only instantiate SentenceTransformer once
    envfix.embeddings.get_embedding("second error")
    mock_st_class.assert_called_once_with("all-MiniLM-L6-v2")


@patch("sentence_transformers.util")
def test_cosine_similarity(mock_util):
    mock_tensor = MagicMock()
    mock_tensor.item.return_value = 0.95
    mock_util.cos_sim.return_value = mock_tensor
    
    score = envfix.embeddings.cosine_similarity([1.0], [1.0])
    assert score == 0.95
    mock_util.cos_sim.assert_called_once_with([1.0], [1.0])
