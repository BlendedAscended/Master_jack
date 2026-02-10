# mcp-server/tools/vectors.py
"""
Local Vector Embedding Tools (CPU-only)

Uses fastembed with BAAI/bge-small-en-v1.5 for local embeddings.
No external API calls — runs entirely on CPU.

Singleton pattern: model loads once at server start, reused across requests.

Model details:
- BAAI/bge-small-en-v1.5
- 384 dimensions
- ~90MB download (cached after first load)
- Optimized for retrieval tasks
"""

import threading
from fastembed import TextEmbedding


class VectorTools:
    """Singleton wrapper around fastembed for local CPU embeddings."""

    _instance = None
    _lock = threading.Lock()
    _model: TextEmbedding = None

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if VectorTools._model is None:
            with VectorTools._lock:
                if VectorTools._model is None:
                    VectorTools._model = TextEmbedding(
                        model_name="BAAI/bge-small-en-v1.5"
                    )

    @property
    def dimensions(self) -> int:
        """Vector dimensions for bge-small-en-v1.5."""
        return 384

    def generate_embedding(self, text: str) -> list[float]:
        """
        Generate a 384-dimension embedding vector for the given text.

        Args:
            text: Input text to embed (truncated to 512 tokens by the model)

        Returns:
            list[float] of length 384
        """
        # fastembed.embed() returns a generator of numpy arrays
        embeddings = list(VectorTools._model.embed([text]))
        return embeddings[0].tolist()

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """
        Batch-generate embeddings for multiple texts.

        Args:
            texts: List of input texts

        Returns:
            list of list[float], each of length 384
        """
        embeddings = list(VectorTools._model.embed(texts))
        return [emb.tolist() for emb in embeddings]
