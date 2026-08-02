"""embeddings.py — Semantic similarity using sentence-transformers."""

from typing import Optional, List




_model = None


def get_embedding(text: str) -> Optional[List[float]]:
    """
    Generate an embedding for the given text using all-MiniLM-L6-v2.
    Returns None if sentence-transformers is not installed.
    """
    global _model
    if _model is None:
        import os
        original_offline = os.environ.get("HF_HUB_OFFLINE")
        
        def set_offline(val: bool):
            if val:
                os.environ["HF_HUB_OFFLINE"] = "1"
            else:
                if original_offline is None:
                    os.environ.pop("HF_HUB_OFFLINE", None)
                else:
                    os.environ["HF_HUB_OFFLINE"] = original_offline

        set_offline(True)
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer("all-MiniLM-L6-v2")
        except ImportError:
            set_offline(False)
            return None
        except Exception:
            set_offline(False)
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer("all-MiniLM-L6-v2")
        finally:
            set_offline(False)

    # Encode returns a numpy array or tensor, convert to standard Python floats for JSON serialization
    embedding = _model.encode(text)
    return embedding.tolist()


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Compute cosine similarity between two embedding vectors.
    Returns 0.0 if sentence-transformers is not installed.
    """
    try:
        from sentence_transformers import util
    except ImportError:
        return 0.0

    # util.cos_sim returns a 2D tensor (1x1), we extract the float item
    return util.cos_sim(vec1, vec2).item()
