"""
Query-time semantic search: embed the user's question, cosine-similarity
against the cached matrix, return the top-k products' metadata only (never
stuff the whole catalog into the chat prompt).
"""
from pathlib import Path

import numpy as np
from google import genai
from google.genai import types as genai_types

from app.config import Settings
from app.db import connect


class CatalogSearch:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._genai_client = genai.Client(api_key=settings.gemini_api_key)

    def _load_matrix(self) -> np.ndarray | None:
        path: Path = self._settings.embeddings_path
        if not path.exists():
            return None
        return np.load(path)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        matrix = self._load_matrix()
        if matrix is None or matrix.shape[0] == 0:
            return []

        result = self._genai_client.models.embed_content(
            model=self._settings.gemini_embedding_model,
            contents=query,
            config=genai_types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
        )
        query_vec = np.array(result.embeddings[0].values, dtype=np.float32)

        # Cosine similarity against every cached product vector.
        norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query_vec)
        norms[norms == 0] = 1e-8
        scores = matrix @ query_vec / norms

        top_indices = np.argsort(-scores)[:top_k]

        with connect(self._settings.catalog_db_path) as conn:
            rows = conn.execute(
                f"SELECT * FROM products WHERE row_index IN "
                f"({','.join('?' * len(top_indices))})",
                [int(i) for i in top_indices],
            ).fetchall()

        by_index = {r["row_index"]: dict(r) for r in rows}
        # Preserve similarity-ranked order.
        return [by_index[i] for i in top_indices if i in by_index]
