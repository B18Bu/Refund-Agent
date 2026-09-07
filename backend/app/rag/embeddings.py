"""调用仅限集群内部访问的本地 embedding 服务。"""
from __future__ import annotations

import math
from typing import Protocol

import httpx

from app.config import settings

EMBEDDING_SERVICE_URL = "http://rag-embedding:8080"
EMBEDDING_DIMENSION = 512


class EmbeddingUnavailable(RuntimeError):
    """embedding 服务不可用或返回不可信向量。"""


class HttpClient(Protocol):
    def post(self, url: str, json: dict, timeout: float): ...


class EmbeddingClient:
    """仅连接固定内部服务地址，防止调用方指定任意 URL。"""

    def __init__(self, http_client: HttpClient | None = None, dimension: int | None = None):
        self._http_client = http_client or httpx.Client()
        self.dimension = dimension if dimension is not None else settings.RAG_EMBEDDING_DIMENSION
        if self.dimension != EMBEDDING_DIMENSION:
            raise ValueError("RAG embedding 维度必须固定为 512")

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self._http_client.post(
                f"{EMBEDDING_SERVICE_URL}/embed", json={"texts": texts}, timeout=10.0
            )
            response.raise_for_status()
            vectors = response.json()["vectors"]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise EmbeddingUnavailable("本地 embedding 服务不可用") from exc
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise EmbeddingUnavailable("embedding 返回数量不匹配")
        if any(
            not isinstance(vector, list)
            or len(vector) != self.dimension
            or any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) for item in vector)
            for vector in vectors
        ):
            raise EmbeddingUnavailable(f"embedding 必须包含 {self.dimension} 个有限数值")
        return [[float(item) for item in vector] for vector in vectors]
