"""Vector store for the internal knowledge base with TENANT ISOLATION.

Every query is forced through a client_id filter: a search can only ever see
documents belonging to that client plus the '__global__' reference scope.
There is deliberately NO API to search across tenants - cross-client leakage
is prevented structurally, not by prompting.
"""
from __future__ import annotations

import hashlib
import math
import re
import uuid

import config


class _KeywordEmbedding:
    """Tiny dependency-free embedding fallback (bag-of-hashed-words). Used only
    when chromadb's default embedding model cannot be downloaded (offline)."""

    DIM = 256

    def __call__(self, input):  # noqa: A002 - chroma API parameter name
        vectors = []
        for doc in input:
            vec = [0.0] * self.DIM
            for tok in re.findall(r"[a-z0-9]+", (doc or "").lower()):
                idx = int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.DIM
                vec[idx] += 1.0
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            vectors.append([x / norm for x in vec])
        return vectors


def _pick_embedding_function():
    try:
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

        ef = DefaultEmbeddingFunction()
        ef(["ping"])  # smoke-test (may download a model on first use)
        return ef
    except Exception:
        return _KeywordEmbedding()


class VectorStore:
    GLOBAL_SCOPE = "__global__"

    def __init__(self) -> None:
        import chromadb

        client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
        self._collection = client.get_or_create_collection(
            "financial_kb",
            embedding_function=_pick_embedding_function(),
            metadata={"hnsw:space": "cosine"},
        )

    def add_documents(self, owner_scope: str, docs: list[dict]) -> int:
        """owner_scope: a client_id or GLOBAL_SCOPE. docs: [{'title':..,'text':..}]"""
        if not docs:
            return 0
        self._collection.add(
            ids=[str(uuid.uuid4()) for _ in docs],
            documents=[d["text"] for d in docs],
            metadatas=[{"client_id": owner_scope, "title": d["title"]} for d in docs],
        )
        return len(docs)

    def search(self, query: str, requesting_client_id: str, k: int = 4) -> list[dict]:
        """Tenant-isolated retrieval: requesting client's docs + global docs ONLY."""
        count = self._collection.count()
        if count == 0:
            return []
        where = {
            "$or": [
                {"client_id": requesting_client_id},
                {"client_id": self.GLOBAL_SCOPE},
            ]
        }
        result = self._collection.query(
            query_texts=[query], n_results=min(k, count), where=where
        )
        hits = []
        for i in range(len(result["ids"][0])):
            meta = result["metadatas"][0][i]
            hits.append({
                "title": meta.get("title", ""),
                "owner_scope": meta.get("client_id", ""),
                "text": result["documents"][0][i],
                "distance": (
                    result["distances"][0][i] if result.get("distances") else None
                ),
            })
        return hits